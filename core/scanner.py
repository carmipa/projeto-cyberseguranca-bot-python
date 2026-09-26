"""
Scanner module - Feed fetching and processing logic.
"""
import math
import ssl
import socket
import asyncio
import html as html_mod
import logging
import re
import feedparser
import aiohttp
import certifi
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple, Dict, Any
from urllib.parse import urljoin, urlparse, urlunparse
import time
import random
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from dateutil import parser as dtparser

import discord
from discord.ext import tasks

from app.settings import (
    LOOP_MINUTES,
    NODE_RED_ENDPOINT,
    BROWSER_USER_AGENTS,
    FEED_FETCH_MAX_RETRIES,
    FEED_FETCH_RETRY_BASE_DELAY,
    FEED_FETCH_RETRY_MAX_DELAY_MS,
    FEED_FETCH_TIMEOUT_MS,
    FEED_FETCH_JITTER_MIN,
    FEED_FETCH_JITTER_MAX,
    FEED_CACHE_ENABLED,
    DEDUP_HISTORY_TTL_HOURS,
    GUNDAM_STRICT_MODE,
    GUNDAM_REQUIRE_IN_TITLE_FOR_GENERIC_YT,
    NEGATIVE_KEYWORDS_STRICT,
    MAX_CONCURRENT_FEEDS,
)
CONNECTIVITY_CHECK_HOST = "1.1.1.1" # Mudado para Cloudflare (8.8.8.8 estava podendo ser bloqueado)
CONNECTIVITY_CHECK_PORT = 53
CONNECTIVITY_CHECK_TIMEOUT = 3

from utils.storage import p, catalog_path, load_json_safe, save_json_safe
from utils.html import clean_html, safe_discord_url
from utils.cache import get_cache_headers, update_cache_state
from utils.heartbeat import bater
from utils.opengraph import fetch_og_media
from utils.security import imagem_publicavel, validate_url
from core.stats import stats
from core.filters import match_intel, match_gundam_relevance
from core.html_monitor import ESTADO_NAO_CONFIGURADO, check_official_sites
from core.telemetria import VEREDITO_ANOMALIA, VEREDITO_ATENCAO, avaliar_varredura, metricas_vazias
from src.services.cveService import fetch_nvd_cves
from src.services.dbService import mark_news_as_sent
from src.services.threatService import ThreatService
from bot.views.share_buttons import ShareButtons

log = logging.getLogger("CyberIntel")

# Lock global para impedir varreduras simultâneas
scan_lock = asyncio.Lock()


# =========================================================
# HISTORY MANAGEMENT
# =========================================================

def load_history() -> Tuple[List[str], Set[str]]:
    """Carrega history.json e devolve (lista, set) para dedupe rápido."""
    h = load_json_safe(p("history.json"), [])
    if not isinstance(h, list):
        log.warning("history.json inválido. Reiniciando histórico.")
        h = []
    
    # Filtra apenas strings para evitar erros
    h = [x for x in h if isinstance(x, str)]
    return h, set(h)


def save_history(history_list: List[str], limit: int = 2000) -> bool:
    """Mantém histórico limitado para não crescer infinito. True se gravou."""
    return save_json_safe(p("history.json"), history_list[-limit:])


def _persistir(state: Dict[str, Any], history_list: List[str]) -> bool:
    """Grava history e state. SÍNCRONA (disco): no event loop, via asyncio.to_thread."""
    ok_h = save_history(history_list)
    ok_s = save_json_safe(p("state.json"), state, atomic=True)
    return ok_h and ok_s


def _estado_conectado(bot: Any) -> Optional[bool]:
    """True/False se o bot expõe o estado da conexão; None se desconhecido (bot de teste)."""
    try:
        if bot.is_closed() or not bot.is_ready():
            return False
        # is_ready não volta a False numa queda de gateway (discord.py 2.x só o
        # limpa no close); latência infinita = sem heartbeat = desconectado.
        return math.isfinite(float(bot.latency))
    except Exception:
        return None


# =========================================================
# SOURCE MANAGEMENT
# =========================================================

def load_sources() -> List[str]:
    """
    Carrega feeds de sources.json.
    Retorna lista única de URLs http(s).
    """
    sources_raw = load_json_safe(catalog_path("sources.json"), [])
    urls: List[str] = []

    def _add(u: Any):
        if isinstance(u, str):
            u = u.strip()
            if u.startswith(("http://", "https://")):
                urls.append(u)

    if isinstance(sources_raw, dict):
        # Inclui 'apis' na lista de chaves, embora APIs sejam tratadas separadamente no scanner
        # Aqui pegamos apenas URLs de feeds RSS/Atom/YouTube
        for key in ("rss_feeds", "youtube_feeds", "official_sites", "feeds", "sources", "urls"):
            val = sources_raw.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        _add(item)
                    elif isinstance(item, dict) and item.get("enabled", True) is not False:
                        _add(item.get("url") or item.get("link"))
            elif isinstance(val, dict):
                # Suporta o novo formato aninhado (ex: {"critical_priority": [...], "high_priority": [...]})
                for sub_key, sub_val in val.items():
                    if isinstance(sub_val, list):
                        for item in sub_val:
                            if isinstance(item, str):
                                _add(item)
                            elif isinstance(item, dict) and item.get("enabled", True) is not False:
                                _add(item.get("url") or item.get("link"))

    elif isinstance(sources_raw, list):
        for item in sources_raw:
            if isinstance(item, str):
                _add(item)
            elif isinstance(item, dict):
                _add(item.get("url") or item.get("link"))

    # remove duplicados mantendo ordem
    seen = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def impressao_do_catalogo() -> Dict[str, Any]:
    """
    Impressão digital do catálogo em uso: caminho, sha256 (16), bytes e fontes ativas.

    PROPÓSITO DE NEGÓCIO: provar no log de arranque QUAL sources.json o bot está
    lendo. O volume `./data:/app/data` sombreava o catálogo da imagem e ninguém
    via; com a impressão, catálogo velho, ausente ou vazio aparece no primeiro
    minuto.

    INVARIANTES DO DOMÍNIO: consulta o mesmo caminho e o mesmo load_sources da
    produção (não reimplementa o critério).

    COMPORTAMENTO EM CASO DE FALHA: nunca levanta; arquivo ausente devolve
    sha="" e bytes=0.
    """
    import hashlib
    import os
    caminho = catalog_path("sources.json")
    try:
        with open(caminho, "rb") as f:
            bruto = f.read()
    except OSError:
        bruto = b""
    return {
        "caminho": caminho,
        "sha": hashlib.sha256(bruto).hexdigest()[:16] if bruto else "",
        "bytes": len(bruto),
        "fontes": len(load_sources()) if bruto else 0,
        "existe": os.path.exists(caminho),
    }


def load_sources_meta() -> Dict[str, Dict[str, str]]:
    """
    Carrega metadados de sources.json (name/category/priority) indexados por URL de feed.
    Isso permite ajustar severidade visual com base na origem (Exploit, Gov, Regulatório, etc.).
    """
    data = load_json_safe(catalog_path("sources.json"), {})
    index: Dict[str, Dict[str, str]] = {}

    if isinstance(data, dict):
        for key in ("rss_feeds", "youtube_feeds", "official_sites"):
            val = data.get(key)
            
            # Função auxiliar para processar itens
            def _process_item(item, list_key):
                if isinstance(item, dict):
                    url = item.get("url") or item.get("link")
                    if isinstance(url, str):
                        name = str(item.get("name", ""))
                        category = str(item.get("category", ""))
                        source_kind = "youtube" if list_key == "youtube_feeds" else "rss"
                        lower_hint = f"{name} {category}".lower()
                        segment = "specialized"
                        if any(x in lower_hint for x in ("google news", "reddit", "news", "aggregator", "general")):
                            segment = "generic"

                        index[url] = {
                            "name": name,
                            "category": category,
                            "priority": item.get("priority", "Medium"),
                            "segment": item.get("segment", segment),
                            "source_kind": item.get("source_kind", source_kind),
                            "max_posts_per_scan": item.get("max_posts_per_scan", 0),
                        }

            if isinstance(val, list):
                for item in val:
                    _process_item(item, key)
            elif isinstance(val, dict):
                # Novo formato aninhado
                for sub_key, sub_val in val.items():
                    if isinstance(sub_val, list):
                        for item in sub_val:
                            _process_item(item, key)
    return index

# utils/html.py handle link sanitization
def sanitize_link(link: str) -> str:
    """
    Remove parâmetros de rastreamento (utm_, etc) para evitar duplicação no histórico.
    Mantém parâmetros úteis (id, v, article).
    """
    try:
        parsed = urlparse(link)
        # Se for YouTube, não mexe na query string (pode quebrar v=...)
        if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
            return link
            
        # Filtra query params
        q_pairs = parsed.query.split('&')
        cleaned_pairs = [
            pair for pair in q_pairs 
            if not pair.startswith(('utm_', 'ref', 'source', 'fbclid', 'timestamp'))
            and pair # remove vazios
        ]
        new_query = '&'.join(cleaned_pairs)
        
        final_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        # Discord Hard Limit: URLs em botões/links não podem exceder 512 caracteres
        if len(final_url) > 512:
            return final_url.split('?')[0][:512]
            
        return final_url
    except ValueError as e:
        log.debug(f"sanitize_link: URL malformada mantida como veio: {link[:120]} ({e})")
        return link[:512] if len(link) > 512 else link

def parse_entry_dt(entry: Any) -> datetime:
    """
    Tenta extrair a data de publicação de forma robusta.
    Retorna datetime (com tzinfo se possível) ou None.
    Aceita tanto objeto feedparser (getattr) quanto dict (get).
    """
    try:
        # Tenta string de data primeiro (ISO 8601, RFC822, etc).
        if isinstance(entry, dict):
            s = (
                entry.get("published")
                or entry.get("updated")
                or entry.get("created")
                or entry.get("dc:date")
            )
        else:
            s = (
                getattr(entry, "published", None)
                or getattr(entry, "updated", None)
                or getattr(entry, "created", None)
            )

        if s:
            raw = str(s)
            try:
                return dtparser.parse(raw)
            except Exception:
                # Fallback para formatos RFC2822 que alguns feeds retornam.
                return parsedate_to_datetime(raw)
    except Exception:
        pass

    # Fallback para struct_time do feedparser (funciona tanto para dict quanto objeto).
    try:
        if isinstance(entry, dict):
            st = entry.get("published_parsed") or entry.get("updated_parsed")
        else:
            st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if st:
            return datetime(*st[:6], tzinfo=timezone.utc)
    except Exception:
        pass

    return None


def _format_human_delta_pt(delta: timedelta) -> str:
    total_seconds = max(0, int(delta.total_seconds()))
    if total_seconds < 60:
        return "agora"
    if total_seconds < 3600:
        mins = total_seconds // 60
        return f"há {mins} minuto{'s' if mins != 1 else ''}"
    if total_seconds < 86400:
        hours = total_seconds // 3600
        return f"há {hours} hora{'s' if hours != 1 else ''}"
    days = total_seconds // 86400
    return f"há {days} dia{'s' if days != 1 else ''}"


def _format_posted_at(entry_dt: datetime) -> str:
    weekdays = [
        "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"
    ]
    months = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
    ]

    dt_utc = entry_dt.astimezone(timezone.utc) if entry_dt.tzinfo else entry_dt.replace(tzinfo=timezone.utc)
    # Mantém BRT fixo (UTC-3) para padronizar visual no Discord.
    dt_local = dt_utc.astimezone(timezone(timedelta(hours=-3)))
    now_utc = datetime.now(timezone.utc)
    rel = _format_human_delta_pt(now_utc - dt_utc)
    weekday_local = weekdays[dt_local.weekday()]
    month_local = months[dt_local.month - 1]
    return (
        f"Postado em: {dt_utc:%d/%m/%Y %H:%M} (UTC) · "
        f"{weekday_local}, {dt_local.day} de {month_local} de {dt_local.year} {dt_local:%H:%M} · {rel}"
    )


# =========================================================
# IMAGEM DA NOTÍCIA
# =========================================================

# Tokens de imagem de enfeite, casados como TOKEN delimitado (nunca substring:
# "comiconline.jpg" contém "icon" e é imagem legítima). Portado do anime-news.
_IMG_TOKENS_DESCARTAVEIS = frozenset({
    "pixel", "spacer", "blank", "tracking", "transparent", "1x1",
    "gravatar", "avatar", "emoji", "emojis", "icon", "icons",
    "badge", "button", "share", "feedburner", "doubleclick",
})
_IMG_ATTR_ORDEM = ("src", "data-src", "data-lazy-src", "data-original", "data-srcset", "srcset")
MEDIA_DOMAINS = ("youtube.com", "youtu.be", "twitch.tv")


def _campo(entry: Any, nome: str, padrao: Any = None) -> Any:
    """Lê um campo de entrada de feed (FeedParserDict ou dict das APIs) sem levantar."""
    try:
        if isinstance(entry, dict):
            return entry.get(nome, padrao)
        return getattr(entry, nome, padrao)
    except Exception:
        return padrao


def _img_candidata(tag: str) -> str:
    """
    URL utilizável de UMA tag <img>, ou "" se ela é enfeite.

    PROPÓSITO DE NEGÓCIO: separar a foto do artigo do pixel de rastreio, do
    ícone de compartilhar e do avatar que vêm no mesmo HTML do feed.

    INVARIANTES DO DOMÍNIO: primeiro atributo UTILIZÁVEL (lazy-load: o src é
    placeholder data: e a imagem real está em data-src); width/height <= 2 é
    pixel; data: nunca serve.

    COMPORTAMENTO EM CASO DE FALHA: devolve "". Nunca levanta.
    """
    bruto = ""
    for attr in _IMG_ATTR_ORDEM:
        m = re.search(rf'\b{attr}\s*=\s*["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if not m:
            continue
        candidato = m.group(1).strip()
        if "," in candidato and " " in candidato.split(",")[0].strip():
            candidato = candidato.split(",")[0].strip().split()[0]
        if not candidato or candidato.lower().startswith("data:"):
            continue
        bruto = candidato
        break
    if not bruto:
        return ""
    for dim in ("width", "height"):
        m = re.search(rf'\b{dim}\s*=\s*["\']?(\d+)', tag, re.IGNORECASE)
        if m and int(m.group(1)) <= 2:
            return ""
    tokens = {t for t in re.split(r"[/\-_.?=&]+", bruto.lower()) if t}
    if tokens & _IMG_TOKENS_DESCARTAVEIS:
        return ""
    return bruto


def extrair_imagem_do_feed(entry: Any, link: str, summary: str) -> str:
    """
    Imagem que a própria FONTE publicou no feed.

    PROPÓSITO DE NEGÓCIO: a imagem declarada no feed é a mais confiável e não
    custa requisição.

    INVARIANTES DO DOMÍNIO: ordem fixa — media_thumbnail, media_content de
    imagem, enclosure de imagem, primeira <img> servível do summary/content.
    Relativa é resolvida contra o link; entidade HTML é decodificada. Sem rede.

    COMPORTAMENTO EM CASO DE FALHA: devolve "" quando o feed não traz imagem.
    Nunca levanta.
    """
    for campo in ("media_thumbnail", "media_content"):
        itens = _campo(entry, campo)
        if isinstance(itens, list):
            for item in itens:
                if not isinstance(item, dict):
                    continue
                ctype = (item.get("type") or "").lower()
                medium = (item.get("medium") or "").lower()
                if campo == "media_content" and ctype and "image" not in ctype and medium != "image":
                    continue
                url = (item.get("url") or "").strip()
                if url:
                    return urljoin(link, html_mod.unescape(url))
    links = _campo(entry, "links")
    if isinstance(links, list):
        for item in links:
            if not isinstance(item, dict):
                continue
            if (item.get("rel") or "") == "enclosure" and "image" in (item.get("type") or "").lower():
                href = (item.get("href") or "").strip()
                if href:
                    return urljoin(link, html_mod.unescape(href))
    blob = summary or ""
    conteudo = _campo(entry, "content")
    if isinstance(conteudo, list):
        blob += " " + " ".join(c.get("value", "") for c in conteudo if isinstance(c, dict))
    for tag in re.findall(r"<img[^>]*>", blob, re.IGNORECASE):
        src = _img_candidata(tag)
        if src:
            if src.startswith("//"):
                src = "https:" + src
            return urljoin(link, html_mod.unescape(src))
    return ""


async def resolver_midia(entry: Any, link: str, summary: str, session: aiohttp.ClientSession) -> Tuple[str, str]:
    """
    (imagem, vídeo) da notícia: feed primeiro, página do artigo depois.

    PROPÓSITO DE NEGÓCIO: fontes que não publicam imagem no feed publicam
    og:image no artigo; sem o segundo passo a notícia sai sem imagem.

    INVARIANTES DO DOMÍNIO:
        - O FEED TEM PRECEDÊNCIA; OpenGraph só quando o feed não trouxe nada.
        - Chamada UMA vez por notícia, nunca por guild (antes: 1 GET por guild).
        - Mídia (YouTube/Twitch) não chega aqui: sai pelo player nativo.

    COMPORTAMENTO EM CASO DE FALHA: devolve ("", "") ou só o que obteve.
    Nunca levanta e nunca bloqueia a publicação (INV-IMG-1).
    """
    imagem = extrair_imagem_do_feed(entry, link, summary)
    if imagem:
        return imagem, ""
    try:
        og_img, og_video = await fetch_og_media(link, session)
    except Exception as e:
        log.debug(f"[IMG] OpenGraph falhou para {link[:80]}: {type(e).__name__}: {e}")
        og_img, og_video = None, None
    return og_img or "", og_video or ""


def build_news_embed(
    bot_user: Any,
    *,
    titulo: str,
    resumo: str,
    link: str,
    embed_color: discord.Color,
    author_prefix: str,
    entry_dt: Optional[datetime],
    imagem: str,
    video: str,
) -> Tuple[discord.Embed, bool]:
    """
    Monta o embed de uma notícia textual, sem enviar (função pura, testável).

    PROPÓSITO DE NEGÓCIO: o card que o servidor lê — título, resumo, data,
    fonte e a imagem da notícia em tamanho grande (set_image), como nos bots
    irmãos desde 2026-09-18.

    INVARIANTES DO DOMÍNIO:
        - Imagem só entra depois de imagem_publicavel: URL inválida recusaria o
          embed INTEIRO (50035) e a notícia nunca sairia.
        - Limites do Discord respeitados: título 256, descrição 4096, campo 1024.
        - Vídeo só como campo, e só URL que passa validate_url.

    COMPORTAMENTO EM CASO DE FALHA: nunca levanta; devolve (embed, True) quando
    havia imagem e ela foi descartada, para o chamador logar o motivo.
    """
    embed = discord.Embed(
        title=titulo[:256],
        description=resumo[:4096],
        url=link,
        color=embed_color,
        timestamp=datetime.now(timezone.utc),
    )
    icon_url = bot_user.avatar.url if bot_user and getattr(bot_user, "avatar", None) else None
    embed.set_author(name=author_prefix, icon_url=icon_url)
    effective_dt = entry_dt or datetime.now(timezone.utc)
    embed.add_field(name="🕒 Publicação", value=_format_posted_at(effective_dt)[:1024], inline=False)
    embed.set_footer(text=f"Fonte: {urlparse(link).netloc} • CyberIntel SOC")

    imagem_ok = imagem_publicavel(imagem)
    if imagem_ok:
        embed.set_image(url=imagem_ok)
    if video and validate_url(video)[0] and len(video) <= 1024:
        embed.add_field(name="🎬 Vídeo detectado", value=video, inline=False)
    return embed, bool(imagem) and not imagem_ok


def classify_severity(title: str, link: str, feed_url: str, source_meta: Dict[str, Dict[str, str]]) -> Tuple[discord.Color, str, bool]:
    """
    Define severidade visual (cor, prefixo e flag crítico) combinando:
    - prioridade/categoria do feed em sources.json
    - palavras-chave no título
    - domínio do link (ex: NVD)
    """
    meta = source_meta.get(feed_url, {})
    priority = str(meta.get("priority", "Medium")).lower()
    category = str(meta.get("category", "")).lower()
    name = str(meta.get("name", "")).lower()

    title_lower = title.lower()
    link_lower = link.lower()

    # Defaults
    embed_color = discord.Color.from_rgb(0, 255, 204)  # Cyan Default
    author_prefix = "🛡️ Intel Update"
    is_critical = False

    # Fonte crítica por natureza (Exploit, Ransomware, Vulnerability Intel, Regulatory)
    if "exploit" in category or "poc" in category or "ransomware" in category:
        priority = "critical"
    if "regulatory" in category or "government" in category:
        # Regulatório é alto impacto para GRC, mas não necessariamente incidente técnico
        if priority not in ("high", "critical"):
            priority = "high"

    # Heurísticas por conteúdo
    if any(word in title_lower for word in ("ransomware", "double extortion", "data leak", "data breach")):
        is_critical = True

    if any(word in title_lower for word in ("zero-day", "0-day", "exploit", "remote code execution", "rce")):
        is_critical = True

    # NVD / CVE explícito
    if "nvd.nist.gov" in link_lower or "cve-" in title_lower:
        # Se vier de Exploit-DB/ZDI/CVE feeds, trata como alta
        if any(src in name for src in ("exploit-db", "zero day initiative", "zdi", "cve details")):
            is_critical = True

    # Marcações manuais (ex: título já com 🚨)
    if "🚨" in title:
        is_critical = True

    # Aplica regras finais
    if is_critical:
        embed_color = discord.Color.from_rgb(255, 0, 0)  # Red
        author_prefix = "🚨 CRITICAL ALERT"
    elif priority in ("high", "critical"):
        embed_color = discord.Color.from_rgb(255, 140, 0)  # Orange
        if "regulatory" in category or "anpd" in name or "enisa" in name:
            author_prefix = "📜 REGULATORY UPDATE"
        elif "exploit" in category or "vulnerability" in category:
            author_prefix = "⚠️ HIGH RISK"
        else:
            author_prefix = "⚠️ PRIORITY INTEL"
    elif "regulatory" in category or "anpd" in name or "enisa" in name:
        embed_color = discord.Color.from_rgb(0, 153, 255)  # Blue
        author_prefix = "📜 REGULATORY UPDATE"

    return embed_color, author_prefix, is_critical


# =========================================================
# SCANNER LOGIC
# =========================================================

def _log_next_run() -> None:
    """Log explícito do próximo horário de varredura."""
    nxt = datetime.now() + timedelta(minutes=LOOP_MINUTES)
    log.info(f"⏳ Aguardando próxima varredura às {nxt:%Y-%m-%d %H:%M:%S} (em {LOOP_MINUTES} min)...")


def _check_connectivity_sync() -> bool:
    """Tenta conexão TCP com Google DNS (8.8.8.8:53). Timeout 3s. Uso em executor."""
    sock = None
    try:
        sock = socket.create_connection(
            (CONNECTIVITY_CHECK_HOST, CONNECTIVITY_CHECK_PORT),
            timeout=CONNECTIVITY_CHECK_TIMEOUT,
        )
        return True
    except (socket.error, OSError):
        return False
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass


async def check_network_connectivity() -> bool:
    """
    Verifica conectividade de rede antes da varredura.
    Conexão rápida com Google DNS (8.8.8.8:53), timeout 3s.
    Retorna True se ok, False se indisponível.
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _check_connectivity_sync),
            timeout=CONNECTIVITY_CHECK_TIMEOUT + 1,
        )
    except asyncio.TimeoutError:
        return False


DESFECHO_OK = "ok"
DESFECHO_NAO_MODIFICADO = "nao_modificado"
DESFECHO_VAZIO = "vazio"
DESFECHO_FALHA = "falha"

IDADE_MAXIMA_DIAS = 7
# O dedup precisa durar MAIS que a janela de idade: com TTL de 168h e corte em
# `.days > 7`, item de 7 dias e algumas horas saía do dedup ainda dentro da
# janela e era repostado (reproduzido na revisão de boa-fé de 26/09; o código
# antigo tinha o mesmo defeito). Margem de 2 dias.
TTL_DEDUP_S = max(DEDUP_HISTORY_TTL_HOURS * 3600, (IDADE_MAXIMA_DIAS + 2) * 86400)
FALHAS_TRANSITORIAS_POR_GUILD = 3
MAX_SEM_DATA_VISTOS = 5000
MAX_SCAN_DURATION = 14 * 60
NODE_RED_PAUSA_S = 6 * 3600
PAUSA_ENTRE_ENVIOS_S = 2.5  # anti-flag de spam do Discord

FALHA_GUILD = "guild"
FALHA_ITEM = "item"
FALHA_TRANSITORIA = "transitoria"
# Códigos do Discord que significam "esta guild não aceita": Missing Access,
# Missing Permissions, Unknown Channel. Um 403 SEM esses códigos (borda,
# Cloudflare) é transitório.
_CODIGOS_RECUSA_DA_GUILD = {50001, 50013, 10003}


def classificar_falha_de_envio(e: Exception) -> str:
    """
    Decide de quem é a falha de um channel.send.

    PROPÓSITO DE NEGÓCIO: punir o culpado certo. Guild sem permissão não pode
    travar as outras; conteúdo recusado não pode apagar a entrega de todas; falha
    de rede tem de ser retentada.

    INVARIANTES DO DOMÍNIO: recusa da guild só com código do Discord
    (50001/50013/10003); 4xx restante = item; 5xx, 429 esgotado, rede e o
    resto = transitória.

    COMPORTAMENTO EM CASO DE FALHA: nunca levanta; desconhecido = transitória
    (retentar é o lado seguro: a pendência vence pelo TTL).
    """
    status = getattr(e, "status", None)
    codigo = getattr(e, "code", None)
    if isinstance(e, discord.HTTPException) and codigo in _CODIGOS_RECUSA_DA_GUILD:
        return FALHA_GUILD
    if isinstance(status, int) and 400 <= status < 500 and status not in (403, 404, 408, 429):
        return FALHA_ITEM
    return FALHA_TRANSITORIA
_node_red_pausado_ate = 0.0


@dataclass
class FeedResultado:
    """
    Desfecho do download de UMA fonte.

    Antes, 304, não-200, timeout, exceção e "200 sem entradas" devolviam todos
    `None` e eram indistinguíveis; fonte morta parecia dia sem notícia.
    `resp_headers` viaja com o resultado e só vira cache depois da entrega.
    """
    url: str
    desfecho: str
    entradas: List[Any] = field(default_factory=list)
    motivo: str = ""
    resp_headers: Optional[Dict[str, str]] = None
    api: bool = False
    titulo: str = ""


def _cabecalhos_de_cache(headers: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for nome in ("ETag", "Last-Modified"):
        valor = headers.get(nome) if headers is not None else None
        if valor:
            out[nome] = valor
    return out


def _prune_history_with_ttl(state: Dict[str, Any], history_list: List[str], history_set: Set[str]) -> None:
    """Remove do dedup os links vistos há mais de DEDUP_HISTORY_TTL_HOURS e as entregas pendentes vencidas."""
    ttl_seconds = TTL_DEDUP_S
    now_ts = time.time()
    history_seen_at = state.setdefault("history_seen_at", {})
    stale = {
        link for link, ts in history_seen_at.items()
        if isinstance(ts, (int, float)) and (now_ts - ts) > ttl_seconds
    }
    if stale:
        for link in stale:
            history_seen_at.pop(link, None)
        history_set.difference_update(stale)
        history_list[:] = [h for h in history_list if h not in stale]
        if isinstance(state.get("dedup"), dict):
            for feed_key, items in state["dedup"].items():
                if isinstance(items, list):
                    state["dedup"][feed_key] = [x for x in items if x not in stale]
        log.info("🧹 dedup.ttl_prune removed=%d ttl_hours=%d", len(stale), DEDUP_HISTORY_TTL_HOURS)
    pendentes = state.setdefault("pendentes", {})
    vencidos = [
        link for link, p_ in pendentes.items()
        if not isinstance(p_, dict) or (now_ts - float(p_.get("desde", 0) or 0)) > ttl_seconds
    ]
    for link in vencidos:
        # Consolida como tratado: sem isto o link, fora do history e do dedup,
        # voltaria a ser "novo" e — sem data confiável — seria repostado a quem
        # já tinha recebido (achado da revisão adversarial de 26/09).
        log.warning(f"⌛ Entrega pendente abandonada após {TTL_DEDUP_S // 3600}h e registrada como tratada: {link}")
        pendentes.pop(link, None)
        if link not in history_set:
            history_set.add(link)
            history_list.append(link)
        history_seen_at[link] = now_ts
        state.setdefault("sem_data_vistos", []).append(link)


async def _push_node_red(session: aiohttp.ClientSession, payload: Dict[str, Any]) -> None:
    """
    Empurra o alerta ao Node-RED. Acessório: nunca afeta a entrega ao Discord.

    Com endpoint ausente (404), pausa por NODE_RED_PAUSA_S e avisa UMA vez — o
    comportamento anterior avisava a cada varredura (747 WARNING em produção).
    """
    global _node_red_pausado_ate
    if time.time() < _node_red_pausado_ate:
        return
    try:
        async with session.post(NODE_RED_ENDPOINT, json=payload, timeout=aiohttp.ClientTimeout(total=3)) as nr_resp:
            if nr_resp.status == 404:
                _node_red_pausado_ate = time.time() + NODE_RED_PAUSA_S
                log.warning(
                    "⚠️ Node-RED sem o fluxo /cyber-intel (404) em %s. Push pausado por %dh.",
                    NODE_RED_ENDPOINT, NODE_RED_PAUSA_S // 3600,
                )
            elif nr_resp.status >= 400:
                log.warning(f"⚠️ Node-RED retornou {nr_resp.status}")
    except asyncio.CancelledError:
        raise
    except Exception as nr_e:
        log.warning(f"⚠️ Falha ao enviar para Node-RED: {type(nr_e).__name__}: {nr_e}")


def _emitir_veredito(state: Dict[str, Any], m: Dict[str, int], abortada: str, trigger: str) -> Dict[str, Any]:
    """
    Fecha a varredura: veredito com motivo, persistido e logado como manchete.

    Chamado em TODO caminho de saída, inclusive os `return` antecipados (sem
    guild, sem catálogo, sem rede) — que são justamente os cenários que o
    veredito existe para nomear.
    """
    meta = state.setdefault("_meta", {})
    agora = time.time()
    if m.get("enviadas", 0) > 0 or not isinstance(meta.get("ultimo_envio_ts"), (int, float)):
        meta["ultimo_envio_ts"] = agora
    horas = (agora - meta["ultimo_envio_ts"]) / 3600
    resultado = avaliar_varredura(m, horas_sem_envio=horas, abortada=abortada, loop_minutes=LOOP_MINUTES)
    resultado["trigger"] = trigger
    meta["ultimo_veredito"] = resultado
    texto = f"🩺 scan.veredito {resultado['veredito']} trigger={trigger} :: " + " | ".join(resultado["motivos"])
    if resultado["veredito"] == VEREDITO_ANOMALIA:
        log.error(texto)
    elif resultado["veredito"] == VEREDITO_ATENCAO:
        log.warning(texto)
    else:
        log.info(texto)
    return resultado


async def run_scan_once(bot: discord.Client, trigger: str = "manual", bypass_cache: bool = False) -> None:
    """
    Executa um ciclo completo de varredura de inteligência.

    PROPÓSITO DE NEGÓCIO:
        Buscar as fontes do catálogo e as APIs (NVD, OTX), filtrar por guild e
        publicar cada notícia nova UMA vez em cada servidor configurado.

    INVARIANTES DO DOMÍNIO:
        - INV-ENTREGA-1: link só vira "entregue" (dedup/history) quando TODAS as
          guilds-alvo receberam; guild que falhou fica em `pendentes` e só ela é
          retentada — a que recebeu não recebe de novo.
        - INV-ENTREGA-2: cache HTTP (ETag/Last-Modified) de um feed só é gravado
          depois de o feed inteiro ser percorrido SEM falha de entrega e sem
          interrupção; senão o 304 seguinte esconderia a notícia para sempre.
        - INV-ENTREGA-3: fonte nova (partida a frio) obedece ao mesmo filtro de
          idade; item sem data na partida a frio é só registrado. Antes a
          partida a frio publicava o histórico inteiro do feed.
        - Modo bypass (/post_latest) publica NO MÁXIMO uma notícia.
        - Uma varredura por vez (scan_lock); veredito emitido em todo caminho.

    COMPORTAMENTO EM CASO DE FALHA:
        Nunca propaga exceção de fonte ou de envio: cada uma vira desfecho com
        motivo, contador e veredito. Exceção inesperada no meio ainda salva o
        estado (o que já foi entregue continua deduplicado) e o batimento.
    """
    if scan_lock.locked():
        log.info(f"⏭️ Varredura ignorada (já existe uma em execução). Trigger: {trigger}")
        return
    async with scan_lock:
        await _executar_varredura(bot, trigger, bypass_cache)


async def _executar_varredura(bot: discord.Client, trigger: str, bypass_cache: bool) -> None:
    from utils.state_cleanup import check_and_cleanup_state

    inicio = time.time()
    m = metricas_vazias()
    abortada = ""
    log.info(
        "🔎 scan.start trigger=%s bypass=%s loop_minutes=%s max_concurrency=%s",
        trigger, bypass_cache, LOOP_MINUTES, MAX_CONCURRENT_FEEDS,
    )

    config = load_json_safe(p("config.json"), {})
    if not isinstance(config, dict):
        config = {}
    guilds = {
        gid: gdata for gid, gdata in config.items()
        if isinstance(gdata, dict) and isinstance(gdata.get("channel_id"), int)
    }
    m["guilds_configuradas"] = len(guilds)
    urls = load_sources()
    m["fontes_total"] = len(urls)
    state = check_and_cleanup_state(force=False)
    history_list, history_set = load_history()
    veredito: Dict[str, Any] = {}
    try:
        if not _persistir(state, history_list):
            # Falha FECHADA: sem conseguir gravar o dedup, cada envio seria
            # repostado na varredura seguinte. A sonda é o PRÓPRIO estado (mesmo
            # tamanho): um arquivo de 30 bytes passava com o disco quase cheio e
            # o state.json falhava só depois do envio (2ª revisão, 26/09).
            m["persistencia_falhou"] = 1
            abortada = "diretório de dados não gravável — envios suspensos para não repostar"
        elif not guilds:
            abortada = "nenhuma guild com channel_id (use /set_channel)"
        elif not urls:
            abortada = "catálogo sem fontes válidas"
        elif not await check_network_connectivity():
            abortada = "rede indisponível"
        else:
            await _varrer(bot, trigger, bypass_cache, guilds, urls, state, history_list, history_set, m, inicio)
    finally:
        if not m["persistencia_falhou"] and not _persistir(state, history_list):
            m["persistencia_falhou"] = 1
        veredito = _emitir_veredito(state, m, abortada, trigger)
        _persistir(state, history_list)
        bater(veredito.get("veredito", ""), conectado=_estado_conectado(bot))
        try:
            from utils.backup import auto_backup_critical_files
            auto_backup_critical_files()
        except Exception as backup_error:
            log.warning(f"Falha no backup automático: {backup_error}")
        stats.scans_completed += 1
        stats.news_posted += m["enviadas"]
        stats.feeds_failed += m["fontes_falha"]
        stats.cache_hits_total += m["fontes_304"]
        stats.last_scan_time = datetime.now()
        stats.ultimo_veredito = veredito
        log.info(
            "✅ scan.done sent=%s falhas_entrega=%s fontes_ok=%s fontes_304=%s fontes_falha=%s fontes_vazias=%s total_feeds=%s trigger=%s",
            m["enviadas"], m["falhas_entrega"], m["fontes_ok"], m["fontes_304"],
            m["fontes_falha"], m["fontes_vazias"], m["fontes_total"], trigger,
        )
        if trigger == "loop":
            _log_next_run()


async def _baixar_feed(session, url, semaphore, use_cache, http_cache, source_meta) -> FeedResultado:
    """Baixa e interpreta UM feed. Nunca levanta (exceto cancelamento): todo desfecho vira FeedResultado."""
    def _retry_delay(attempt_index: int) -> float:
        base = FEED_FETCH_RETRY_BASE_DELAY * (2 ** attempt_index)
        jitter = random.uniform(0.0, FEED_FETCH_RETRY_BASE_DELAY)
        return min(base + jitter, max(1.0, FEED_FETCH_RETRY_MAX_DELAY_MS / 1000.0))

    nome = str(source_meta.get(url, {}).get("name", "")).strip() or urlparse(url).netloc
    async with semaphore:
        await asyncio.sleep(random.uniform(FEED_FETCH_JITTER_MIN, FEED_FETCH_JITTER_MAX))
        cache_headers = get_cache_headers(url, http_cache) if use_cache else {}
        request_headers = {**cache_headers, "User-Agent": random.choice(BROWSER_USER_AGENTS)}
        ultimo_motivo = ""
        for attempt in range(FEED_FETCH_MAX_RETRIES):
            try:
                async with session.get(url, headers=request_headers) as resp:
                    if resp.status == 304:
                        return FeedResultado(url, DESFECHO_NAO_MODIFICADO)
                    if resp.status in _STATUS_TRANSITORIOS:
                        ultimo_motivo = f"HTTP {resp.status}"
                        if attempt < FEED_FETCH_MAX_RETRIES - 1:
                            delay = _retry_delay(attempt)
                            log.warning("♻️ feed.retry url=%s status=%s attempt=%s/%s delay=%.2fs",
                                        url, resp.status, attempt + 1, FEED_FETCH_MAX_RETRIES, delay)
                            await asyncio.sleep(delay)
                            continue
                        return FeedResultado(url, DESFECHO_FALHA, motivo=f"{ultimo_motivo} após {FEED_FETCH_MAX_RETRIES} tentativas")
                    if resp.status != 200:
                        return FeedResultado(url, DESFECHO_FALHA, motivo=f"HTTP {resp.status}")
                    text = await resp.text(errors="ignore")
                    headers = _cabecalhos_de_cache(resp.headers)
                loop = asyncio.get_running_loop()
                feed = await loop.run_in_executor(None, feedparser.parse, text)
                entries = list(getattr(feed, "entries", []) or [])
                if not entries:
                    bozo = getattr(feed, "bozo_exception", None)
                    motivo = f"200 sem entradas ({type(bozo).__name__}: {bozo})" if bozo else "200 sem entradas"
                    return FeedResultado(url, DESFECHO_VAZIO, motivo=motivo[:200])
                titulo_feed = str(getattr(feed, "feed", {}).get("title", "") or "")
                return FeedResultado(url, DESFECHO_OK, entries, resp_headers=headers, titulo=titulo_feed)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                ultimo_motivo = f"{type(e).__name__}: {e}"[:200]
                if attempt < FEED_FETCH_MAX_RETRIES - 1:
                    delay = _retry_delay(attempt)
                    log.warning("♻️ feed.error_retry source=%s url=%s attempt=%s/%s delay=%.2fs err=%s",
                                nome, url, attempt + 1, FEED_FETCH_MAX_RETRIES, delay, type(e).__name__)
                    await asyncio.sleep(delay)
                    continue
                return FeedResultado(url, DESFECHO_FALHA, motivo=ultimo_motivo)
        return FeedResultado(url, DESFECHO_FALHA, motivo=ultimo_motivo or "sem tentativa")


_STATUS_TRANSITORIOS = (408, 409, 425, 429, 500, 502, 503, 504)


async def _varrer(bot, trigger, bypass_cache, guilds, urls, state, history_list, history_set, m, inicio) -> None:
    source_meta = load_sources_meta()
    state.setdefault("dedup", {})
    http_cache = state.setdefault("http_cache", {})
    state.setdefault("html_hashes", {})
    pendentes = state.setdefault("pendentes", {})
    _prune_history_with_ttl(state, history_list, history_set)
    sem_data_vistos = state.setdefault("sem_data_vistos", [])
    sem_data_set = set(sem_data_vistos)

    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    base_headers = {
        "User-Agent": random.choice(BROWSER_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    timeout = aiohttp.ClientTimeout(total=max(2, int(FEED_FETCH_TIMEOUT_MS / 1000)))
    use_cache = FEED_CACHE_ENABLED and not bypass_cache
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FEEDS)
    canais_invisiveis: Set[str] = set()
    falhas_por_guild: Dict[str, int] = {}
    guilds_recusadas: Set[str] = set()

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_ctx), headers=base_headers, timeout=timeout
    ) as session:
        brutos = await asyncio.gather(
            *(_baixar_feed(session, u, semaphore, use_cache, http_cache, source_meta) for u in urls),
            return_exceptions=True,
        )
        results: List[FeedResultado] = []
        for u, r in zip(urls, brutos):
            if isinstance(r, BaseException):
                if isinstance(r, asyncio.CancelledError):
                    raise r
                results.append(FeedResultado(u, DESFECHO_FALHA, motivo=f"{type(r).__name__}: {r}"[:200]))
            else:
                results.append(r)

        for r in results:
            chave = {DESFECHO_OK: "fontes_ok", DESFECHO_NAO_MODIFICADO: "fontes_304",
                     DESFECHO_VAZIO: "fontes_vazias", DESFECHO_FALHA: "fontes_falha"}[r.desfecho]
            m[chave] += 1
            if r.desfecho in (DESFECHO_FALHA, DESFECHO_VAZIO):
                log.warning("⚠️ feed.%s source=%s url=%s motivo=%s", r.desfecho,
                            source_meta.get(r.url, {}).get("name", ""), r.url, r.motivo)

        try:
            cve_entries = await fetch_nvd_cves()
            if cve_entries:
                log.info(f"🔎 Encontradas {len(cve_entries)} vulnerabilidades CVSS >= 7 (NVD).")
                results.append(FeedResultado("api://nvd", DESFECHO_OK, cve_entries, api=True))
        except Exception as e:
            log.exception(f"❌ Falha ao buscar CVEs: {e}")
        try:
            otx_pulses = await ThreatService.get_otx_pulses()
            if otx_pulses:
                log.info(f"🛸 Encontrados {len(otx_pulses)} pulses do AlienVault OTX.")
                formatados = [{
                    "title": f"🚨 OTX: {pp.get('name', 'Unknown Threat')}",
                    "link": f"https://otx.alienvault.com/pulse/{pp.get('id')}",
                    "summary": f"**Threat:** {pp.get('threat_hunter_scanner', 'Unknown')}\n\n{str(pp.get('description') or 'Sem descrição.')[:500]}",
                    "published": pp.get("created"),
                } for pp in otx_pulses if pp.get("id")]
                results.append(FeedResultado("api://otx", DESFECHO_OK, formatados, api=True))
        except Exception as e:
            log.exception(f"❌ Falha ao buscar OTX Pulses: {e}")

        for r in results:
            if r.desfecho != DESFECHO_OK:
                continue
            if (time.time() - inicio) > MAX_SCAN_DURATION:
                log.warning("🛑 Tempo limite do scan alcançado (>14min); feeds restantes ficam para o próximo ciclo sem cache gravado.")
                break
            if m["persistencia_falhou"]:
                log.error("🛑 Estado não gravável no meio da varredura: envios interrompidos para não repostar.")
                break
            falhas_feed, interrompido = await _processar_feed(
                bot, r, guilds, state, history_list, history_set, sem_data_set, sem_data_vistos,
                pendentes, source_meta, session, bypass_cache, m, inicio, canais_invisiveis,
                falhas_por_guild, guilds_recusadas,
            )
            if r.resp_headers and use_cache and falhas_feed == 0 and not interrompido:
                update_cache_state(r.url, r.resp_headers, http_cache)
            elif r.resp_headers and use_cache:
                log.info(f"📦 Cache NÃO gravado para {r.url}: falhas_entrega={falhas_feed} interrompido={interrompido}")
            if bypass_cache and (m["enviadas"] > 0 or m["falhas_entrega"] > 0 or interrompido):
                break

    if len(sem_data_vistos) > MAX_SEM_DATA_VISTOS:
        del sem_data_vistos[: len(sem_data_vistos) - MAX_SEM_DATA_VISTOS]
    m["canais_nao_resolvidos"] = len(canais_invisiveis)
    m["canais_sem_permissao"] = len(guilds_recusadas)
    # Troca de lado DECLARADA: guild que recusa (403/404) não recebe depois o
    # que perdeu — retentar travava o cache de todos e repostava às demais.
    # O dono vê no veredito; o admin da guild, no /forcecheck.
    state.setdefault("_meta", {})["guilds_sem_permissao"] = sorted(guilds_recusadas)

    await _rodar_html_monitor(bot, guilds, state)


async def _processar_feed(bot, r, guilds, state, history_list, history_set, sem_data_set, sem_data_vistos,
                          pendentes, source_meta, session, bypass_cache, m, inicio, canais_invisiveis,
                          falhas_por_guild, guilds_recusadas) -> Tuple[int, bool]:
    """Percorre as entradas de UM feed. Devolve (falhas_de_entrega, interrompido)."""
    url = r.url
    is_cold_start = url not in state["dedup"]
    if is_cold_start:
        log.info(f"❄️ [Cold Start] {url}: filtro de idade mantido; itens sem data só são registrados.")
        state["dedup"][url] = []
    feed_meta = source_meta.get(url, {})
    source_segment = str(feed_meta.get("segment", "specialized"))
    source_kind = str(feed_meta.get("source_kind", "rss"))
    try:
        max_posts_per_scan = int(feed_meta.get("max_posts_per_scan", 0) or 0)
    except (TypeError, ValueError):
        max_posts_per_scan = 0
    feed_posted = 0
    falhas_feed = 0

    for entry in r.entradas:
        link = str(_campo(entry, "link") or "").strip()
        title = str(_campo(entry, "title") or "")
        summary = str(_campo(entry, "summary") or _campo(entry, "description") or "")
        if not link:
            continue
        if not r.api:
            link = urljoin(url, link.replace(" ", "%20"))
        link = sanitize_link(link)
        if not validate_url(link)[0]:
            # Link vai para embed.url e para o botão: inválido recusaria a
            # MENSAGEM INTEIRA (50035) em todas as guilds (revisão de 26/09).
            m["itens_link_invalido"] += 1
            log.warning(f"⚠️ Item com link inválido ignorado ({url}): {link[:150]}")
            continue
        m["itens_examinados"] += 1
        pend = pendentes.get(link) if not bypass_cache else None
        if not bypass_cache and pend is None:
            if link in state["dedup"].get(url, []) or link in history_set or link in sem_data_set:
                continue
        if (time.time() - inicio) > MAX_SCAN_DURATION:
            return falhas_feed, True
        if max_posts_per_scan > 0 and feed_posted >= max_posts_per_scan:
            log.info("⏭️ feed.max_posts_reached url=%s limit=%s", url, max_posts_per_scan)
            return falhas_feed, True

        entry_dt = parse_entry_dt(entry)
        data_confiavel = False
        if entry_dt:
            now = datetime.now(entry_dt.tzinfo) if entry_dt.tzinfo else datetime.now()
            if (now - entry_dt) > timedelta(days=IDADE_MAXIMA_DIAS):
                continue
            # Data no FUTURO (evento agendado, medido no Dark Reading em
            # 26/09/2026: item de dezembro) não prova idade: sem este corte ele
            # passaria no filtro e voltaria a cada TTL do history até a data.
            data_confiavel = entry_dt <= now + timedelta(days=1)
        if not data_confiavel:
            m["itens_sem_data"] += 1
            if is_cold_start and not bypass_cache:
                sem_data_set.add(link)
                sem_data_vistos.append(link)
                continue

        t_clean = clean_html(title).strip()
        s_clean = clean_html(summary).strip()[:2000]
        if GUNDAM_STRICT_MODE:
            ok_rel, reason = match_gundam_relevance(
                title=t_clean, summary=s_clean, source_segment=source_segment, source_kind=source_kind,
                require_title_for_generic_yt=GUNDAM_REQUIRE_IN_TITLE_FOR_GENERIC_YT,
                strict_negative=NEGATIVE_KEYWORDS_STRICT,
            )
            if not ok_rel:
                continue

        ja_entregues = list(pend.get("guilds_ok", [])) if isinstance(pend, dict) else []
        falhou_disjuntor = False
        alvo_invisivel = False
        recusadas_previas: List[str] = []
        alvos = []
        for gid, gdata in guilds.items():
            if gid in ja_entregues:
                continue
            if not match_intel(str(gid), title, summary, {gid: gdata}, source_segment):
                continue
            if gid in guilds_recusadas:
                # Já recusou (403/404) nesta varredura: não gastar outra chamada.
                recusadas_previas.append(gid)
                continue
            if falhas_por_guild.get(gid, 0) >= FALHAS_TRANSITORIAS_POR_GUILD:
                # Disjuntor: guild falhando nesta varredura não consome o tempo
                # das outras (2,5s por tentativa, teto de 14 min por varredura).
                falhou_disjuntor = True
                continue
            channel = bot.get_channel(gdata["channel_id"])
            if channel is None:
                canais_invisiveis.add(str(gid))
                alvo_invisivel = True
                continue
            alvos.append((gid, channel))
        if not alvos and recusadas_previas and not falhou_disjuntor:
            alvos_vazios_por_recusa = True
        else:
            alvos_vazios_por_recusa = False
        if not alvos and not alvos_vazios_por_recusa:
            if falhou_disjuntor:
                pendentes.setdefault(link, {"guilds_ok": ja_entregues, "desde": time.time(), "feed": url})
                falhas_feed += 1
            elif pend is not None and alvo_invisivel:
                # Canal momentaneamente invisível (reidentificação, guild
                # indisponível): mantém a pendência; ela vence pelo TTL.
                pass
            elif pend is not None:
                # As guilds que faltavam saíram (canal sumiu, filtro mudou): o que
                # já foi entregue vira entregue de vez. Só descartar a pendência
                # reabria o link e repostava para quem já tinha recebido
                # (reproduzido na revisão operacional de 26/09).
                pendentes.pop(link, None)
                state["dedup"][url].append(link)
                history_set.add(link)
                history_list.append(link)
                state.setdefault("history_seen_at", {})[link] = time.time()
                if not data_confiavel:
                    sem_data_set.add(link)
                    sem_data_vistos.append(link)
            continue

        embed_color, author_prefix, is_critical = classify_severity(title, link, url, source_meta)
        is_media = any(d in link for d in MEDIA_DOMAINS)
        final_link = safe_discord_url(link)
        embed = None
        if not is_media:
            imagem, video = await resolver_midia(entry, link, summary, session)
            embed, descartada = build_news_embed(
                bot.user, titulo=t_clean, resumo=s_clean, link=link, embed_color=embed_color,
                author_prefix=author_prefix, entry_dt=entry_dt, imagem=imagem, video=video,
            )
            if descartada:
                log.warning(f"⚠️ [EMBED] Imagem descartada por URL inválida, notícia segue sem ela: {imagem[:120]}")
            if not final_link:
                embed.description = (embed.description or "")[:3800] + f"\n\n🔗 **Link Original:** {link[:250]}"

        entregues_agora = []
        item_envenenado = False
        recusadas = list(recusadas_previas)
        falhou = False
        for gid, channel in alvos:
            try:
                view = ShareButtons(t_clean[:100], final_link or link, is_critical=is_critical)
                if is_media:
                    await channel.send(content=f"📺 **{t_clean[:256]}**\n{final_link or link}"[:2000], view=view)
                else:
                    await channel.send(embed=embed, view=view)
                entregues_agora.append(gid)
                m["enviadas"] += 1
                log.info(f"✨ [Enviado] guild={gid}: {t_clean[:60]}")
            except asyncio.CancelledError:
                raise
            except discord.HTTPException as e:
                tipo = classificar_falha_de_envio(e)
                codigo = getattr(e, "code", "")
                if tipo == FALHA_GUILD:
                    # Sem permissão / canal apagado (códigos do Discord, nunca um
                    # 403 genérico de borda): retentar não resolve e a pendência
                    # travaria o cache de todos. Vira sinal de configuração.
                    recusadas.append(gid)
                    guilds_recusadas.add(gid)
                    log.error(f"❌ Guild {gid} recusou o envio ({type(e).__name__} {codigo}): verifique a permissão do bot no canal {channel.id}"[:500])
                elif tipo == FALHA_ITEM:
                    # O Discord recusou o CONTEÚDO (4xx, ex. 50035): falha igual
                    # em toda guild; não é culpa da guild e não pode disparar o
                    # disjuntor dela (2ª revisão adversarial: 3 itens ruins
                    # apagavam a entrega de todas).
                    item_envenenado = True
                    log.error(f"❌ Discord recusou o conteúdo do item (HTTP {getattr(e, 'status', '?')} {codigo}); item descartado: {link[:150]} :: {e}"[:600])
                    break
                else:
                    falhou = True
                    m["falhas_entrega"] += 1
                    falhas_por_guild[gid] = falhas_por_guild.get(gid, 0) + 1
                    log.error(f"❌ Falha transitória ao enviar para guild {gid} canal {channel.id}: {type(e).__name__} {codigo} {e}"[:500])
            except Exception as e:
                falhou = True
                m["falhas_entrega"] += 1
                falhas_por_guild[gid] = falhas_por_guild.get(gid, 0) + 1
                codigo = getattr(e, "code", "")
                log.error(f"❌ Falha transitória ao enviar para guild {gid} canal {channel.id}: {type(e).__name__} {codigo} {e}"[:500])
            await asyncio.sleep(PAUSA_ENTRE_ENVIOS_S)

        entregues = ja_entregues + entregues_agora
        if item_envenenado:
            m["itens_recusados_discord"] += 1
            pendentes.pop(link, None)
            state["dedup"][url].append(link)
            history_set.add(link)
            history_list.append(link)
            state.setdefault("history_seen_at", {})[link] = time.time()
            sem_data_set.add(link)
            sem_data_vistos.append(link)
            continue
        falhou = falhou or falhou_disjuntor
        if falhou and bypass_cache:
            # /post_latest nunca cria pendência: senão, com os canais quebrados,
            # enfileiraria o feed inteiro e tudo sairia de novo depois (revisão
            # de boa-fé de 26/09). Uma tentativa e para.
            return falhas_feed + 1, True
        if falhou:
            falhas_feed += 1
            pendentes[link] = {
                "guilds_ok": entregues,
                "desde": (pend or {}).get("desde", time.time()) if isinstance(pend, dict) else time.time(),
                "feed": url,
            }
        else:
            pendentes.pop(link, None)
        if entregues_agora:
            feed_posted += 1
        if (entregues or recusadas) and not falhou:
            state["dedup"][url].append(link)
            if not data_confiavel:
                sem_data_set.add(link)
                sem_data_vistos.append(link)
            history_set.add(link)
            history_list.append(link)
            state.setdefault("history_seen_at", {})[link] = time.time()
        if entregues_agora or pend is not None:
            # Gravar a CADA notícia entregue: `docker stop` mata o processo e o
            # `finally` da varredura não roda; o que saiu seria repostado.
            if not await asyncio.to_thread(_persistir, state, history_list):
                m["persistencia_falhou"] = 1
                log.error("🛑 Falha ao gravar o estado após envio: varredura interrompida para não repostar.")
                return falhas_feed, True
        if entregues_agora:
            try:
                await asyncio.to_thread(mark_news_as_sent, link, title, summary)
            except Exception as db_e:
                log.warning(f"⚠️ Falha ao gravar no database.json: {db_e}")
            await _push_node_red(session, {
                "title": title, "link": link,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": urlparse(link).netloc, "summary": summary[:200],
            })
            if bypass_cache:
                return falhas_feed, True
    return falhas_feed, False


async def _rodar_html_monitor(bot, guilds, state) -> None:
    """Sites oficiais sem RSS: três estados, e envio que não derruba a varredura."""
    try:
        html_updates, new_hashes, estado = await check_official_sites(state.get("html_hashes", {}))
    except Exception as e:
        log.exception(f"❌ Erro no HTML Monitor: {e}")
        return
    state["html_hashes"] = new_hashes
    if estado == ESTADO_NAO_CONFIGURADO:
        log.debug("HTML Monitor: nenhum site oficial no catálogo (official_sites).")
        return
    log.info(f"🔎 HTML Monitor: estado={estado} mudanças={len(html_updates)}")
    for update in html_updates:
        for gid, gdata in guilds.items():
            channel = bot.get_channel(gdata["channel_id"])
            if channel is None:
                continue
            try:
                await channel.send(f"⚠️ **CYBERINTEL ALERT**\n{update['title'][:200]}\n{update['link']}")
            except Exception as e:
                log.error(f"❌ HTML Monitor: falha ao avisar guild {gid}: {type(e).__name__}: {e}")


# =========================================================
# LOOP MANAGEMENT
# =========================================================

loop_task = None

def start_scheduler(bot: discord.Client):
    """Inicia o loop agendado."""
    global loop_task
    
    @tasks.loop(minutes=LOOP_MINUTES)
    async def intelligence_gathering():
        try:
            await run_scan_once(bot, trigger="loop")
        except Exception as e:
            log.exception(f"🔥 Erro não tratado dentro do loop 'intelligence_gathering': {e}")

    @intelligence_gathering.before_loop
    async def _before_loop():
        await bot.wait_until_ready()
    
    loop_task = intelligence_gathering
    loop_task.start()
    log.info(f"🔄 Agendador de tarefas iniciado ({LOOP_MINUTES} min).")
