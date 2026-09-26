import discord
from discord import app_commands
from discord.ext import commands
import logging
from src.services.newsService import get_latest_security_news

log = logging.getLogger("CyberIntel")

class News(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="news", description="Busca as últimas notícias de Cyber Segurança (The Hacker News, BleepingComputer)")
    async def news(self, interaction: discord.Interaction):
        # Audit Log
        user = interaction.user
        log.info(f"AUDIT: Comando /news solicitado por {user} (ID: {user.id}) em {interaction.guild} (ID: {interaction.guild_id if interaction.guild else 'DM'})")

        await interaction.response.defer()

        try:
            news_items = await get_latest_security_news()
            
            if not news_items:
                await interaction.followup.send("❌ Não foi possível obter notícias no momento.")
                return

            embed = discord.Embed(
                title="🛡️ CyberIntel Feed - Últimas Notícias",
                description="Monitoramento de Threat Intelligence em tempo real.",
                color=0x00ffcc # Cyber Green
            )
            
            # Limita a 5 notícias para não exceder limite do Discord (25 fields)
            for item in news_items[:5]:
                title = item.get('title', 'Sem título')[:256]  # Limite do Discord
                summary = item.get('summary', 'Sem resumo')[:1024]  # Limite do Discord
                link = item.get('link', '#')
                
                embed.add_field(
                    name=title,
                    value=f"{summary}\n[Ler mais]({link})",
                    inline=False
                )

            embed.set_footer(text="Fontes: The Hacker News, BleepingComputer | CyberIntel System")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            log.exception(f"❌ Erro ao executar comando /news: {e}")
            try:
                await interaction.followup.send("❌ Ocorreu um erro ao buscar as notícias.")
            except Exception as send_error:
                log.error(f"❌ Falha ao enviar mensagem de erro no /news: {send_error}")

async def setup(bot):
    await bot.add_cog(News(bot))
