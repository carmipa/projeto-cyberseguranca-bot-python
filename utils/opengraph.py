"""
Imagem (e vídeo) de destaque de uma notícia, lida da PÁGINA do artigo.

Substitui o antigo `_extract_media_preview` do scanner, que: buscava a página
uma vez POR GUILD (N requisições por notícia); lia a página inteira sem teto;
não validava o link (SSRF), nem o destino de redirecionamento; e devolvia
og:image relativo ou com entidade HTML (&amp;) direto para o embed — URL que o
Discord recusa com 50035, derrubando a notícia inteira.

Portado do projeto-anime-news (f475c72, 2026-09-18) por duplicação consciente;
aqui sem proxy de saída e com checagem de DNS antes de cada GET.
"""
import asyncio
import logging
from typing import Optional, Tuple
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from utils.security import resolve_para_publico, validate_url

log = logging.getLogger("CyberIntel")

_OG_USER_AGENT = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
_OG_TIMEOUT_S = 8
_MAX_BYTES = 262144
_MAX_REDIRECTS = 1
_STATUS_REDIRECT = (301, 302, 303, 307, 308)


async def fetch_og_media(url: str, session: aiohttp.ClientSession) -> Tuple[Optional[str], Optional[str]]:
    """
    Busca (imagem, vídeo) declarados pela página do artigo.

    PROPÓSITO DE NEGÓCIO:
        Dar ao card do Discord a imagem que identifica a notícia quando o feed
        não a publica.

    INVARIANTES DO DOMÍNIO:
        - INV-IMG-1: nenhuma falha aqui impede a publicação; nunca levanta.
        - INV-IMG-2: todo endereço buscado passou por validate_url E pela
          resolução de DNS para IP público, inclusive o destino do redirect.
        - URL devolvida é absoluta (entidades já decodificadas pelo parser).
        - Parse fora do event loop.

    COMPORTAMENTO EM CASO DE FALHA:
        (None, None) com o motivo em log de debug.
    """
    if not url:
        return None, None
    ok, motivo = validate_url(url)
    if not ok:
        log.debug(f"[OG] URL reprovada: {url[:120]} ({motivo})")
        return None, None
    html_txt, final = await _baixar_html(url.strip(), session)
    if not html_txt:
        return None, None
    try:
        loop = asyncio.get_running_loop()
        bruta_img, bruta_video = await loop.run_in_executor(None, _extrair_midia, html_txt)
    except Exception as e:
        log.debug(f"[OG] Falha ao extrair meta tags de {final}: {type(e).__name__}: {e}")
        return None, None
    return _absoluta(final, bruta_img), _absoluta(final, bruta_video)


def _absoluta(base: str, bruta: Optional[str]) -> Optional[str]:
    if not bruta:
        return None
    # BeautifulSoup já decodificou as entidades do atributo; decodificar de novo
    # corromperia URL legítima que contenha '&amp;' literal.
    absoluta = urljoin(base, bruta.strip())
    if not absoluta.startswith(("http://", "https://")):
        return None
    return absoluta


async def _baixar_html(alvo: str, session: aiohttp.ClientSession) -> Tuple[Optional[str], str]:
    """Baixa até _MAX_BYTES do artigo, seguindo no máximo 1 redirect validado. Nunca levanta."""
    visitados = 0
    while True:
        ok, motivo = await resolve_para_publico(alvo)
        if not ok:
            log.debug(f"[OG] Destino recusado: {alvo[:120]} ({motivo})")
            return None, alvo
        try:
            async with session.get(
                alvo,
                headers={"User-Agent": _OG_USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"},
                timeout=aiohttp.ClientTimeout(total=_OG_TIMEOUT_S),
                allow_redirects=False,
            ) as resp:
                if resp.status in _STATUS_REDIRECT:
                    destino = resp.headers.get("Location", "")
                    if visitados >= _MAX_REDIRECTS or not destino:
                        log.debug(f"[OG] Redirecionamento não seguido ({resp.status}): {alvo}")
                        return None, alvo
                    candidato = urljoin(alvo, destino)
                    ok, motivo = validate_url(candidato)
                    if not ok:
                        log.debug(f"[OG] Redirect reprovado: {candidato[:120]} ({motivo})")
                        return None, alvo
                    alvo = candidato
                    visitados += 1
                    continue
                if resp.status != 200:
                    log.debug(f"[OG] HTTP {resp.status} no artigo: {alvo}")
                    return None, alvo
                bruto = await resp.content.read(_MAX_BYTES)
                return bruto.decode(resp.charset or "utf-8", errors="replace"), alvo
        except asyncio.TimeoutError:
            log.debug(f"[OG] Timeout de {_OG_TIMEOUT_S}s no artigo: {alvo}")
            return None, alvo
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.debug(f"[OG] Falha ao buscar {alvo}: {type(e).__name__}: {e}")
            return None, alvo


def _meta(sopa, *pares) -> Optional[str]:
    for attr, valor in pares:
        tag = sopa.find("meta", attrs={attr: valor})
        if tag and (tag.get("content") or "").strip():
            return tag["content"]
    return None


def _extrair_midia(html_txt: str) -> Tuple[Optional[str], Optional[str]]:
    """
    (imagem, vídeo) das meta tags. SÍNCRONA: roda no executor.

    Ordem da imagem: og:image > og:image:secure_url > twitter:image > itemprop
    image > link rel=image_src. A primeira presente e não vazia ganha.
    """
    sopa = BeautifulSoup(html_txt, "html.parser")
    imagem = _meta(
        sopa,
        ("property", "og:image"), ("name", "og:image"), ("property", "og:image:secure_url"),
        ("name", "twitter:image"), ("property", "twitter:image"), ("name", "twitter:image:src"),
        ("itemprop", "image"),
    )
    if not imagem:
        ls = sopa.find("link", rel="image_src")
        if ls and (ls.get("href") or "").strip():
            imagem = ls["href"]
    video = _meta(sopa, ("property", "og:video:secure_url"), ("property", "og:video:url"), ("property", "og:video"))
    return imagem, video
