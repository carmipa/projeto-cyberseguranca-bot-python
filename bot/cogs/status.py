"""
Status cog - /status command to show bot statistics.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import logging

from core.stats import stats
from bot.permissoes import eh_dono, eh_admin, solicitar_varredura_manual
from app.settings import LOOP_MINUTES

log = logging.getLogger("CyberIntel")



class ScanButton(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Verificar Agora", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="status_scan_now")
    async def scan_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Botão do /status: só administrador, pela porta única (antes qualquer membro disparava varredura global)."""
        if not eh_admin(interaction):
            await interaction.response.send_message("❌ Apenas administradores podem forçar a verificação.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, texto = await solicitar_varredura_manual(self.bot, "manual_button")
        await interaction.followup.send(("✅ Verificação concluída. " if ok else "⏳ Não executada: ") + texto, ephemeral=True)


class StatusCog(commands.Cog):
    """Cog com comando de status do bot."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="status", description="Mostra estatísticas do bot CyberIntel.")
    async def status(self, interaction: discord.Interaction):
        """Exibe estatísticas e status atual do bot."""
        try:
            await interaction.response.defer(ephemeral=True) # Fix timeout
            
            # Próxima varredura: a do agendador, não "agora + intervalo".
            from core.scanner import loop_task
            proxima = loop_task.next_iteration if loop_task else None
            next_scan_ts = int(proxima.timestamp()) if proxima else None
            
            embed = discord.Embed(
                title="🔐 Status do CyberIntel Bot",
                color=discord.Color.from_rgb(0, 255, 64),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="⏰ Uptime",
                value=stats.format_uptime(),
                inline=True
            )
            
            embed.add_field(
                name="📡 Varreduras",
                value=f"{stats.scans_completed}",
                inline=True
            )
            
            embed.add_field(
                name="📰 Notícias Enviadas",
                value=f"{stats.news_posted}",
                inline=True
            )
            
            embed.add_field(
                name="📦 Cache Hits Total",
                value=f"{stats.cache_hits_total}",
                inline=True
            )
            
            if stats.last_scan_time:
                last_scan_str = f"<t:{int(stats.last_scan_time.timestamp())}:R>"
            else:
                last_scan_str = "Nenhuma ainda"
            
            embed.add_field(
                name="🕐 Última Varredura",
                value=last_scan_str,
                inline=True
            )
            
            embed.add_field(
                name="⏳ Próxima Varredura",
                value=f"<t:{next_scan_ts}:R>" if next_scan_ts else "Agendador parado",
                inline=True
            )
            ver = stats.ultimo_veredito or {}
            if ver:
                embed.add_field(
                    name=f"🩺 Saúde da última varredura: {ver.get('veredito', '?')}",
                    value=" | ".join(ver.get("motivos", []))[:1024] or "-",
                    inline=False,
                )
            
            embed.set_footer(text=f"NetRunner v1.0 | Intervalo: {LOOP_MINUTES} min")
            
            # Adiciona o botão de scan
            view = ScanButton(self.bot)
            
            # EPHEMERAL: Apenas o usuário que digitou vê a mensagem.
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            log.exception(f"❌ Erro no comando /status: {e}")
            try:
                await interaction.followup.send("❌ Erro ao exibir status.", ephemeral=True)
            except Exception as send_error:
                log.error(f"❌ Falha ao enviar mensagem de erro no /status: {send_error}")

    @app_commands.command(name="now", description="Força uma verificação imediata de notícias (respeita o intervalo mínimo).")
    @app_commands.checks.has_permissions(administrator=True)
    async def now(self, interaction: discord.Interaction):
        """Varredura manual pela porta única."""
        await interaction.response.defer(ephemeral=True)
        ok, texto = await solicitar_varredura_manual(self.bot, "command_now", ignora_intervalo=(dono := await eh_dono(interaction)), detalhado=dono)
        await interaction.followup.send(("✅ Scan finalizado. " if ok else "⏳ Não executado: ") + texto, ephemeral=True)


async def setup(bot):
    """Setup function para carregar o cog."""
    # O bound_scan foi injetado no bot no main.py
    await bot.add_cog(StatusCog(bot))
