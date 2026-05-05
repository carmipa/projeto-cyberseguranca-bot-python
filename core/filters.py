"""
Filters module - News filtering and categorization logic.
"""
from typing import Dict, List, Any, Tuple
import logging
from utils.html import clean_html

log = logging.getLogger("CyberIntel")


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

GUNDAM_WHITELIST = [
    "gundam", "gunpla", "bandai", "sunrise", "mobile suit", "zeon", "newtype",
    "char aznable", "amuro", "gquuuuuuux", "witch from mercury", "seed freedom",
    "rx-78", "mgex", "rg", "hg", "pg", "master grade", "real grade", "perfect grade"
]

GUNDAM_NEGATIVE = [
    "giveaway", "airdrop", "bet", "casino", "gambling", "nft", "crypto",
    "clickbait", "free money", "adult", "dating"
]


# =========================================================
# HELPER FUNCTIONS
# =========================================================

import re

def _contains_any(text: str, keywords: List[str]) -> bool:
    """
    Verifica se alguma keyword está presente no texto usando Regex.
    
    A verificação é feita com "word boundaries" (\\b) para evitar falsos positivos
    em substrings (ex: 'bot' em 'bottle').
    Suporta pluralização simples opcional ('s?').
    
    Args:
        text (str): Texto a ser analisado.
        keywords (List[str]): Lista de palavras-chave.
        
    Returns:
        bool: True se encontrar pelo menos uma correspondência.
    """
    if not keywords:
        return False

    # Escapa keywords para segurança no regex
    # Monta padrão: (?<!:)\b(?:kw1|kw2|...|kwn)s?\b
    escaped_kws = [re.escape(k) for k in keywords]
    pattern_str = r'(?<!:)\b(?:' + '|'.join(escaped_kws) + r')s?\b'
    
    return bool(re.search(pattern_str, text, re.IGNORECASE))


def match_gundam_relevance(
    title: str,
    summary: str,
    source_segment: str = "specialized",
    source_kind: str = "",
    require_title_for_generic_yt: bool = False,
    strict_negative: bool = False,
) -> Tuple[bool, str]:
    """
    Filtro semântico para feeds de Gundam/Gunpla.
    Retorna (aprovado, motivo).
    """
    t = clean_html(title or "").lower()
    s = clean_html(summary or "").lower()
    content = f"{t} {s}".strip()

    if strict_negative and _contains_any(content, GUNDAM_NEGATIVE):
        return False, "negative_keyword"

    has_title_signal = _contains_any(t, GUNDAM_WHITELIST)
    has_content_signal = _contains_any(content, GUNDAM_WHITELIST)

    if source_segment == "generic":
        if source_kind == "youtube" and require_title_for_generic_yt and not has_title_signal:
            return False, "generic_youtube_without_title_signal"
        if not has_content_signal:
            return False, "generic_without_gundam_signal"
        return True, "generic_with_signal"

    # Fonte especializada: permite sinal em título ou resumo
    if has_content_signal:
        return True, "specialized_with_signal"
    return False, "specialized_without_signal"


def match_intel(guild_id: str, title: str, summary: str, config: Dict[str, Any], source_segment: str = "specialized") -> bool:
    """
    Decide se notícia deve ir para a guild.
    
    Lógica:
      1. Exige filtros configurados
      2. Corta blacklist GLOBAL
      3. Corta negative_filters da GUILD (se houver)
      4. Exige termos CyberIntel core
      5. Se for fonte "generic", exige match no TÍTULO (não apenas no resumo)
      6. "todos" libera tudo (ainda respeitando blacklist/negative)
      7. Senão, precisa bater em categoria selecionada
    
    Args:
        guild_id: ID da guild
        title: Título da notícia
        summary: Resumo da notícia
        config: Configuração carregada
        source_segment: Segmento da fonte (specialized/generic)
    
    Returns:
        True se notícia deve ser postada
    """
    g = config.get(str(guild_id), {})
    filters = g.get("filters", [])
    negative_filters = g.get("negative_filters", [])

    if not isinstance(filters, list) or not filters:
        log.debug(f"🛑 [Filtro] Guild {guild_id} sem filtros configurados.")
        return False

    t_clean = clean_html(title).lower()
    s_clean = clean_html(summary).lower()
    content = f"{t_clean} {s_clean}".strip()

    # 1. Bloqueia blacklist GLOBAL
    if _contains_any(content, BLACKLIST):
        log.debug(f"🛑 [Filtro] Conteúdo bloqueado por blacklist GLOBAL: {title[:50]}...")
        return False

    # 2. Bloqueia negative_filters da GUILD
    if negative_filters and _contains_any(content, negative_filters):
        log.debug(f"🛑 [Filtro] Conteúdo bloqueado por negative_filters da guild {guild_id}: {title[:50]}...")
        return False

    # 3. Exige pelo menos um termo Core
    if not _contains_any(content, CYBER_CORE):
        log.debug(f"🛑 [Filtro] Conteúdo ignorado (Sem termos CyberCore): {title[:50]}...")
        return False

    # 4. Se a fonte for GENÉRICA (ex: Google Alerts), exige que o sinal esteja no TÍTULO
    # Isso evita que o Google traga notícias de "culinária" porque mencionaram "segurança alimentar" no resumo.
    if source_segment == "generic":
        if not _contains_any(t_clean, CYBER_CORE):
            log.debug(f"🛑 [Filtro-Genérico] Sinal não encontrado no TÍTULO: {title[:50]}...")
            return False

    # 5. "todos" libera tudo
    if "todos" in filters or "all" in filters:
        return True

    # 6. Verifica categorias específicas
    for f in filters:
        kws = CAT_MAP.get(f, [])
        if kws and _contains_any(content, kws):
            return True

    log.debug(f"🛑 [Filtro] Conteúdo rejeitado (Não bateu com categorias {filters}): {title[:50]}...")
    return False
