"""
Admin cog - Administrative commands (/forcecheck).
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging

log = logging.getLogger("CyberIntel")


class AdminCog(commands.Cog):
    """Cog com comandos administrativos."""
    
    def __init__(self, bot, run_scan_once_func):
        self.bot = bot
        self.run_scan_once = run_scan_once_func
    
    @app_commands.command(name="forcecheck", description="Força varredura imediata de feeds.")
    @app_commands.checks.has_permissions(administrator=True)
    async def forcecheck(self, interaction: discord.Interaction):
        """Força uma varredura imediata sem abrir o dashboard."""
        try:
            await interaction.response.defer(ephemeral=True)
            await self.run_scan_once(trigger="forcecheck")
            await interaction.followup.send("✅ Varredura forçada concluída!", ephemeral=True)
        except Exception as e:
            log.exception(f"❌ Erro crítico em /forcecheck: {e}")
            try:
                await interaction.followup.send("❌ Falha ao executar varredura.", ephemeral=True)
            except:
                pass
    
    @app_commands.command(name="post_latest", description="Força a postagem da notícia mais recente (ignora cache)")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_latest(self, interaction: discord.Interaction):
        """Força a postagem de 1 notícia ignorando se ela já foi postada."""
        try:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("🚀 Buscando notícia mais recente (Bypass Mode)...", ephemeral=True)
            await self.run_scan_once(trigger="post_latest", bypass_cache=True)
            await interaction.followup.send("✅ Operação finalizada. Verifique o canal SOC.", ephemeral=True)
        except Exception as e:
            log.exception(f"❌ Erro em /post_latest: {e}")
            await interaction.followup.send(f"❌ Falha: {e}", ephemeral=True)

    
    @forcecheck.error
    async def forcecheck_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Trata erros do comando /forcecheck."""
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ Você precisa ter **Administrador** para usar este comando."
            
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
            except discord.NotFound:
                pass
            return
        
        log.exception("Erro no comando /forcecheck", exc_info=error)


async def setup(bot):
    """Setup function para carregar o cog."""
    # O bound_scan foi injetado no bot no main.py
    run_scan = getattr(bot, "run_scan_once", None)
    await bot.add_cog(AdminCog(bot, run_scan))
