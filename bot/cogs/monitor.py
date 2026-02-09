import discord
from discord.ext import commands, tasks
import logging
import os
import feedparser

log = logging.getLogger("CyberIntel")

class Monitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_news_link = None
        self.channel_id = int(os.getenv('DISCORD_NEWS_CHANNEL_ID', 0))
        
        # Inicia o loop se o channel ID estiver configurado
        if self.channel_id:
            self.monitor_cyber_news.start()
        else:
            log.warning("⚠️ DISCORD_NEWS_CHANNEL_ID não configurado. Monitoramento automático desativado.")

    def cog_unload(self):
        self.monitor_cyber_news.cancel()

    @tasks.loop(minutes=30)
    async def monitor_cyber_news(self):
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            log.warning(f"⚠️ Canal de notícias não encontrado (ID: {self.channel_id})")
            return

        try:
            # Usando o feedparser diretamente conforme solicitado, mas idealmente usaria o service
            # Para manter consistência com o pedido do usuário:
            feed = feedparser.parse("https://feeds.feedburner.com/TheHackersNews")
            
            if feed.entries:
                latest = feed.entries[0]
                
                # Só posta se for uma notícia nova e diferente da última vista nesta sessão
                # (Idealmente persistiria isso em banco/json para sobreviver a restart)
                if self.last_news_link != latest.link:
                    self.last_news_link = latest.link
                    
                    embed = discord.Embed(
                        title=f"🚨 ALERTA: {latest.title}",
                        url=latest.link,
                        description=(latest.description[:300] + "...") if hasattr(latest, 'description') else "Sem descrição.",
                        color=0xFF0000 # Vermelho para alertas automáticos
                    )
                    embed.set_footer(text="Monitoramento Automático - Threat Intelligence")
                    
                    log.info(f"📢 Nova ameaça detectada: {latest.title}")
                    await channel.send(embed=embed)
                    
        except Exception as e:
            log.error(f"Erro no loop de monitoramento: {e}")

    @monitor_cyber_news.before_loop
    async def before_monitor(self):
        await self.bot.wait_until_ready()
        log.info("🛡️ Monitoramento de ameaças iniciado.")

async def setup(bot):
    await bot.add_cog(Monitor(bot))
