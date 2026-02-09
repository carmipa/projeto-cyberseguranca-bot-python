"""
Info cog - Informational commands (/help, /about, /feeds, /ping).
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging

from core.stats import stats
from core.scanner import load_sources
from utils.storage import p, load_json_safe, save_json_safe

log = logging.getLogger("CyberIntel")


class InfoCog(commands.Cog):
    """Cog com comandos informativos."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="ping", description="Verifica a latência do bot.")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Pong! Latência: `{latency}ms`", ephemeral=True)

    @app_commands.command(name="about", description="Sobre o CyberIntel System.")
    async def about(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ CyberIntel SOC Bot",
            description="Sistema de Inteligência em Cibersegurança e Monitoramento de Ameaças.",
            color=discord.Color.from_rgb(0, 255, 64)
        )
        
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        
        embed.add_field(name="👨‍💻 Desenvolvedor", value="Paulo André Carminati", inline=False)
        embed.add_field(name="🛠️ Stack", value="Python 3.10 • Discord.py • Docker", inline=True)
        embed.add_field(name="🚀 Versão", value="v3.1 (Stable)", inline=True)
        
        embed.set_footer(text="CyberIntel SOC System — Proteção Proativa")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="feeds", description="Lista todos os feeds monitorados.")
    async def feeds(self, interaction: discord.Interaction):
        urls = load_sources()
        total = len(urls)
        
        display_urls = urls[:15]
        remaining = total - 15
        
        lista = "\n".join(f"• <{u}>" for u in display_urls)
        if remaining > 0:
            lista += f"\n\n... e mais {remaining} fontes configuradas."
            
        embed = discord.Embed(
            title=f"📡 Fontes de Inteligência ({total})",
            description=lista,
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="Mostra a lista de comandos disponíveis.")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🧰 Guia de Comandos CyberIntel",
            description="Aqui estão os comandos disponíveis para monitoramento e administração:",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="📡 Inteligência e Status",
            value="`/news` - Exibe os últimos alertas.\n`/cve [id]` - Busca detalhes de vulnerabilidades.\n`/scan [url]` - Analisa URLs suspeitas.\n`/soc_status` - Verifica conectividade das APIs.",
            inline=False
        )

        embed.add_field(
            name="🛠️ Configuração e Administração",
            value="`/dashboard` - Status do painel SOC.\n`/force_scan` - Força varredura imediata.\n`/set_channel` - Define canal de alertas.\n`/post_latest` - Bypass de cache para testes.",
            inline=False
        )

        embed.add_field(
            name="📊 Sistema",
            value="`/status` - Saúde do bot e da VPS.\n`/feeds` - Lista fontes monitoradas.\n`/about` - Informações técnicos.\n`/ping` - Latência real.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(InfoCog(bot))
