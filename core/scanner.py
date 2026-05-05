"""
Scanner module - Feed fetching and processing logic.
"""
import ssl
import socket
import asyncio
import logging
import re
import feedparser
import aiohttp
import certifi
from typing import List, Set, Tuple, Dict, Any
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import time
import os
import random
from datetime import datetime, timedelta, timezone
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

from utils.storage import p, load_json_safe, save_json_safe
from utils.html import clean_html, safe_discord_url
from utils.cache import load_http_state, save_http_state, get_cache_headers, update_cache_state
from core.stats import stats
from core.filters import match_intel, match_gundam_relevance
from core.html_monitor import check_official_sites
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


def save_history(history_list: List[str], limit: int = 2000) -> None:
    """Mantém histórico limitado para não crescer infinito."""
    save_json_safe(p("history.json"), history_list[-limit:])


# =========================================================
# SOURCE MANAGEMENT
# =========================================================

def load_sources() -> List[str]:
    """
    Carrega feeds de sources.json.
    Retorna lista única de URLs http(s).
    """
    sources_raw = load_json_safe(p("sources.json"), [])
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
            val = sources_raw.get(key, [])
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        _add(item)
                    elif isinstance(item, dict):
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


def load_sources_meta() -> Dict[str, Dict[str, str]]:
    """
    Carrega metadados de sources.json (name/category/priority) indexados por URL de feed.
    Isso permite ajustar severidade visual com base na origem (Exploit, Gov, Regulatório, etc.).
    """
    data = load_json_safe(p("sources.json"), {})
    index: Dict[str, Dict[str, str]] = {}

    if isinstance(data, dict):
        for key in ("rss_feeds", "youtube_feeds", "official_sites"):
            val = data.get(key, [])
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        url = item.get("url")
                        if isinstance(url, str):
                            name = str(item.get("name", ""))
                            category = str(item.get("category", ""))
                            source_kind = "youtube" if key == "youtube_feeds" else "rss"
                            lower_hint = f"{name} {category}".lower()
                            segment = "specialized"
                            if any(x in lower_hint for x in ("google news", "reddit", "news", "aggregator", "general")):
                                segment = "generic"

                            index[url] = {
                                "name": item.get("name", ""),
                                "category": category,
                                "priority": item.get("priority", "Medium"),
                                "segment": item.get("segment", segment),
                                "source_kind": item.get("source_kind", source_kind),
                            }
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
    except:
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
            return dtparser.parse(str(s))
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


async def _extract_media_preview(session: aiohttp.ClientSession, link: str) -> Tuple[str, str]:
    """
    Scraping leve para capturar imagem/vídeo social cards quando o feed não traz mídia.
    Retorna (thumb_url, video_url).
    """
    try:
        async with session.get(link, allow_redirects=True) as resp:
            if resp.status >= 400:
                return "", ""
            html = await resp.text(errors="ignore")
    except Exception:
        return "", ""

    # Busca tags OG/Twitter primeiro (mais estável para preview)
    og_image = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    tw_image = re.search(r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    og_video = re.search(r'<meta[^>]+property=["\']og:video(?::url)?["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    video_src = re.search(r'<video[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    source_src = re.search(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)

    thumb = (og_image.group(1) if og_image else "") or (tw_image.group(1) if tw_image else "")
    video = (og_video.group(1) if og_video else "") or (video_src.group(1) if video_src else "") or (source_src.group(1) if source_src else "")
    return thumb.strip(), video.strip()


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


async def run_scan_once(bot: discord.Client, trigger: str = "manual", bypass_cache: bool = False) -> None:
    """
    Executa um ciclo completo de varredura de inteligência.
    """
    if scan_lock.locked():
        log.info(f"⏭️ Varredura ignorada (já existe uma em execução). Trigger: {trigger}")
        return

    async with scan_lock:
        scan_start_time = time.time()
        MAX_SCAN_DURATION = 14 * 60 # 14 minutos limite (loop de 15m)

        log.info(
            "🔎 scan.start trigger=%s bypass=%s loop_minutes=%s max_concurrency=%s gundam_mode=%s",
            trigger,
            bypass_cache,
            LOOP_MINUTES,
            MAX_CONCURRENT_FEEDS,
            GUNDAM_STRICT_MODE,
        )


        config = load_json_safe(p("config.json"), {})
        
        # Verifica se há guilds configuradas
        if not config or not any(isinstance(v, dict) and v.get("channel_id") for v in config.values()):
            log.warning("⚠️ Nenhuma guild configurada com 'channel_id'. Use /dashboard para configurar.")
            _log_next_run()
            return
            
        urls = load_sources()
        if not urls:
            log.warning("Nenhuma URL válida em sources.json.")
            _log_next_run()
            return

        # Índice de metadados das fontes (para severidade visual)
        source_meta = load_sources_meta()

        # =========================================================
        # UNIFIED STATE MANAGEMENT & AUTO-CLEANUP
        # =========================================================
        from utils.state_cleanup import check_and_cleanup_state

        # Caminho do arquivo de estado unificado
        state_file = p("state.json")

        # Verifica e limpa state.json se necessário (por tempo ou tamanho)
        state = check_and_cleanup_state(force=False)
        
        http_cache = state["http_cache"]
        html_hashes = state["html_hashes"]
        history_list, history_set = load_history()

        # Check-up de conectividade antes de iniciar download dos feeds
        if not await check_network_connectivity():
            log.warning("[WARN] Rede indisponível. Postergando scan.")
            _log_next_run()
            return

        # SSL Configuration
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        # User-Agent rotativo para evitar bloqueio em sites como CISA
        base_headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        }
        timeout = aiohttp.ClientTimeout(total=max(2, int(FEED_FETCH_TIMEOUT_MS / 1000)))
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        sent_count = 0
        cache_hits = 0
        node_red_enabled = True
        
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FEEDS)

        def _retry_delay(attempt_index: int) -> float:
            # Backoff exponencial com jitter para evitar thundering herd.
            base = FEED_FETCH_RETRY_BASE_DELAY * (2 ** attempt_index)
            jitter = random.uniform(0.0, FEED_FETCH_RETRY_BASE_DELAY)
            max_delay = max(1.0, FEED_FETCH_RETRY_MAX_DELAY_MS / 1000.0)
            return min(base + jitter, max_delay)

        def _is_transient_status(status_code: int) -> bool:
            return status_code in (403, 408, 409, 425, 429, 500, 502, 503, 504)

        def _prune_history_with_ttl() -> None:
            ttl_seconds = DEDUP_HISTORY_TTL_HOURS * 3600
            now_ts = time.time()
            history_seen_at = state.setdefault("history_seen_at", {})
            stale_links = [
                link for link, ts in history_seen_at.items()
                if isinstance(ts, (int, float)) and (now_ts - ts) > ttl_seconds
            ]
            if stale_links:
                stale_set = set(stale_links)
                for link in stale_links:
                    history_seen_at.pop(link, None)
                history_set.difference_update(stale_set)
                history_list[:] = [h for h in history_list if h not in stale_set]
                if isinstance(state.get("dedup"), dict):
                    for feed_key, items in state["dedup"].items():
                        if isinstance(items, list):
                            state["dedup"][feed_key] = [x for x in items if x not in stale_set]
                log.info("🧹 dedup.ttl_prune removed=%d ttl_hours=%d", len(stale_links), DEDUP_HISTORY_TTL_HOURS)

        _prune_history_with_ttl()

        async def fetch_and_process_feed(session, url):
            nonlocal cache_hits, state
            
            async with semaphore:
                # Jitter por requisição para reduzir padrão robótico.
                await asyncio.sleep(random.uniform(FEED_FETCH_JITTER_MIN, FEED_FETCH_JITTER_MAX))

                # Garante User-Agent de navegador rotativo
                use_cache = FEED_CACHE_ENABLED and not bypass_cache
                cache_headers = {} if not use_cache else get_cache_headers(url, http_cache)
                request_headers = {**cache_headers, "User-Agent": random.choice(BROWSER_USER_AGENTS)}

                for attempt in range(FEED_FETCH_MAX_RETRIES):
                    try:
                        async with session.get(url, headers=request_headers) as resp:
                            if resp.status == 304:
                                cache_hits += 1
                                log.debug(f"📦 Cache hit: {url} (304)")
                                return None

                            if _is_transient_status(resp.status):
                                if attempt < FEED_FETCH_MAX_RETRIES - 1:
                                    delay = _retry_delay(attempt)
                                    log.warning(
                                        "♻️ feed.retry url=%s status=%s attempt=%s/%s delay=%.2fs",
                                        url,
                                        resp.status,
                                        attempt + 1,
                                        FEED_FETCH_MAX_RETRIES,
                                        delay,
                                    )
                                    await asyncio.sleep(delay)
                                    continue
                                log.warning("⚠️ feed.drop_transient_exhausted url=%s status=%s", url, resp.status)
                                return None

                            if resp.status >= 400:
                                log.warning("⚠️ feed.http_error url=%s status=%s", url, resp.status)
                                return None

                            if resp.status == 431:
                                log.warning(f"⚠️ Twitter/X Error: Header value too long (431) - {url}")
                                return None

                            if use_cache:
                                update_cache_state(url, resp.headers, http_cache)
                            text = await resp.text(errors="ignore")

                        loop = asyncio.get_running_loop()
                        feed = await loop.run_in_executor(None, lambda: feedparser.parse(text))

                        entries = (getattr(feed, "entries", []) or [])
                        return (url, entries)

                    except asyncio.CancelledError:
                        # Não engolir: deixa o cancelamento propagar (ex.: shutdown do bot)
                        raise
                    except asyncio.TimeoutError:
                        if attempt < FEED_FETCH_MAX_RETRIES - 1:
                            delay = _retry_delay(attempt)
                            log.warning(
                                "⏱️ feed.timeout_retry url=%s attempt=%s/%s delay=%.2fs",
                                url,
                                attempt + 1,
                                FEED_FETCH_MAX_RETRIES,
                                delay,
                            )
                            await asyncio.sleep(delay)
                            continue
                        log.warning(
                            "⏱️ Timeout ao baixar feed (30s) após %d tentativas: %s...",
                            FEED_FETCH_MAX_RETRIES,
                            url[:60],
                        )
                        return None
                    except Exception as e:
                        if attempt < FEED_FETCH_MAX_RETRIES - 1:
                            delay = _retry_delay(attempt)
                            log.warning(
                                "♻️ feed.error_retry url=%s attempt=%s/%s delay=%.2fs err=%s",
                                url,
                                attempt + 1,
                                FEED_FETCH_MAX_RETRIES,
                                delay,
                                type(e).__name__,
                            )
                            await asyncio.sleep(delay)
                            continue
                        log.exception(f"❌ Falha ao baixar feed '{url}': {e}")
                        return None

                return None

        async with aiohttp.ClientSession(connector=connector, headers=base_headers, timeout=timeout) as session:
            # 1. Fetch RSS Feeds
            tasks = [fetch_and_process_feed(session, url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 2. Fetch CVEs (NIST API)
            try:
                cve_entries = await fetch_nvd_cves()
                if cve_entries:
                    log.info(f"🔎 Encontradas {len(cve_entries)} novas vulnerabilidades críticas (NVD).")
                    results.append(("api://nvd", cve_entries))
            except Exception as e:
                log.exception(f"❌ Falha ao buscar CVEs: {e}")

            # 3. Fetch OTX Pulses
            try:
                otx_pulses = await ThreatService.get_otx_pulses()
                if otx_pulses:
                    log.info(f"🛸 Encontrados {len(otx_pulses)} pulses do AlienVault OTX.")
                    # Formata para o padrão de entrada
                    formatted_pulses = []
                    for p_item in otx_pulses:
                        p_id = p_item.get("id")
                        formatted_pulses.append({
                            "title": f"🚨 OTX: {p_item.get('name', 'Unknown Threat')}",
                            "link": f"https://otx.alienvault.com/pulse/{p_id}",
                            "summary": f"**Threat:** {p_item.get('threat_hunter_scanner', 'Unknown')}\n\n{p_item.get('description', 'Sem descrição.')[:500]}...",
                            "source": "AlienVault OTX",
                            "published": p_item.get("created")
                        })
                    results.append(("api://otx", formatted_pulses))
            except Exception as e:
                log.exception(f"❌ Falha ao buscar OTX Pulses: {e}")

            # 4. Process All Results
            for result in results:
                if isinstance(result, Exception):
                    log.warning(f"⚠️ Uma tarefa de feed falhou: {result}")
                    continue
                if result is None:
                    continue
                    
                if (time.time() - scan_start_time) > MAX_SCAN_DURATION:
                    log.warning("🛑 Tempo limite do scan alcançado (>14min). Abortando loop de postagens de feeds para evitar bloqueios do Discord e overlaps.")
                    break
                    
                url, entries = result
                
                is_cold_start = url not in state["dedup"]
                if is_cold_start:
                    log.info(f"❄️ [Cold Start] Detectado para {url}. Inicializando dedup e flexibilizando filtro de idade.")
                    state["dedup"][url] = []
                
                feed_meta = source_meta.get(url, {})
                source_segment = str(feed_meta.get("segment", "specialized"))
                source_kind = str(feed_meta.get("source_kind", "rss"))
                
                for entry in entries:
                    # Suporte a dict (CVE) ou objeto feedparser (RSS)
                    if isinstance(entry, dict):
                        link = entry.get("link") or ""
                        title = entry.get("title") or ""
                        summary = entry.get("summary") or ""
                    else:
                        link = entry.get("link") or ""
                        title = entry.get("title") or ""
                        summary = entry.get("summary") or entry.get("description") or ""

                    if not link: continue
                    link = sanitize_link(link)
                    
                    # Deduplicação (Ignorada em modo Bypass)
                    if not bypass_cache:
                        if link in state["dedup"].get(url, []):
                            continue
                        if link in history_set:
                            continue

                    if (time.time() - scan_start_time) > MAX_SCAN_DURATION:
                        break

                    # Filtro de Data
                    entry_dt = parse_entry_dt(entry)
                    if entry_dt:
                        now = datetime.now(entry_dt.tzinfo) if entry_dt.tzinfo else datetime.now()
                        age = now - entry_dt
                        if not is_cold_start and age.days > 7:
                            log.debug(f"👴 [Old] Ignorado (idade {age.days}d): {link}")
                            continue

                    posted_anywhere = False
                    t_clean = clean_html(title).strip()
                    s_clean = clean_html(summary).strip()[:2000]
                    translation_cache: Dict[str, Tuple[str, str]] = {}

                    # Camada semântica opcional para cenários específicos (Gundam/Gunpla).
                    if GUNDAM_STRICT_MODE:
                        is_relevant, reason = match_gundam_relevance(
                            title=t_clean,
                            summary=s_clean,
                            source_segment=source_segment,
                            source_kind=source_kind,
                            require_title_for_generic_yt=GUNDAM_REQUIRE_IN_TITLE_FOR_GENERIC_YT,
                            strict_negative=NEGATIVE_KEYWORDS_STRICT,
                        )
                        if not is_relevant:
                            log.debug(
                                "🧠 relevance.reject source=%s segment=%s kind=%s reason=%s title=%s",
                                url,
                                source_segment,
                                source_kind,
                                reason,
                                t_clean[:80],
                            )
                            continue

                    # Loop de Envio para Guilds
                    for gid, gdata in config.items():
                        if not isinstance(gdata, dict): continue
                        
                        channel_id = gdata.get("channel_id")
                        if not isinstance(channel_id, int): continue

                        if not match_intel(str(gid), title, summary, config, source_segment):
                            log.debug(f"🛡️ [Filtro] Guild {gid} bloqueou: {title[:50]}...")
                            continue
                        
                        log.info(f"✨ [Match] Guild {gid} aprovou: {title[:50]}...")
                        channel = bot.get_channel(channel_id)
                        
                        if channel is None:
                            log.warning(f"Canal {channel_id} não encontrado.")
                            continue

                        target_lang = "en_US"
                        if target_lang in translation_cache:
                            t_translated, s_translated = translation_cache[target_lang]
                        else:
                            # Tradução global desativada para reduzir CPU no hot path.
                            t_translated = t_clean
                            s_translated = s_clean
                            translation_cache[target_lang] = (t_translated, s_translated)

                        # Detector de Mídia
                        media_domains = ("youtube.com", "youtu.be", "twitch.tv")
                        # Lógica de Severidade Visual
                        cvss_score = 0.0
                        if isinstance(entry, dict) and "cvss" in entry:
                            # Se vier da API com score
                            # (Nota: no cveService já filtramos > 7.0)
                            pass 

                        # Severidade visual baseada em fonte + conteúdo
                        embed_color, author_prefix, is_critical = classify_severity(
                            title=title,
                            link=link,
                            feed_url=url,
                            source_meta=source_meta,
                        )

                        try:
                            embed = discord.Embed(
                                title=t_translated[:256],
                                description=s_translated,
                                url=link,
                                color=embed_color,
                                timestamp=datetime.now()
                            )
                            
                            # from utils.translator import t (Removido)
                            # author_name = t.get('embed.author', lang=target_lang) 
                            # Substituído pelo prefixo dinâmico de severidade
                            
                            icon_url = bot.user.avatar.url if bot.user and bot.user.avatar else None
                            embed.set_author(name=author_prefix, icon_url=icon_url)
                            
                            source_domain = urlparse(link).netloc
                            posted_at_text = _format_posted_at(entry_dt) if entry_dt else "Postado em: data não informada"
                            embed.add_field(name="🕒 Publicação", value=posted_at_text[:1024], inline=False)
                            footer_text = f"Fonte: {source_domain} • CyberIntel SOC"
                            embed.set_footer(text=footer_text)
                            
                            thumb_url = None
                            if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                                try:
                                    thumb_url = entry.media_thumbnail[0].get("url")
                                    if thumb_url:
                                        embed.set_thumbnail(url=thumb_url)
                                except Exception as e:
                                    log.debug(f"Falha ao extrair thumbnail de {link}: {e}")
                            
                            if "nvd.nist.gov" in link:
                                 thumb_url = "https://nvd.nist.gov/site-media/images/NIST_logo.svg?v=1"

                            if not thumb_url:
                                scraped_thumb, scraped_video = await _extract_media_preview(session, link)
                                if scraped_thumb:
                                    thumb_url = scraped_thumb
                                if scraped_video:
                                    embed.add_field(name="🎬 Vídeo detectado", value=scraped_video[:1024], inline=False)

                            if thumb_url:
                                embed.set_thumbnail(url=thumb_url)

                            # Validação Robust de URL para Discord
                            final_link = safe_discord_url(link)
                            
                            # View com botões de compartilhamento
                            view = ShareButtons(t_translated[:100], final_link or link, is_critical=is_critical)

                            is_media = any(d in link for d in media_domains)
                            if is_media:
                                await channel.send(content=f"📺 **{t_translated}**\n{final_link or link}", view=view)
                            else:
                                if not final_link:
                                    embed.description = (embed.description or "") + f"\n\n🔗 **Link Original:** {link}"
                                await channel.send(embed=embed, view=view)

                            posted_anywhere = True
                            sent_count += 1
                            
                            await asyncio.sleep(2.5) # Sleep maior p/ prevenir flag de spam do Discord

                        except Exception as e:
                            log.exception(f"❌ Falha ao enviar no canal {channel_id}: {e}")

                    if posted_anywhere:
                        state["dedup"][url].append(link)
                        history_set.add(link)
                        history_list.append(link)
                        state.setdefault("history_seen_at", {})[link] = time.time()

                        # =========================================================
                        # PERSISTÊNCIA database.json (painel Windows + vps_api)
                        # =========================================================
                        try:
                            mark_news_as_sent(link, title=title, description=str(summary or ""))
                            log.debug(f"mark_news_as_sent chamado para: {link[:50]}...")
                        except Exception as db_e:
                            log.warning(f"⚠️ Falha ao gravar no database.json: {db_e}")

                        # =========================================================
                        # NODE-RED ALERT PUSH
                        # =========================================================
                        try:
                            if node_red_enabled:
                                alert_payload = {
                                    "title": title,
                                    "link": link,
                                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "source": urlparse(link).netloc,
                                    "summary": summary[:200]
                                }
                                async with session.post(NODE_RED_ENDPOINT, json=alert_payload) as nr_resp:
                                    if nr_resp.status == 200:
                                        log.debug(f"📡 Enviado para Node-RED: {title[:30]}")
                                    elif nr_resp.status == 404:
                                        node_red_enabled = False
                                        log.warning(
                                            "⚠️ Node-RED endpoint não encontrado (404) em %s. "
                                            "Desativando push para Node-RED até o próximo scan.",
                                            NODE_RED_ENDPOINT,
                                        )
                                    else:
                                        log.warning(f"⚠️ Node-RED retornou {nr_resp.status}")
                        except Exception as nr_e:
                            log.warning(f"⚠️ Falha ao enviar para Node-RED: {nr_e}")

        # =========================================================
        # HTML MONITOR RUN
        # =========================================================
        try:
            log.info("🔎 Verificando sites oficiais (HTML Watcher)...")
            html_updates, new_hashes = await check_official_sites(html_hashes)
            
            if html_updates:
                log.info(f"✨ {len(html_updates)} atualizações em sites oficiais!")
                state["html_hashes"] = new_hashes
                for update in html_updates:
                    u_title = update["title"]
                    
                    # Notifica Discord
                    for gid, gdata in config.items():
                         channel_id = gdata.get("channel_id")
                         if channel_id:
                             channel = bot.get_channel(channel_id)
                             if channel:
                                 await channel.send(f"⚠️ **CYBERINTEL ALERT**\n{u_title}\n{update['link']}")
            else:
                 if new_hashes != html_hashes:
                     state["html_hashes"] = new_hashes
                     
        except Exception as e:
            log.exception(f"❌ Erro no HTML Monitor: {e}")

        save_history(history_list)
        # Persiste o estado atualizado de forma atômica
        save_json_safe(state_file, state, atomic=True)
        
        # Backup automático após varredura bem-sucedida
        try:
            from utils.backup import auto_backup_critical_files
            auto_backup_critical_files()
        except Exception as backup_error:
            log.warning(f"Falha no backup automático: {backup_error}")
        
        stats.scans_completed += 1
        stats.news_posted += sent_count
        stats.cache_hits_total += cache_hits
        stats.last_scan_time = datetime.now()
        
        log.info(
            "✅ scan.done sent=%s cache_hits=%s total_feeds=%s trigger=%s cache_enabled=%s",
            sent_count,
            cache_hits,
            len(urls),
            trigger,
            FEED_CACHE_ENABLED,
        )
        _log_next_run()


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
