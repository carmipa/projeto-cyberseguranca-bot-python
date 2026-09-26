"""
HTML utilities - Text cleaning functions.
"""
import re


# Compiled regex patterns for performance
_HTML_RE = re.compile(r"<.*?>|&([a-z0-9]+|#[0-9]{1,6});", flags=re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "utm_viz_id", "utm_pubreferrer",
    "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src", "mkt_tok",
}


def clean_html(raw_html: str) -> str:
    """
    Remove tags HTML e entidades; normaliza espaços.
    """
    if not raw_html:
        return ""
    
    # Remove tags HTML e entidades
    txt = re.sub(_HTML_RE, " ", raw_html)
    
    # Normaliza múltiplos espaços em um só
    txt = re.sub(_WS_RE, " ", txt).strip()
    
    return txt


def safe_discord_url(raw: str) -> str | None:
    """
    Sanitiza e encurta URLs para evitar o limite de 512 caracteres do Discord.
    
    Args:
        raw: URL bruta
    
    Returns:
        URL limpa e encurtada ou None se exceder o limite após limpeza.
    """
    if not raw:
        return None

    url = raw.strip()
    if len(url) <= 512:
        return url

    try:
        p_url = urlparse(url)
        # 1) Remove fragmento (#...)
        p_url = p_url._replace(fragment="")

        # 2) Remove parâmetros de rastreamento (UTM, etc)
        q = [(k, v) for k, v in parse_qsl(p_url.query, keep_blank_values=True)
             if k.lower() not in TRACKING_KEYS]
        url_no_track = urlunparse((p_url.scheme, p_url.netloc, p_url.path, p_url.params, urlencode(q, doseq=True), ""))
        
        if len(url_no_track) <= 512:
            return url_no_track

        # 3) Remove toda a query string se ainda estiver grande
        url_no_query = urlunparse((p_url.scheme, p_url.netloc, p_url.path, p_url.params, "", ""))
        if len(url_no_query) <= 512:
            return url_no_query

        # 4) Ainda grande? Não cria componente para evitar crash 400
        return None
    except ValueError:
        return None
