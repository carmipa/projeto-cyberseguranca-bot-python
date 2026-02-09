import discord
from discord.ext import commands, tasks
import logging
import os
from src.services.newsService import get_latest_security_news
from src.services.dbService import is_news_sent, mark_news_as_sent
from src.services.threatService import ThreatService
from core.scanner import run_scan_once
from discord import app_commands

log = logging.getLogger("CyberIntel")

class Monitor(commands.Cog):
    """
    Cog responsável pelo monitoramento contínuo de ameaças e ferramentas de scan.
    """
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

    @app_commands.command(name="force_scan", description="Força uma varredura imediata de inteligência e posta novidades")
    @app_commands.checks.has_permissions(administrator=True)
    async def force_scan(self, interaction: discord.Interaction):
        """Comando para forçar o ciclo de scan."""
        await interaction.response.defer(thinking=True)
        log.info(f"⚡ Force Scan iniciado por {interaction.user.name}")
        
        # Chama a função core do scanner
        try:
            await run_scan_once(self.bot, trigger="manual_force")
            await interaction.followup.send("✅ **Scan Manual Concluído!** Verifique os canais para novos alertas.")
        except Exception as e:
            log.error(f"Erro no Force Scan: {e}")
            await interaction.followup.send(f"❌ Erro ao executar scan: {e}")

    @app_commands.command(name="scan", description="Analisa uma URL suspeita (URLScan.io + VirusTotal)")
    @app_commands.describe(url="A URL para analisar")
    async def scan_command(self, interaction: discord.Interaction, url: str):
        """Comando de Scan de URL."""
        await interaction.response.defer(thinking=True)
        
        # 1. URLScan.io
        scan_data = await ThreatService.scan_url_urlscan(url)
        uuid = scan_data.get("uuid") if scan_data else None
        
        # 2. VirusTotal
        vt_data = await ThreatService.check_vt_reputation(url)
        
        embed = discord.Embed(title="🔎 Relatório de Inteligência", color=0x00FFCC)
        embed.add_field(name="Alvo", value=url, inline=False)
        
        if uuid:
            result_url = f"https://urlscan.io/result/{uuid}/"
            embed.add_field(name="URLScan.io", value=f"[Ver Relatório Completo]({result_url})", inline=True)
            # Nota: O resultado visual (screenshot) demora para processar, então mandamos o link
        else:
            embed.add_field(name="URLScan.io", value="❌ Falha ou não configurado", inline=True)
            
        if vt_data:
             # Se for submit, tem ID. Se for rep, tem stats.
             # Como implementamos submit, mostramos o link da análise
             analysis_id = vt_data.get("id", "Unknown")
             embed.add_field(name="VirusTotal", value=f"Análise submetida.\nID: {analysis_id}", inline=True)
        else:
             embed.add_field(name="VirusTotal", value="❌ Falha ou não configurado", inline=True)
             
        await interaction.followup.send(embed=embed)

    @tasks.loop(minutes=30)
    async def monitor_cyber_news(self):
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            # Em caso de restart, pode levar um tempo para o cache de canais popular
            return
            
        # ... logic mantida ...

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
