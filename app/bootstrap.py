import logging
from datetime import datetime

import discord
from discord.ext import commands

from app.settings import COMMAND_PREFIX, LOG_LEVEL, TOKEN
from bot.views.filter_dashboard import FilterDashboard, LanguagePickerView
from core.scanner import run_scan_once, start_scheduler
from src.services.dbService import init_db
from utils.discord_sync import sync_from_discord
from utils.git_info import get_current_hash, get_git_changes
from utils.logger import setup_logger
from utils.storage import load_json_safe, p, save_json_safe
from web.server import start_web_server


log = logging.getLogger("CyberIntel")


def _init_runtime() -> None:
    init_db()
    try:
        from utils.backup import cleanup_old_backups
        cleanup_old_backups()
    except Exception as exc:
        log.warning("Falha ao limpar backups antigos: %s", exc)


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = True
    bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
    return bot


def bind_scan(bot: commands.Bot) -> None:
    async def bound_scan(trigger="manual", bypass_cache=False):
        await run_scan_once(bot, trigger, bypass_cache)
    bot.run_scan_once = bound_scan


async def register_ready_flow(bot: commands.Bot) -> None:
    log.info("✅ Bot conectado como: %s (ID: %s)", bot.user, bot.user.id if bot.user else "N/A")
    log.info("📊 Servidores conectados: %d", len(bot.guilds))

    try:
        await start_web_server(bot=bot, port=8080)
    except Exception as exc:
        log.exception("❌ Falha ao iniciar Web Server: %s", exc)

    cfg = load_json_safe(p("config.json"), {})
    if isinstance(cfg, dict):
        for gid in cfg.keys():
            try:
                bot.add_view(FilterDashboard(int(gid)))
                bot.add_view(LanguagePickerView(int(gid)))
                log.info("View persistente registrada para guild %s", gid)
            except Exception as exc:
                log.exception("❌ Erro ao registrar view para guild %s: %s", gid, exc)

    log.info("🔄 Sincronizando comandos Slash por Guild...")
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            log.info("✅ Sync concluído para guild: %s (%s)", guild.name, guild.id)
        except Exception as exc:
            log.exception("❌ Falha ao sincronizar guild %s: %s", guild.id, exc)

    await bot.tree.sync()
    log.info("✅ Slash sync global solicitado.")

    try:
        await sync_from_discord(bot)
    except Exception as sync_err:
        log.warning("Sync do Discord falhou (não crítico): %s", sync_err)


async def announce_version_if_needed(bot: commands.Bot) -> None:
    try:
        current_hash = get_current_hash()
        state_file = p("state.json")
        state = load_json_safe(state_file, {})
        last_hash = state.get("last_announced_hash")
        cfg = load_json_safe(p("config.json"), {})

        if not current_hash or current_hash == last_hash:
            return

        changes = get_git_changes()
        target_channel = None
        if isinstance(cfg, dict):
            for _, gdata in cfg.items():
                if isinstance(gdata, dict) and gdata.get("channel_id"):
                    target_channel = bot.get_channel(gdata["channel_id"])
                    if target_channel:
                        break

        if not target_channel:
            return

        log.info("📢 Anunciando nova versão %s no canal %s", current_hash, target_channel.name)
        now = datetime.now()
        date_str = now.strftime("%Y.%m.%d")
        time_str = now.strftime("%H:%M")

        embed = discord.Embed(
            title=f"🔐 CYBERINTEL SYSTEM UPDATE - LOG DAY {date_str}",
            description=f"{changes}\n\n**Repositório:** [github.com/carmipa/gundam-news-discord](https://github.com/carmipa/gundam-news-discord)",
            color=discord.Color.from_rgb(0, 255, 64),
        )
        embed.set_footer(text=f"Status: Secure | Nodes: Active | Deploy: {time_str} BRT")
        await target_channel.send(embed=embed)

        state["last_announced_hash"] = current_hash
        save_json_safe(state_file, state)
    except Exception as exc:
        log.exception("❌ Falha ao processar anúncio de versão: %s", exc)


async def load_extensions(bot: commands.Bot) -> None:
    extensions = [
        "bot.cogs.info",
        "bot.cogs.news",
        "bot.cogs.cve",
        "bot.cogs.monitor",
        "bot.cogs.stats",
        "bot.cogs.security",
        "bot.cogs.admin",
        "bot.cogs.dashboard",
        "bot.cogs.status",
        "bot.cogs.setup",
    ]
    for ext in extensions:
        try:
            await bot.load_extension(ext)
            log.info("🧩 Cog carregado: %s", ext)
        except Exception as exc:
            log.exception("❌ Falha ao carregar cog %s: %s", ext, exc)
    log.info("🚀 Todos os Cogs processados.")


async def run_bot() -> None:
    setup_logger(level=LOG_LEVEL)
    _init_runtime()
    bot = create_bot()
    bind_scan(bot)

    @bot.command()
    @commands.is_owner()
    async def sync(ctx):
        try:
            synced = await bot.tree.sync()
            await ctx.send(f"✅ Sincronizado {len(synced)} comandos globalmente.")
            if ctx.guild:
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced_guild = await ctx.bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ Sincronizado {len(synced_guild)} comandos na guild: {ctx.guild.name}")
        except Exception as exc:
            await ctx.send(f"❌ Erro ao sincronizar: {exc}")

    @bot.event
    async def on_ready():
        await register_ready_flow(bot)

    start_scheduler(bot)
    await announce_version_if_needed(bot)
    await load_extensions(bot)
    await bot.start(TOKEN)
