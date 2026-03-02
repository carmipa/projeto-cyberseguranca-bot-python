"""
Sincroniza mensagens do Discord para database.json.
Permite que o painel Windows exiba as notícias já publicadas no Discord.
"""
import logging
from utils.storage import p, load_json_safe
from src.services.dbService import mark_news_as_sent, is_news_sent

log = logging.getLogger("CyberIntel")

LIMIT_MESSAGES = 100  # Últimas N mensagens por canal


async def sync_from_discord(bot) -> int:
    """
    Busca mensagens recentes dos canais configurados e popula database.json.
    Retorna o número de itens adicionados.
    """
    config = load_json_safe(p("config.json"), {})
    if not config:
        log.debug("sync_from_discord: config.json vazio, nada a sincronizar")
        return 0

    added = 0
    for gid, gdata in config.items():
        if not isinstance(gdata, dict):
            continue
        channel_id = gdata.get("channel_id")
        if not channel_id:
            continue

        channel = bot.get_channel(channel_id)
        if not channel:
            log.warning(f"sync_from_discord: canal {channel_id} não encontrado")
            continue

        try:
            async for msg in channel.history(limit=LIMIT_MESSAGES):
                # Mensagens com embeds (formato do scanner)
                for embed in msg.embeds:
                    url = embed.url or ""
                    title = embed.title or ""
                    desc = embed.description or ""
                    if not url or not title:
                        continue
                    if is_news_sent(url):
                        continue
                    try:
                        mark_news_as_sent(url, title=title, description=desc)
                        added += 1
                        log.debug(f"Sync: adicionado {title[:40]}...")
                    except Exception as e:
                        log.warning(f"sync_from_discord: falha ao salvar {url[:50]}: {e}")

                # Mensagens com conteúdo e link (ex: mídia)
                if not msg.embeds and msg.content:
                    for word in msg.content.split():
                        if word.startswith("http") and "discord" not in word.lower():
                            if is_news_sent(word):
                                continue
                            title = msg.content[:100].replace("\n", " ")
                            try:
                                mark_news_as_sent(word, title=title)
                                added += 1
                            except Exception:
                                pass
                            break
        except Exception as e:
            log.exception(f"sync_from_discord: erro no canal {channel_id}: {e}")

    if added:
        log.info(f"✅ Sync do Discord: {added} notícia(s) adicionada(s) ao database.json")
    return added
