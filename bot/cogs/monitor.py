import discord
from discord.ext import commands, tasks
import logging
import os
from src.services.newsService import get_latest_security_news
from src.services.dbService import is_news_sent, mark_news_as_sent

log = logging.getLogger("CyberIntel")

class Monitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
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
            # Em caso de restart, pode levar um tempo para o cache de canais popular
            return

        try:
            # Busca as notícias dos feeds usando o serviço centralizado
            news_items = get_latest_security_news()
            
            for item in news_items:
                # Se o link NÃO estiver no banco, é novo!
                if not is_news_sent(item['link']):
                    embed = discord.Embed(
                        title=f"🚨 NOVO ALERTA: {item['title']}",
                        url=item['link'],
                        description=item['summary'],
                        color=0xFF0000 # Vermelho para alertas automáticos
                    )
                    embed.set_footer(text="Monitoramento Automático - Threat Intelligence")
                    
                    log.info(f"📢 Nova ameaça detectada e enviada: {item['title']}")
                    await channel.send(embed=embed)
                    
                    # Salva no banco para não repetir
                    mark_news_as_sent(item['link'], item['title'])
                    
        except Exception as e:
            log.error(f"Erro no loop de monitoramento: {e}")

    @monitor_cyber_news.before_loop
    async def before_monitor(self):
        await self.bot.wait_until_ready()
        log.info("🛡️ Monitoramento de ameaças iniciado com persistência.")

async def setup(bot):
    await bot.add_cog(Monitor(bot))
