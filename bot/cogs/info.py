"""
Info cog - Informational commands (/help, /about, /feeds, /ping, /server_log).
"""
import os
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
        try:
            embed = discord.Embed(
                title="🛡️ CyberIntel SOC Bot",
                description="Sistema de Inteligência em Cibersegurança e Monitoramento de Ameaças.",
                color=discord.Color.from_rgb(0, 255, 64)
            )
            
            if self.bot.user and self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)
            
            embed.add_field(name="👨‍💻 Desenvolvedor", value="Paulo André Carminati", inline=False)
            embed.add_field(name="🛠️ Stack", value="Python 3.10+ • Discord.py • Docker", inline=True)
            embed.add_field(name="🚀 Versão", value="NetRunner v1.0", inline=True)
            
            embed.set_footer(text="CyberIntel SOC System — Proteção Proativa")
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            log.exception(f"❌ Erro no comando /about: {e}")
            await interaction.response.send_message("❌ Erro ao exibir informações.", ephemeral=True)

    @app_commands.command(name="feeds", description="Lista todos os feeds monitorados.")
    async def feeds(self, interaction: discord.Interaction):
        try:
            urls = load_sources()
            total = len(urls)
            
            if total == 0:
                await interaction.response.send_message("⚠️ Nenhuma fonte configurada. Verifique `sources.json`.", ephemeral=True)
                return
            
            display_urls = urls[:15]
            remaining = total - 15
            
            lista = "\n".join(f"• <{u}>" for u in display_urls)
            if remaining > 0:
                lista += f"\n\n... e mais {remaining} fonte(s) configurada(s)."
                
            embed = discord.Embed(
                title=f"📡 Fontes de Inteligência ({total})",
                description=lista[:4096],  # Limite do Discord
                color=discord.Color.blue()
            )
            
            embed.set_footer(text="CyberIntel SOC | Monitoramento Ativo")
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            log.exception(f"❌ Erro ao listar feeds: {e}")
            await interaction.response.send_message("❌ Erro ao carregar lista de feeds.", ephemeral=True)

    @app_commands.command(name="server_log", description="Mostra as últimas linhas do log do servidor (apenas admin).")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(lines="Quantidade de linhas do log (10–200).")
    async def server_log(self, interaction: discord.Interaction, lines: int = 50):
        """
        Exibe as últimas N linhas do arquivo de log do bot (logs/bot.log).
        Restrito a administradores do servidor.
        """
        try:
            await interaction.response.defer(ephemeral=True)

            # Sanitiza quantidade de linhas
            if lines < 10:
                lines = 10
            if lines > 200:
                lines = 200

            # Caminho do log (mesmo usado pelo utils.logger)
            log_path = os.path.join(os.getcwd(), "logs", "bot.log")

            if not os.path.exists(log_path):
                await interaction.followup.send("❌ Arquivo de log não encontrado (`logs/bot.log`).", ephemeral=True)
                return

            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    all_lines = f.readlines()
            except Exception as read_err:
                log.exception(f"❌ Erro ao ler arquivo de log: {read_err}")
                await interaction.followup.send("❌ Não foi possível ler o arquivo de log.", ephemeral=True)
                return

            if not all_lines:
                await interaction.followup.send("⚠️ Arquivo de log vazio.", ephemeral=True)
                return

            tail = all_lines[-lines:]
            content = "".join(tail).strip()

            if not content:
                await interaction.followup.send("⚠️ Nenhum conteúdo de log para exibir.", ephemeral=True)
                return

            # Garante que não excede o limite de 2000 caracteres do Discord
            max_len = 1800
            truncated = False
            if len(content) > max_len:
                content = content[-max_len:]
                truncated = True

            header = f"📝 Últimas {lines} linha(s) de `logs/bot.log`"
            if truncated:
                header += " (trecho final truncado, arquivo completo em anexo)."

            message = f"{header}\n```log\n{content}\n```"

            if truncated:
                # Quando o conteúdo é truncado, também envia o arquivo completo como anexo
                await interaction.followup.send(
                    message,
                    file=discord.File(log_path, filename="server_log.txt"),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(message, ephemeral=True)
        except Exception as e:
            log.exception(f"❌ Erro no comando /server_log: {e}")
            try:
                await interaction.followup.send("❌ Erro ao exibir o log do servidor.", ephemeral=True)
            except Exception as send_error:
                log.error(f"❌ Falha ao enviar mensagem de erro no /server_log: {send_error}")

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
            value="`/dashboard` - Status do painel SOC.\n`/force_scan` - Força varredura imediata.\n`/set_channel` - Define canal de alertas.\n`/post_latest` - Bypass de cache para testes.\n`/server_log` - Últimas linhas do log (Admin).",
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
