# =========================================================
# CyberIntel Bot - "NetRunner" v1.0
# main.py (Modularized)
#
# Ponto de entrada da aplicação. Gerencia o ciclo de vida do bot,
# carregamento de cogs, inicialização de serviços (Web, DB) e
# logs do sistema.
# =========================================================

import logging
import asyncio
import discord
from discord.ext import commands

from settings import TOKEN, COMMAND_PREFIX, LOG_LEVEL
from utils.storage import p, load_json_safe
from bot.views.filter_dashboard import FilterDashboard
from core.scanner import start_scheduler, run_scan_once
from web.server import start_web_server  # Novo web server
from utils.git_info import get_git_changes, get_current_hash
from utils.storage import save_json_safe

# Configuração de Logs
from utils.logger import setup_logger
from src.services.dbService import init_db

# Inicializa Logger Centralizado
setup_logger(level=LOG_LEVEL)

# Inicializa banco de dados
init_db()

log = logging.getLogger("CyberIntel")


# =========================================================
# SETUP DO BOT
# =========================================================

async def main():
    # Intents
    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = True

    # Bot Instance
    bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

    @bot.tree.command(name="ping", description="Teste rápido do CyberIntel")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("🏓 Pong! CyberIntel online.")

    # =========================================================
    # EVENTOS
    # =========================================================
    
    @bot.command()
    @commands.is_owner()
    async def sync(ctx):
        """Comando manual para sincronizar comandos Slash."""
        try:
            # Sync global
            synced = await bot.tree.sync()
            await ctx.send(f"✅ Sincronizado {len(synced)} comandos globalmente.")
            
            # Sync na guild atual também (garantia)
            if ctx.guild:
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced_guild = await ctx.bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ Sincronizado {len(synced_guild)} comandos na guild: {ctx.guild.name}")
        except Exception as e:
            await ctx.send(f"❌ Erro ao sincronizar: {e}")

    @bot.event
    async def on_ready():
        try:
            log.info(f"✅ Bot conectado como: {bot.user} (ID: {bot.user.id})")
            log.info(f"📊 Servidores conectados: {len(bot.guilds)}")

            # 0. Iniciar Web Server (Fase 10)
            try:
                await start_web_server(port=8080)
            except Exception as e:
                log.error(f"❌ Falha ao iniciar Web Server: {e}")

            # 1. Carregar Views Persistentes
            cfg = load_json_safe(p("config.json"), {})
            if isinstance(cfg, dict):
                for gid in cfg.keys():
                    try:
                        bot.add_view(FilterDashboard(int(gid)))
                        log.info(f"View persistente registrada para guild {gid}")
                    except Exception as e:
                        log.error(f"Erro view guild {gid}: {e}")

            # 2. Sync Comandos (Slash) movido para main() para ocorrer APÓS o carregamento dos cogs
            pass
        except Exception as e:
            log.error(f"Erro no on_ready: {e}")

    # =========================================================
    # CARREGAR COMPONENTES E CONFIGURAÇÕES NO BOOT
    # =========================================================

    # 3. Iniciar Loop de Scanner
    start_scheduler(bot)

    # 4. Anúncio de Versão (Git Check)
    try:
        current_hash = get_current_hash()
        state_file = p("state.json")
        state = load_json_safe(state_file, {})
        last_hash = state.get("last_announced_hash")

        if current_hash and current_hash != last_hash:
            changes = get_git_changes()
            repo_url = "https://github.com/carmipa/gundam-news-discord"
            
            target_channel = None
            if isinstance(cfg, dict):
                for gid, gdata in cfg.items():
                    if isinstance(gdata, dict) and gdata.get("channel_id"):
                         target_channel = bot.get_channel(gdata["channel_id"])
                         if target_channel: break
            
            if target_channel:
                log.info(f"📢 Anunciando nova versão {current_hash} no canal {target_channel.name}")
                from datetime import datetime
                now = datetime.now()
                date_str = now.strftime("%Y.%m.%d")
                time_str = now.strftime("%H:%M")
                
                embed = discord.Embed(
                    title=f"🔐 CYBERINTEL SYSTEM UPDATE - LOG DAY {date_str}",
                    description=f"{changes}\n\n**Repositório:** [github.com/carmipa/gundam-news-discord](https://github.com/carmipa/gundam-news-discord)",
                    color=discord.Color.from_rgb(0, 255, 64)
                )
                embed.set_footer(text=f"Status: Secure | Nodes: Active | Deploy: {time_str} BRT")
                await target_channel.send(embed=embed)
                
                state["last_announced_hash"] = current_hash
                save_json_safe(state_file, state)
            else:
                 log.warning("⚠️ Nova versão detectada, mas nenhum canal encontrado para anunciar.")
        else:
            log.info(f"ℹ️ Versão atual ({current_hash}) já anunciada anteriormente.")

    except Exception as e:
        log.error(f"❌ Falha ao processar anúncio de versão: {e}")

    # =========================================================
    # CARREGAR COGS
    # =========================================================
    
    async def bound_scan(trigger="manual"):
        await run_scan_once(bot, trigger)

    try:
        await bot.load_extension("bot.cogs.info")
        await bot.load_extension("bot.cogs.news")
        await bot.load_extension("bot.cogs.cve")
        await bot.load_extension("bot.cogs.monitor")
        await bot.load_extension("bot.cogs.stats")
        await bot.load_extension("bot.cogs.security")
        
        from bot.cogs.admin import setup as setup_admin
        from bot.cogs.dashboard import setup as setup_dashboard
        
        await setup_admin(bot, bound_scan)
        await setup_dashboard(bot, bound_scan)
        await bot.load_extension("bot.cogs.setup")
        
        log.info("🧩 Cogs carregados com sucesso.")

        # =========================================================
        # SYNC DE COMANDOS (SLASH) - Deve ocorrer APÓS carregar cogs
        # =========================================================
        log.info("🔄 Sincronizando comandos Slash (Árvore de Comandos)...")
        synced = await bot.tree.sync()
        log.info(f"✅ {len(synced)} comandos Slash sincronizados globalmente.")
        
    except Exception as e:
        log.exception(f"Falha ao carregar cogs ou sincronizar: {e}")

    # =========================================================
    # START
    # =========================================================
    await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("🛑 Bot encerrado pelo usuário.")
    except Exception as e:
        log.exception(f"🔥 Erro fatal: {e}")
