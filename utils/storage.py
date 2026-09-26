"""
Storage utilities - JSON load/save functions.
Otimizado para auditoria e compliance em cybersegurança/GRC.
Implementa file locking e escrita atômica para prevenir corrupção.
"""
import os
import json
import logging
import tempfile
import shutil
import time
from typing import Any
from contextlib import contextmanager

log = logging.getLogger("MaftyIntel")

# Diretório de dados fixo: evita divergência entre bot e vps_api no mesmo volume Docker.
# Preferir DATA_DIR (ex.: /app/data no Docker); senão, <projeto>/data a partir de __file__.
def _data_base_dir() -> str:
    env_dir = os.environ.get("DATA_DIR")
    if env_dir and os.path.isabs(env_dir):
        return os.path.abspath(env_dir)
    if env_dir:
        return os.path.abspath(os.path.join(os.getcwd(), env_dir))
    # Projeto = pasta acima de utils/
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(_root, "data")


def catalog_dir() -> str:
    """
    Diretório do CATÁLOGO versionado (sources.json).

    PROPÓSITO DE NEGÓCIO:
        Separar o catálogo, que vem da imagem, do estado de execução, que vive no
        volume. No compose o volume `./data:/app/data` sombreava o diretório
        inteiro: fonte nova commitada e imagem reconstruída, e o contêiner
        continuava lendo o sources.json velho do host. Em silêncio.

    INVARIANTES DO DOMÍNIO:
        CATALOG_DIR tem precedência; sem ele, <projeto>/data (desenvolvimento local).

    COMPORTAMENTO EM CASO DE FALHA:
        Nunca levanta; caminho inexistente aparece no arranque (impressão digital
        do catálogo) e no veredito da varredura.
    """
    env_dir = os.environ.get("CATALOG_DIR")
    if env_dir:
        return os.path.abspath(env_dir)
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(_root, "data")


def catalog_path(filename: str) -> str:
    """Caminho absoluto de um arquivo do catálogo (ver catalog_dir)."""
    return os.path.join(catalog_dir(), filename)


def p(filename: str) -> str:
    """
    Retorna o caminho absoluto para um arquivo, garantindo que arquivos de dados (.json)
    fiquem na pasta 'data/' para persistência (Docker Volumes).
    Usa diretório fixo (DATA_DIR ou <projeto>/data) para alinhar com vps_api no mesmo volume.
    Nota: "database.json" deve ir para data/; só ignoramos quando o path já é "data/..." ou contém /.
    """
    has_path = "/" in filename or "\\" in filename
    if filename.endswith(".json") and not has_path:
        # Coloca em data/ (DATA_DIR ou <projeto>/data); não excluir "database.json" por começar com "data"
        target = os.path.join(_data_base_dir(), filename)
    else:
        target = os.path.join(os.getcwd(), filename)
    return os.path.abspath(target)


def _candidatos_backup(filepath: str) -> list:
    """
    Backups de um arquivo, do mais confiável ao mais antigo: o `.backup` de
    emergência ao lado dele e depois os automáticos de data/backups (o mais
    recente primeiro). Os automáticos existem a cada varredura; sem este passo a
    recuperação só funcionava se uma gravação anterior tivesse falhado.
    """
    candidatos = []
    emergencia = filepath + ".backup"
    if os.path.exists(emergencia):
        candidatos.append(emergencia)
    pasta = os.path.join(_data_base_dir(), "backups")
    nome = os.path.basename(filepath)
    try:
        auto = [
            os.path.join(pasta, f) for f in os.listdir(pasta)
            if f.startswith(nome + "_") and f.endswith(".json.backup")
        ]
    except OSError:
        auto = []
    auto.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return candidatos + auto


def load_json_safe(filepath: str, default: Any, validate: bool = True) -> Any:
    """
    Carrega um JSON de estado/config sem derrubar o bot.

    PROPÓSITO DE NEGÓCIO:
        config.json (canais das guilds), history.json e state.json (dedup) são a
        memória do bot. Perder um deles em silêncio faz o bot parar de postar
        (config) ou repostar tudo (history/state).

    INVARIANTES DO DOMÍNIO:
        - Arquivo corrompido NUNCA vira padrão enquanto houver backup íntegro:
          tenta o `.backup` de emergência e depois os automáticos (mais recente
          primeiro), e regrava o original a partir do que recuperou.
        - A exceção de parse chega aqui com o tipo original (ver _file_lock).

    COMPORTAMENTO EM CASO DE FALHA:
        Devolve `default` quando o arquivo não existe, está vazio, ou está
        corrompido sem nenhum backup íntegro — sempre com log (WARNING/ERROR)
        dizendo qual dos casos foi. Nunca levanta.
    """
    try:
        if not os.path.exists(filepath):
            log.warning(f"Arquivo '{filepath}' não existe. Usando padrão.")
            return default
        
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            log.warning(f"Arquivo '{filepath}' está vazio. Usando padrão.")
            return default
        
        # Tenta carregar arquivo principal
        try:
            with _file_lock(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            # Validação básica de integridade
            if validate:
                # Testa se pode serializar novamente (valida estrutura)
                json.dumps(data)
            
            return data
            
        except (json.JSONDecodeError, ValueError) as e:
            log.error(f"JSON corrompido em '{filepath}': {e}")
            
            for backup_path in _candidatos_backup(filepath):
                log.warning(f"Tentando recuperar de backup: {backup_path}")
                try:
                    with open(backup_path, "r", encoding="utf-8") as f:
                        backup_data = json.load(f)
                    save_json_safe(filepath, backup_data, atomic=True)
                    log.info(f"✅ Backup restaurado com sucesso: {filepath} <- {backup_path}")
                    return backup_data
                except (OSError, json.JSONDecodeError, ValueError) as backup_error:
                    log.error(f"Falha ao restaurar backup {backup_path}: {backup_error}")
            log.error(f"Nenhum backup íntegro para '{filepath}'. Usando padrão.")
            return default
            
    except Exception as e:
        log.error(f"Falha ao carregar '{filepath}': {e}. Usando padrão.")
        return default


_LOCK_ESPERA_S = 2.0
_LOCK_ORFAO_S = 30.0


@contextmanager
def _file_lock(filepath: str):
    """
    Trava de arquivo por lockfile exclusivo (O_EXCL) ao redor de uma leitura/escrita.

    PROPÓSITO DE NEGÓCIO:
        Bot e vps_api leem e gravam os mesmos JSON no mesmo volume; a trava evita
        que uma gravação intercale com outra.

    INVARIANTES DO DOMÍNIO:
        - Um único `yield`: exceção do corpo propaga com o TIPO ORIGINAL. A versão
          anterior tinha `yield` dentro de `except`, e todo JSONDecodeError virava
          "generator didn't stop after throw()" — o que desviava o load_json_safe
          da recuperação por backup e devolvia histórico VAZIO (repostagem total).
          Medido em 2026-09-26.
        - Só remove o lockfile que ELA criou. A versão anterior apagava o lock de
          outro processo quando não conseguia o seu.
        - Lockfile órfão (processo morto) com mais de _LOCK_ORFAO_S é descartado.

    COMPORTAMENTO EM CASO DE FALHA:
        Sem conseguir a trava em _LOCK_ESPERA_S, segue sem ela com WARNING (a
        escrita atômica por rename continua protegendo contra arquivo truncado).
        Nunca levanta por causa da trava.
    """
    lock_file = filepath + ".lock"
    lock_fd = None
    prazo = time.monotonic() + _LOCK_ESPERA_S
    while lock_fd is None:
        try:
            lock_fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_file) > _LOCK_ORFAO_S:
                    os.remove(lock_file)
                    log.warning(f"Lockfile órfão descartado: {lock_file}")
                    continue
            except OSError:
                continue
            if time.monotonic() >= prazo:
                log.warning(f"Lock ocupado há mais de {_LOCK_ESPERA_S}s, seguindo sem trava: {filepath}")
                break
            time.sleep(0.05)
        except OSError as e:
            log.warning(f"Não foi possível criar lock para {filepath}: {e}")
            break
    try:
        yield
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError as e:
                log.debug(f"Falha ao fechar lock {lock_file}: {e}")
            try:
                os.remove(lock_file)
            except OSError as e:
                log.debug(f"Falha ao remover lock {lock_file}: {e}")


def save_json_safe(filepath: str, data: Any, atomic: bool = True) -> None:
    """
    Salva JSON com indentação de forma segura e atômica.
    
    Para auditoria e compliance:
    - Escrita atômica (temp file + rename) previne corrupção
    - File locking previne race conditions
    - Validação de JSON antes de salvar
    
    Args:
        filepath: Caminho do arquivo JSON
        data: Dados a salvar
        atomic: Se True, usa escrita atômica (temp + rename)
    """
    try:
        # Garante que diretório existe
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        
        # Valida dados antes de serializar
        try:
            json.dumps(data)  # Testa serialização
        except (TypeError, ValueError) as e:
            log.error(f"Dados inválidos para JSON '{filepath}': {e}")
            return
        
        with _file_lock(filepath):
            if atomic:
                # Escrita atômica: escreve em temp file e depois renomeia
                # Isso garante que o arquivo original não é corrompido em caso de interrupção
                temp_dir = os.path.dirname(filepath) or "."
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode='w',
                        encoding='utf-8',
                        dir=temp_dir,
                        delete=False,
                        suffix='.tmp'
                    ) as tmp_file:
                        tmp_path = tmp_file.name
                        json.dump(data, tmp_file, indent=2, ensure_ascii=False)
                        tmp_file.flush()
                        os.fsync(tmp_file.fileno())
                    os.replace(tmp_path, filepath)
                    tmp_path = None
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.remove(tmp_path)
            else:
                # Escrita direta (fallback se atomic falhar)
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
        
        log.debug(f"✅ JSON salvo com sucesso: {filepath}")
        
    except Exception as e:
        log.error(f"Falha ao salvar '{filepath}': {e}")
        # Em caso de erro, tenta backup do arquivo original se existir
        if os.path.exists(filepath):
            backup_path = filepath + ".backup"
            try:
                shutil.copy2(filepath, backup_path)
                log.info(f"Backup criado: {backup_path}")
            except OSError as copy_err:
                log.error(f"Falha ao criar backup de emergência {backup_path}: {copy_err}")
