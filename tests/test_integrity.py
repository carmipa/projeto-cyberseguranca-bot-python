def test_imports():
    """Importa os módulos que já quebraram o arranque (cveService sem Optional, 2026-02)."""
    from core.scanner import load_history, load_sources  # noqa: F401
    from src.services.cveService import fetch_nvd_cves, get_cve_details  # noqa: F401
    from src.services.threatService import ThreatService  # noqa: F401
    from bot.cogs.info import InfoCog  # noqa: F401
