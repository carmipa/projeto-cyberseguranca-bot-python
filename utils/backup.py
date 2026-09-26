"""
Sistema de Backup Automático para arquivos JSON.
Mantém histórico auditável para compliance e GRC.
"""
import os
import re
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from utils.storage import p, _data_base_dir

log = logging.getLogger("CyberIntel_Backup")

MAX_BACKUPS_PER_FILE = 30  # Mantém últimos 30 backups POR ARQUIVO de origem
BACKUP_RETENTION_DAYS = 90  # Mantém backups por 90 dias


def backup_dir() -> Path:
    """
    Diretório dos backups, resolvido NA CHAMADA dentro do diretório de dados.

    PROPÓSITO DE NEGÓCIO:
        O backup tem de morar onde o estado vive. Antes era "data/backups"
        relativo ao diretório de trabalho do processo: iniciado de outra pasta,
        gravava longe do estado e a limpeza varria uma pasta vazia reportando
        sucesso.

    INVARIANTES DO DOMÍNIO:
        Sempre <DATA_DIR>/backups (ou <projeto>/data/backups sem DATA_DIR).

    COMPORTAMENTO EM CASO DE FALHA:
        Nunca levanta aqui; falha de criação aparece em ensure_backup_dir.
    """
    return Path(_data_base_dir()) / "backups"


def ensure_backup_dir():
    """Garante que diretório de backup existe."""
    backup_path = backup_dir()
    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path


_CARIMBO = re.compile(r"_\d{8}_\d{6}(?:_[^.]*)?\.json\.backup$")


def _origem_do_backup(nome: str) -> str:
    """'config.json_20260926_101010_auto.json.backup' -> 'config.json' (nome com '_' incluído)."""
    return _CARIMBO.sub("", nome)


def create_backup(filepath: str, label: Optional[str] = None) -> Optional[str]:
    """
    Cria backup de um arquivo JSON com timestamp.
    
    Args:
        filepath: Caminho do arquivo a fazer backup
        label: Label opcional para identificar o backup (ex: "pre_update")
    
    Returns:
        Caminho do backup criado ou None se falhar
    """
    try:
        if not os.path.exists(filepath):
            log.warning(f"Arquivo não existe para backup: {filepath}")
            return None
        
        backup_dir = ensure_backup_dir()
        filename = os.path.basename(filepath)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Nome do backup: filename_YYYYMMDD_HHMMSS[_label].json.backup
        backup_name = f"{filename}_{timestamp}"
        if label:
            backup_name += f"_{label}"
        backup_name += ".json.backup"
        
        backup_path = backup_dir / backup_name
        
        # copy, não copy2: o backup precisa da data de CRIAÇÃO. copy2 preservava
        # o mtime do original, e o config.json (que muda raramente) nascia com
        # idade > 90 dias e era apagado pela limpeza no mesmo ciclo — medido na
        # VPS: 1350 avisos, um por varredura, e zero backup de config.json.
        shutil.copy(filepath, backup_path)
        
        log.info(f"✅ Backup criado: {backup_path}")
        return str(backup_path)
        
    except Exception as e:
        log.error(f"Erro ao criar backup de {filepath}: {e}")
        return None


def cleanup_old_backups(filepath: Optional[str] = None):
    """
    Aplica a retenção dos backups: idade máxima e quantidade máxima por arquivo.

    PROPÓSITO DE NEGÓCIO:
        Impedir que os backups encham o disco sem apagar o backup que ainda é
        a única cópia recuperável de um arquivo.

    INVARIANTES DO DOMÍNIO:
        - O teto de MAX_BACKUPS_PER_FILE vale POR ARQUIVO de origem. Antes o teto
          era global: 4 arquivos por varredura dividindo 30 vagas, e o
          database.json (5 MB) empurrava os demais para fora.
        - Cada backup é avaliado e removido no máximo UMA vez (antes, velho E
          excedente era apagado duas vezes e a segunda falhava).
        - O backup mais recente de cada arquivo nunca é removido por idade.

    COMPORTAMENTO EM CASO DE FALHA:
        Erro ao remover um backup é logado e a limpeza segue com os outros.
        Nunca levanta.
    """
    try:
        pasta = ensure_backup_dir()
        now = datetime.now().timestamp()
        padrao = f"{os.path.basename(filepath)}_*.json.backup" if filepath else "*.json.backup"

        grupos = {}
        for b in pasta.glob(padrao):
            grupos.setdefault(_origem_do_backup(b.name), []).append(b)

        removed_count = 0
        for origem, backups in grupos.items():
            backups.sort(key=lambda b: b.stat().st_mtime, reverse=True)
            for posicao, backup_path in enumerate(backups):
                idade = now - backup_path.stat().st_mtime
                velho = posicao > 0 and idade > BACKUP_RETENTION_DAYS * 24 * 3600
                excedente = posicao >= MAX_BACKUPS_PER_FILE
                if not (velho or excedente):
                    continue
                try:
                    backup_path.unlink()
                    removed_count += 1
                except OSError as e:
                    log.warning(f"Erro ao remover backup {backup_path}: {e}")

        if removed_count > 0:
            log.info(f"🧹 Limpeza de backups: {removed_count} arquivos removidos")

    except Exception as e:
        log.error(f"Erro na limpeza de backups: {e}")


def list_backups(filepath: str) -> List[dict]:
    """
    Lista backups disponíveis para um arquivo.
    
    Args:
        filepath: Caminho do arquivo original
    
    Returns:
        Lista de dicts com informações dos backups
    """
    try:
        backup_dir = ensure_backup_dir()
        filename = os.path.basename(filepath)
        backups = list(backup_dir.glob(f"{filename}_*.json.backup"))
        
        backup_info = []
        for backup_path in sorted(backups, key=lambda p: p.stat().st_mtime, reverse=True):
            stat = backup_path.stat()
            backup_info.append({
                "path": str(backup_path),
                "name": backup_path.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "age_days": (datetime.now().timestamp() - stat.st_mtime) / (24 * 3600)
            })
        
        return backup_info
        
    except Exception as e:
        log.error(f"Erro ao listar backups: {e}")
        return []


def restore_backup(filepath: str, backup_path: Optional[str] = None) -> bool:
    """
    Restaura um arquivo de um backup.
    
    Args:
        filepath: Caminho do arquivo a restaurar
        backup_path: Caminho do backup específico. Se None, usa o mais recente.
    
    Returns:
        True se restauração bem-sucedida
    """
    try:
        if backup_path is None:
            # Usa backup mais recente
            backups = list_backups(filepath)
            if not backups:
                log.error(f"Nenhum backup encontrado para {filepath}")
                return False
            backup_path = backups[0]["path"]
        
        if not os.path.exists(backup_path):
            log.error(f"Backup não existe: {backup_path}")
            return False
        
        # Cria backup do arquivo atual antes de restaurar
        create_backup(filepath, label="pre_restore")
        
        # Restaura
        shutil.copy2(backup_path, filepath)
        log.info(f"✅ Arquivo restaurado: {filepath} <- {backup_path}")
        return True
        
    except Exception as e:
        log.error(f"Erro ao restaurar backup: {e}")
        return False


def auto_backup_critical_files():
    """
    Cria backups automáticos dos arquivos críticos do sistema.
    Deve ser chamado periodicamente (ex: antes de operações importantes).
    """
    critical_files = [
        "config.json",
        "state.json",
        "history.json",
        "database.json",
    ]
    
    backed_up = 0
    for filename in critical_files:
        filepath = p(filename)
        if os.path.exists(filepath):
            if create_backup(filepath, label="auto"):
                backed_up += 1
    
    if backed_up > 0:
        log.info(f"📦 Backup automático concluído: {backed_up} arquivos")
    
    # Limpa backups antigos
    cleanup_old_backups()
