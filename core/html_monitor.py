"""
HTML Monitor - detecta mudança em sites oficiais sem RSS.

Até 2026-09-26 lia a chave `official_sites_reference_(not_rss)`, que NÃO EXISTE
no catálogo: retornava vazio de imediato e o scanner anunciava "Verificando
sites oficiais" a cada varredura sem verificar nada. Agora lê `official_sites`
e distingue os três estados: nao_configurado, verificado e falha.
"""
import asyncio
import hashlib
import logging
import random
import ssl
from typing import Dict, List, Tuple

import aiohttp
import certifi
from bs4 import BeautifulSoup

from app.settings import BROWSER_USER_AGENTS
from utils.security import resolve_para_publico, validate_url
from utils.storage import catalog_path, load_json_safe

log = logging.getLogger("CyberIntel")

ESTADO_NAO_CONFIGURADO = "nao_configurado"
ESTADO_VERIFICADO = "verificado"
ESTADO_FALHA = "falha"

IGNORE_TAGS = ['script', 'style', 'meta', 'noscript', 'iframe', 'svg']
IGNORE_SELECTORS = ['.ad', '.advertisement', '.widget', '#clock', '.timestamp', '.cookie-consent']
_MAX_BYTES = 2 * 1024 * 1024


def _hash_da_pagina(content: str) -> Tuple[str, str]:
    """(título, sha256 do texto limpo). SÍNCRONA: roda no executor (BeautifulSoup é CPU-bound)."""
    soup = BeautifulSoup(content, 'html.parser')
    for tag in soup(IGNORE_TAGS):
        tag.decompose()
    for selector in IGNORE_SELECTORS:
        for match in soup.select(selector):
            match.decompose()
    text_content = soup.get_text(separator=' ', strip=True)
    title = soup.title.string.strip() if soup.title and soup.title.string else "Sem título"
    return title, hashlib.sha256(text_content.encode('utf-8')).hexdigest()


async def fetch_page_hash(session: aiohttp.ClientSession, url: str) -> Tuple[str, str, str]:
    """(url, título, hash) da página; ("", "") no título/hash em qualquer falha, com motivo logado."""
    try:
        ok, motivo = await resolve_para_publico(url)
        if not ok:
            log.warning(f"HTML Monitor: {url} recusado ({motivo})")
            return url, "", ""
        # Sem seguir redirecionamento: o destino não passaria pela checagem de
        # SSRF, e o título da página seria publicado em todas as guilds.
        async with session.get(url, allow_redirects=False) as resp:
            if resp.status != 200:
                log.warning(f"HTML Monitor: {url} respondeu {resp.status}")
                return url, "", ""
            content = (await resp.content.read(_MAX_BYTES)).decode(resp.charset or "utf-8", errors="ignore")
        loop = asyncio.get_running_loop()
        title, page_hash = await loop.run_in_executor(None, _hash_da_pagina, content)
        return url, title, page_hash
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.warning(f"HTML Monitor: falha ao buscar {url}: {type(e).__name__}: {e}")
        return url, "", ""


def urls_monitoradas() -> List[str]:
    """URLs de `official_sites` do catálogo (itens com enabled:false ficam de fora)."""
    sources = load_json_safe(catalog_path("sources.json"), {})
    itens = sources.get("official_sites", []) if isinstance(sources, dict) else []
    urls = []
    for item in itens if isinstance(itens, list) else []:
        if isinstance(item, str):
            url = item
        elif isinstance(item, dict) and item.get("enabled", True) is not False:
            url = item.get("url") or ""
        else:
            continue
        if validate_url(url)[0]:
            urls.append(url.strip())
    return urls


async def check_official_sites(current_state: Dict[str, str]) -> Tuple[List[Dict[str, str]], Dict[str, str], str]:
    """
    Verifica mudança nos sites oficiais do catálogo.

    PROPÓSITO DE NEGÓCIO:
        Avisar quando uma página institucional sem RSS muda de conteúdo.

    INVARIANTES DO DOMÍNIO:
        - "Não achei mudança" (verificado) e "não tinha como achar"
          (nao_configurado / falha) são estados diferentes e devolvidos à parte.
        - Primeira leitura de uma URL só registra o hash, nunca alerta.
        - Parse fora do event loop.

    COMPORTAMENTO EM CASO DE FALHA:
        Nunca levanta. Devolve ([], estado_atual, ESTADO_FALHA) se nenhuma URL
        pôde ser lida; URLs que falharem mantêm o hash anterior.
    """
    urls = urls_monitoradas()
    if not urls:
        return [], current_state, ESTADO_NAO_CONFIGURADO

    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    headers = {
        "User-Agent": random.choice(BROWSER_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    updates: List[Dict[str, str]] = []
    new_state = dict(current_state)
    lidas = 0
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_ctx),
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        results = await asyncio.gather(*(fetch_page_hash(session, u) for u in urls))
    for url, title, page_hash in results:
        if not page_hash:
            continue
        lidas += 1
        last_hash = current_state.get(url)
        if not last_hash:
            new_state[url] = page_hash
            log.info(f"HTML Monitor: hash inicial registrado para {url}")
            continue
        if page_hash != last_hash:
            log.info(f"HTML Monitor: MUDANÇA detectada em {url}")
            updates.append({"title": f"🔄 Update: {title}", "link": url})
            new_state[url] = page_hash
    return updates, new_state, (ESTADO_VERIFICADO if lidas else ESTADO_FALHA)
