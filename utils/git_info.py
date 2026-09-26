import logging
import subprocess

log = logging.getLogger("CyberIntel")


def _git(*args: str) -> str:
    """Roda git sem shell (lista de argumentos). Levanta em falha; quem chama trata."""
    return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL, timeout=5).decode("utf-8").strip()  # nosec B603 B607 - argumentos fixos


def get_git_changes() -> str:
    """'hash - mensagem' do último commit, ou texto fixo se não houver git (a imagem Docker não leva .git)."""
    try:
        return _git("log", "-1", "--pretty=format:%h - %s")
    except Exception as e:
        log.debug(f"Git info indisponível: {e}")
        return "Maintenance Update (No Git Info)"


def get_current_hash():
    """Hash curto do HEAD, ou None sem git."""
    try:
        return _git("log", "-1", "--pretty=format:%h") or None
    except Exception as e:
        log.debug(f"Hash do git indisponível: {e}")
        return None
