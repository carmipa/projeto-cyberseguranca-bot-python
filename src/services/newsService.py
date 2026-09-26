import asyncio
import logging
from typing import Dict, List

import aiohttp
import feedparser

log = logging.getLogger("CyberIntel")

FEEDS = (
    "https://feeds.feedburner.com/TheHackersNews",
    "https://www.bleepingcomputer.com/feed/",
)
_TIMEOUT_S = 15


async def get_latest_security_news(itens_por_feed: int = 3) -> List[Dict[str, str]]:
    """
    Últimas notícias de duas fontes fixas, para o /news e o monitor rápido.

    PROPÓSITO DE NEGÓCIO: resposta imediata ao /news sem esperar a varredura.

    INVARIANTES DO DOMÍNIO:
        - Rede pelo aiohttp com teto de tempo; parse no executor. Antes era
          `feedparser.parse(url)`: download SÍNCRONO e sem timeout dentro do
          event loop — fonte lenta congelava o bot inteiro (heartbeat do gateway).
        - Só http(s) no link devolvido.

    COMPORTAMENTO EM CASO DE FALHA: fonte que falha é logada com o motivo e
    pulada; devolve lista (possivelmente vazia). Nunca levanta.
    """
    news_list: List[Dict[str, str]] = []
    loop = asyncio.get_running_loop()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=_TIMEOUT_S)) as session:
        for url in FEEDS:
            try:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0 CyberIntelBot"}) as resp:
                    if resp.status != 200:
                        log.warning(f"newsService: {url} respondeu {resp.status}")
                        continue
                    texto = await resp.text(errors="ignore")
                feed = await loop.run_in_executor(None, feedparser.parse, texto)
                for entry in feed.entries[:itens_por_feed]:
                    link = str(entry.get("link") or "")
                    if not link.startswith(("http://", "https://")):
                        continue
                    resumo = str(entry.get("description") or "Sem resumo disponível.")
                    news_list.append({
                        "title": str(entry.get("title") or "Sem título"),
                        "link": link,
                        "summary": resumo[:200] + ("..." if len(resumo) > 200 else ""),
                    })
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning(f"newsService: erro ao ler {url}: {type(e).__name__}: {e}")
    return news_list
