"""
Scanner module - Feed fetching and processing logic.
"""
import ssl
import asyncio
import logging
import feedparser
import aiohttp
import certifi
from datetime import datetime, timedelta, timezone
from dateutil import parser as dtparser
from typing import List, Set, Tuple, Dict, Any
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import time
import os

import discord
from discord.ext import tasks

from settings import LOOP_MINUTES, NODE_RED_ENDPOINT
from utils.storage import p, load_json_safe, save_json_safe
from utils.html import clean_html, safe_discord_url
from utils.cache import load_http_state, save_http_state, get_cache_headers, update_cache_state
# from utils.translator import translate_to_target, t (Removido sistema legado)
from core.stats import stats
from core.filters import match_intel
from core.html_monitor import check_official_sites
from src.services.cveService import fetch_nvd_cves
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
                            index[url] = {
                                "name": item.get("name", ""),
                                "category": item.get("category", ""),
                                "priority": item.get("priority", "Medium"),
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
        # Tenta dateutil primeiro (ISO 8601 do YouTube)
        if isinstance(entry, dict):
            s = entry.get("published") or entry.get("updated")
        else:
            s = getattr(entry, "published", None) or getattr(entry, "updated", None)
            
        if s:
            return dtparser.isoparse(s)
    except:
        pass
    
    # Fallback para struct_time do feedparser (apenas objetos)
    if not isinstance(entry, dict):
        try:
            st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
            if st:
                return datetime(*st[:6], tzinfo=timezone.utc)
        except:
            pass
        
    return None


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


async def run_scan_once(bot: discord.Client, trigger: str = "manual", bypass_cache: bool = False) -> None:
    """
    Executa um ciclo completo de varredura de inteligência.
    """
    if scan_lock.locked():
        log.info(f"⏭️ Varredura ignorada (já existe uma em execução). Trigger: {trigger}")
        return

    async with scan_lock:
        log.info(f"🔎 Iniciando varredura de inteligência... (trigger={trigger}, bypass={bypass_cache})")


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

        # SSL Configuration
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        sent_count = 0
        cache_hits = 0
        
        MAX_CONCURRENT_FEEDS = 5
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FEEDS)

        async def fetch_and_process_feed(session, url):
            nonlocal cache_hits, state
            
            async with semaphore:
                try:
                    if "youtube.com" in url or "youtu.be" in url:
                        await asyncio.sleep(2)
                        
                    request_headers = get_cache_headers(url, http_cache)
                    
                    async with session.get(url, headers=request_headers) as resp:
                        if resp.status == 304:
                            cache_hits += 1
                            log.debug(f"📦 Cache hit: {url} (304)")
                            return None
                        
                        if resp.status == 431:
                            log.warning(f"⚠️ Twitter/X Error: Header value too long (431) - {url}")
                            return None

                        update_cache_state(url, resp.headers, http_cache)
                        text = await resp.text(errors="ignore")
                    
                    loop = asyncio.get_running_loop()
                    feed = await loop.run_in_executor(None, lambda: feedparser.parse(text))
                    
                    entries = getattr(feed, "entries", []) or []
                    return (url, entries)
                    
                except Exception as e:
                    log.exception(f"❌ Falha ao baixar feed '{url}': {e}")
                    return None

        async with aiohttp.ClientSession(connector=connector, headers=base_headers, timeout=timeout) as session:
            # 1. Fetch RSS Feeds
            tasks = [fetch_and_process_feed(session, url) for url in urls]
            results = await asyncio.gather(*tasks)
            
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
                if result is None:
                    continue
                    
                url, entries = result
                
                is_cold_start = url not in state["dedup"]
                if is_cold_start:
                    log.info(f"❄️ [Cold Start] Detectado para {url}. Ignorando travas de tempo para os 3 primeiros posts.")
                    state["dedup"][url] = []
                
                feed_posted_count = 0
                
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

                    # Em modo bypass, pegamos apenas a primeira notícia total para evitar flood
                    if bypass_cache and sent_count >= 1: break
                    if is_cold_start and feed_posted_count >= 3: continue

                    # Filtro de Data
                    entry_dt = parse_entry_dt(entry)
                    if entry_dt:
                        now = datetime.now(entry_dt.tzinfo) if entry_dt.tzinfo else datetime.now()
                        age = now - entry_dt
                        if not is_cold_start and age.days > 7:
                            log.debug(f"👴 [Old] Ignorado (idade {age.days}d): {link}")
                            continue

                    posted_anywhere = False

                    # Loop de Envio para Guilds
                    for gid, gdata in config.items():
                        if not isinstance(gdata, dict): continue
                        
                        channel_id = gdata.get("channel_id")
                        if not isinstance(channel_id, int): continue

                        if not match_intel(str(gid), title, summary, config):
                            log.debug(f"🛡️ [Filtro] Guild {gid} bloqueou: {title[:50]}...")
                            continue
                        
                        log.info(f"✨ [Match] Guild {gid} aprovou: {title[:50]}...")
                        channel = bot.get_channel(channel_id)
                        
                        if channel is None:
                            log.warning(f"Canal {channel_id} não encontrado.")
                            continue

                        t_clean = clean_html(title).strip()
                        s_clean = clean_html(summary).strip()[:2000]

                        target_lang = "en_US"
                        if str(gid) in config and "language" in config[str(gid)]:
                            target_lang = config[str(gid)]["language"]
                        
                        # Skip translation - Using original content for SOC speed
                        t_translated = t_clean 
                        s_translated = s_clean

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
                            if is_cold_start: feed_posted_count += 1
                            
                            await asyncio.sleep(1)

                        except Exception as e:
                            log.exception(f"❌ Falha ao enviar no canal {channel_id}: {e}")

                    if posted_anywhere:
                        state["dedup"][url].append(link)
                        history_set.add(link)
                        history_list.append(link)
                        
                        # =========================================================
                        # NODE-RED ALERT PUSH
                        # =========================================================
                        try:
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
        
        log.info(f"✅ Varredura concluída. (enviadas={sent_count}, cache_hits={cache_hits}/{len(urls)}, trigger={trigger})")
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
