import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.permissoes import eh_dono, solicitar_varredura_manual
from src.services.dbService import is_news_sent, mark_news_as_sent
from src.services.newsService import get_latest_security_news
from src.services.threatService import ThreatService

log = logging.getLogger("CyberIntel")


class Monitor(commands.Cog):
    """
    Monitoramento rápido (a cada 30 min) de duas fontes para o canal do .env,
    e as ferramentas /force_scan e /scan.
    """

    def __init__(self, bot):
        self.bot = bot
        self.channel_id = int(os.getenv('DISCORD_CHANNEL_ID', os.getenv('DISCORD_NEWS_CHANNEL_ID', 0)) or 0)
        if self.channel_id:
            self.monitor_cyber_news.start()
        else:
            log.warning("⚠️ DISCORD_NEWS_CHANNEL_ID não configurado. Monitoramento automático desativado.")

    def cog_unload(self):
        self.monitor_cyber_news.cancel()

    @app_commands.command(name="force_scan", description="Força uma varredura imediata (respeita o intervalo mínimo).")
    @app_commands.checks.has_permissions(administrator=True)
    async def force_scan(self, interaction: discord.Interaction):
        """Varredura manual pela porta única."""
        await interaction.response.defer(ephemeral=True)
        log.info(f"⚡ Force Scan solicitado por {interaction.user.name} ({interaction.user.id})")
        ok, texto = await solicitar_varredura_manual(self.bot, "manual_force", ignora_intervalo=(dono := await eh_dono(interaction)), detalhado=dono)
        await interaction.followup.send(("✅ Scan concluído. " if ok else "⏳ Não executado: ") + texto, ephemeral=True)

    @app_commands.command(name="scan", description="Analisa uma URL suspeita (URLScan.io + VirusTotal)")
    @app_commands.describe(url="A URL para analisar")
    async def scan_command(self, interaction: discord.Interaction, url: str):
        """Comando de Scan de URL."""
        await interaction.response.defer()
        if not url or not url.startswith(("http://", "https://")) or len(url) > 2000:
            await interaction.followup.send("❌ URL inválida. Use uma URL completa começando com http:// ou https://")
            return
        try:
            scan_data = await ThreatService.scan_url_urlscan(url)
            uuid = scan_data.get("uuid") if scan_data else None
            vt_data = await ThreatService.check_vt_reputation(url)

            embed = discord.Embed(title="🔎 Relatório de Inteligência", color=0x00FFCC)
            embed.add_field(name="Alvo", value=url[:1024], inline=False)
            if uuid:
                embed.add_field(name="URLScan.io", value=f"[Ver Relatório Completo](https://urlscan.io/result/{uuid}/)", inline=True)
            else:
                embed.add_field(
                    name="URLScan.io",
                    value="❌ Não disponível. Configure **URLSCAN_API_KEY** no `.env` (grátis: urlscan.io/user/signup).",
                    inline=True,
                )
            if vt_data and not vt_data.get("error"):
                analysis_id = str(vt_data.get("data", {}).get("id") or vt_data.get("id") or "Unknown")
                embed.add_field(name="VirusTotal", value=f"Análise submetida.\nID: {analysis_id[:50]}", inline=True)
            else:
                embed.add_field(
                    name="VirusTotal",
                    value="❌ Não disponível. Configure **VT_API_KEY** no `.env` (grátis: virustotal.com/gui/join-us).",
                    inline=True,
                )
            embed.set_footer(text="CyberIntel SOC | Threat Intelligence")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            log.exception(f"❌ Erro ao analisar URL {url[:200]}: {e}")
            await interaction.followup.send("❌ Erro ao analisar a URL; detalhes no log do servidor.")

    @tasks.loop(minutes=30)
    async def monitor_cyber_news(self):
        """
        Publica no canal do .env as notícias novas de duas fontes fixas.

        PROPÓSITO DE NEGÓCIO: alerta rápido entre varreduras longas.

        INVARIANTES DO DOMÍNIO:
            - Consulta o dedup da varredura (history.json) e o database.json, sob o
              mesmo scan_lock: antes cada caminho olhava só o seu registro, e a
              mesma notícia podia sair duas vezes no canal.
            - NÃO grava no history.json: o history é global, e gravar ali uma
              notícia publicada só neste canal a tiraria de todos os outros
              servidores.
            - Se o canal do .env já é o canal de alguma guild, não publica: a
              varredura já entrega lá, com imagem e filtros.
            - Rede e disco fora do event loop; embed dentro dos limites do Discord.

        COMPORTAMENTO EM CASO DE FALHA: loga e tenta no próximo ciclo; notícia
        que falhou no envio não é marcada como enviada.
        """
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            log.warning(f"Monitor rápido: canal {self.channel_id} não encontrado; ciclo pulado.")
            return
        from core.scanner import load_history, sanitize_link, scan_lock
        from utils.storage import load_json_safe, p
        cfg = load_json_safe(p("config.json"), {})
        if isinstance(cfg, dict) and any(
            isinstance(g, dict) and g.get("channel_id") == self.channel_id for g in cfg.values()
        ):
            log.debug("Monitor rápido: canal do .env já recebe a varredura; nada a fazer.")
            return
        if scan_lock.locked():
            log.info("Monitor rápido: varredura em andamento; ciclo pulado.")
            return
        async with scan_lock:
            try:
                news_items = await get_latest_security_news()
                _, history_set = load_history()
                for item in news_items:
                    link = sanitize_link(item['link'])
                    if link in history_set or await asyncio_to_thread(is_news_sent, link):
                        continue
                    embed = discord.Embed(
                        title=f"🚨 NOVO ALERTA: {item['title']}"[:256],
                        url=link,
                        description=item['summary'][:4096],
                        color=0xFF0000,
                    )
                    embed.set_footer(text="Monitoramento Automático - Threat Intelligence")
                    await channel.send(embed=embed)
                    log.info(f"📢 Nova ameaça detectada e enviada: {item['title'][:80]}")
                    await asyncio_to_thread(mark_news_as_sent, link, item['title'])
            except Exception as e:
                log.exception(f"❌ Erro no loop de monitoramento: {e}")

    @monitor_cyber_news.before_loop
    async def before_monitor(self):
        await self.bot.wait_until_ready()
        log.info("🛡️ Monitoramento de ameaças iniciado com persistência.")


async def asyncio_to_thread(func, *args):
    import asyncio
    return await asyncio.to_thread(func, *args)


async def setup(bot):
    await bot.add_cog(Monitor(bot))
