"""
Filters module - News filtering and categorization logic.
"""
from typing import Dict, List, Any
from utils.html import clean_html


# =========================================================
# FILTROS / CATEGORIAS
# =========================================================

CYBER_CORE = [
    "security", "cyber", "hacker", "malware", "ransomware", "exploit", 
    "vulnerability", "cvss", "zero-day", "breach", "phishing", "ddos", 
    "botnet", "apt", "cve", "infosec", "pentest", "forensics", "patch",
    "incident", "bypass", "rce", "injection", "xss", "sqli", "auth",
    "cisa", "nsa", "fbi", "mitre", "owasp", "nist", "gdpr", "lgpd"
]

BLACKLIST = [
    "casino", "gambling", "dating", "meet singles", 
    "weight loss", "crypto", "bitcoin", "blockchain", "nft", 
    "sale", "deal", "discount", "coupon", "amazon prime"
]

CAT_MAP = {
    "malware": ["malware", "virus", "trojan", "spyware", "backdoor", "rootkit", "worm", "botnet", "command and control", "c2"],
    "ransomware": ["ransomware", "encrypt", "extortion", "lockbit", "clop", "blackcat", "royal", "play", "akira"],
    "vulnerability": ["vulnerability", "bug", "patch", "update", "weakness", "flaw", "cisa", "nist"],
    "cvss": ["cvss", "score", "severity", "critical", "high"],
    "zero-day": ["zero-day", "0-day", "unpatched", "in the wild"],
    "first-day": ["first-day", "1-day", "recently patched"],
    "exploit": ["exploit", "poc", "proof of concept", "attack vector", "rce", "remote code execution"],
    "data breach": ["breach", "leak", "dump", "database", "exposed", "records", "millions"],
    "hacker": ["hacker", "attacker", "threat actor", "apt", "group", "defaced"],
    "security": ["security", "cyber", "infosec", "protection", "defense", "hardening", "policy"],
    "cve": ["cve-", "cve-202", "cve-2024", "cve-2025", "cve-2026"]
}

FILTER_OPTIONS = {
    "todos": ("ALL INTEL", "🌟"),
    "malware": ("Malware", "🦠"),
    "ransomware": ("Ransomware", "🔒"),
    "vulnerability": ("Vulnerability", "🛡️"),
    "exploit": ("Exploit", "💥"),
    "zero-day": ("Zero-Day", "🕵️"),
    "data breach": ("Breach", "📂"),
    "cve": ("CVE", "🆔")
}


# =========================================================
# HELPER FUNCTIONS
# =========================================================

import re

def _contains_any(text: str, keywords: List[str]) -> bool:
    """
    Verifica se alguma keyword está presente no texto usando Regex.
    
    Usa word boundaries (\b) para evitar matches parciais.
    Suporta plural opcional ('s?').
    """
    if not keywords:
        return False

    # Escapa keywords para segurança no regex
    # Monta padrão: (?<!:)\b(?:kw1|kw2|...|kwn)s?\b
    escaped_kws = [re.escape(k) for k in keywords]
    pattern_str = r'(?<!:)\b(?:' + '|'.join(escaped_kws) + r')s?\b'
    
    return bool(re.search(pattern_str, text))


def match_intel(guild_id: str, title: str, summary: str, config: Dict[str, Any]) -> bool:
    """
    Decide se notícia deve ir para a guild.
    
    Lógica:
      1. Exige filtros configurados
      2. Corta blacklist
      3. Exige termos CyberIntel core
      4. "todos" libera tudo
      5. Senão, precisa bater em categoria selecionada
    
    Args:
        guild_id: ID da guild
        title: Título da notícia
        summary: Resumo da notícia
        config: Configuração carregada
    
    Returns:
        True se notícia deve ser postada
    """
    g = config.get(str(guild_id), {})
    filters = g.get("filters", [])

    if not isinstance(filters, list) or not filters:
        return False

    content = f"{clean_html(title)} {clean_html(summary)}".lower()

    # Bloqueia blacklist
    if _contains_any(content, BLACKLIST):
        return False

    # Exige pelo menos um termo Core (menos restritivo para não bloquear genéricos importantes)
    # Mas essencial para evitar notícias de "hacker" em contextos de golfe/jogos não relacionados
    if not _contains_any(content, CYBER_CORE):
        return False

    # "todos" libera tudo
    if "todos" in filters or "all" in filters:
        return True

    # Verifica categorias específicas
    for f in filters:
        kws = CAT_MAP.get(f, [])
        if kws and _contains_any(content, kws):
            return True

    return False
