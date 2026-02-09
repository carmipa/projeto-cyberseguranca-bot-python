import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import logging

log = logging.getLogger("CyberIntel")

class Dashboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dashboard_url = "http://localhost:1880/ui"
        self.nodered_internal_url = "http://nodered:1880" 

    async def check_nodered_health(self):
        """Verifica se o container do Node-RED está respondendo"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.nodered_internal_url, timeout=2) as resp:
                    return resp.status == 200
        except Exception as e:
            log.warning(f"Node-RED Health Check falhou: {e}")
            return False

    @app_commands.command(name="dashboard", description="Acessa o SOC Dashboard em tempo real")
    async def dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        import os
        # Verifica ambiente: production (VPS) ou development (Local)
        is_vps = os.getenv("DEPLOY_ENV", "development").lower() == "production"
        
        # URL Dashboard: Localhost se local, IP/Tunnel se VPS (aqui assumimos tunnel na porta 1880 ou config de host)
        # Se for VPS, o usuário acessa via túnel SSH (localhost dele -> servidor) ou IP direto se exposto (não recomendado)
        # O padrão seguro sugerido pelo usuário é acesso local via túnel, então a URL final é localhost também,
        # MAS a mensagem muda para orientar sobre o túnel.
        
        dashboard_url = "http://localhost:1880/ui"
        
        is_online = await self.check_nodered_health()
        
        embed = discord.Embed(
            title="🖥️ SOC Dashboard Access",
            description="Acesso ao painel de telemetria e análise de ameaças.",
            color=0x00ffcc if is_online else 0xff0000
        )
        
        view = None
        if is_online:
            if is_vps:
                embed.add_field(name="🛡️ Ambiente: VPS (Produção)", value="Acesso requer **Túnel SSH** na porta 1880.", inline=False)
                embed.add_field(name="🔗 Link", value=f"[Abrir Dashboard (Via Túnel)]({dashboard_url})", inline=False)
            else:
                embed.add_field(name="🛠️ Ambiente: Local (Dev/Desktop)", value="Rodando localmente.", inline=False)
                embed.add_field(name="🔗 Link", value=f"[Abrir Dashboard Local]({dashboard_url})", inline=False)
            
            embed.add_field(name="Status Node-RED", value="🟢 ONLINE", inline=True)
            
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Abrir Painel", url=dashboard_url, style=discord.ButtonStyle.link))
        else:
            embed.description = "⚠️ O serviço de Dashboard (Node-RED) parece estar offline."
            embed.add_field(name="Status", value="🔴 OFFLINE", inline=True)
            embed.add_field(name="Ação Requerida", value="Verifique o container `nodered`.", inline=False)

        embed.set_footer(text=f"Requisitado por: {interaction.user.name}")
        
        if view:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Dashboard(bot))
