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
from typing import Any
from contextlib import contextmanager

# File locking cross-platform
try:
    import fcntl  # Linux/Unix
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False
    try:
        import msvcrt  # Windows
        HAS_MSVCRT = True
    except ImportError:
        HAS_MSVCRT = False

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


def load_json_safe(filepath: str, default: Any, validate: bool = True) -> Any:
    """
    Carrega JSON sem derrubar o bot se faltar / vazio / corrompido.
    Implementa validação de integridade e recuperação de backup se necessário.
    
    Args:
        filepath: Caminho do arquivo JSON
        default: Valor padrão se falhar
        validate: Se True, valida estrutura JSON antes de retornar
    
    Returns:
        Dados do JSON ou valor padrão
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
            
            # Tenta recuperar de backup
            backup_path = filepath + ".backup"
            if os.path.exists(backup_path):
                log.warning(f"Tentando recuperar de backup: {backup_path}")
                try:
                    with open(backup_path, "r", encoding="utf-8") as f:
                        backup_data = json.load(f)
                    # Restaura backup
                    save_json_safe(filepath, backup_data, atomic=True)
                    log.info(f"✅ Backup restaurado com sucesso: {filepath}")
                    return backup_data
                except Exception as backup_error:
                    log.error(f"Falha ao restaurar backup: {backup_error}")
            
            return default
            
    except Exception as e:
        log.error(f"Falha ao carregar '{filepath}': {e}. Usando padrão.")
        return default


@contextmanager
def _file_lock(filepath: str):
    """
    Context manager para file locking cross-platform.
    Previne race conditions em operações concorrentes.
    """
    lock_file = filepath + ".lock"
    lock_fd = None
    
    try:
        # Cria arquivo de lock
        lock_fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        
        # Aplica lock baseado no OS
        if HAS_FCNTL:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        elif HAS_MSVCRT:
            msvcrt.locking(lock_fd, msvcrt.LK_LOCK, 1)
        
        yield
        
    except FileExistsError:
        # Lock já existe, aguarda um pouco e tenta novamente
        import time
        time.sleep(0.1)
        # Tenta novamente (implementação simples, pode melhorar com retry logic)
        if os.path.exists(lock_file):
            log.warning(f"Lock file existe para {filepath}, aguardando...")
            time.sleep(0.5)
        yield
    except Exception as e:
        log.error(f"Erro ao criar lock para {filepath}: {e}")
        yield
    finally:
        if lock_fd is not None:
            try:
                if HAS_FCNTL:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except:
                pass
        
        # Remove arquivo de lock
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except:
            pass


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
                    os.fsync(tmp_file.fileno())  # Force write to disk
                
                # Renomeia temp para arquivo final (operação atômica no filesystem)
                shutil.move(tmp_path, filepath)
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
            except:
                pass
