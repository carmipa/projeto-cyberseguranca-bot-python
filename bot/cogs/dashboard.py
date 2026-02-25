import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import logging

from settings import DASHBOARD_PUBLIC_URL

log = logging.getLogger("CyberIntel")


class Dashboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # URL que o usuário vai clicar (pública ou via túnel)
        # Se quiser mascarar o endereço, deixe DASHBOARD_PUBLIC_URL vazio ("")
        # ou use um placeholder como "hidden" / "masked".
        self.dashboard_url = (DASHBOARD_PUBLIC_URL or "").strip()
        # URL interna usada pelo container para healthcheck
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

    async def _send_dashboard_embed(self, interaction: discord.Interaction) -> None:
        """Lógica compartilhada entre /dashboard e /monitor."""
        try:
            await interaction.response.defer(ephemeral=True)

            import os

            # Verifica ambiente: production (VPS) ou development (Local)
            is_vps = os.getenv("DEPLOY_ENV", "development").lower() == "production"

            # URL que será apresentada para o usuário clicar
            dashboard_url = self.dashboard_url
            hide_url = (not dashboard_url) or dashboard_url.lower() in {"hidden", "mask", "masked"}

            is_online = await self.check_nodered_health()

            embed = discord.Embed(
                title="🖥️ SOC Dashboard Access",
                description="Acesso ao painel de telemetria e análise de ameaças.",
                color=0x00ffcc if is_online else 0xff0000,
            )

            view = None
            if is_online:
                if is_vps:
                    embed.add_field(
                        name="🛡️ Ambiente: VPS (Produção)",
                        value=(
                            "Se você configurou um domínio público, o link abaixo já aponta para ele.\n"
                            "Se estiver usando **túnel SSH**, mantenha `DASHBOARD_PUBLIC_URL` como "
                            "`http://localhost:1880/ui` e abra o túnel antes de clicar."
                        ),
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name="🛠️ Ambiente: Local (Dev/Desktop)",
                        value="Rodando localmente.",
                        inline=False,
                    )

                if not hide_url:
                    embed.add_field(name="🔗 Link", value=f"[Abrir Dashboard]({dashboard_url})", inline=False)
                else:
                    embed.add_field(
                        name="🔐 Acesso",
                        value=(
                            "O endereço do SOC Dashboard está **mascarado** por segurança.\n"
                            "Use o runbook interno ou o túnel SSH configurado para abrir o painel."
                        ),
                        inline=False,
                    )
                embed.add_field(name="Status Node-RED", value="🟢 ONLINE", inline=True)

                view = None
                if not hide_url:
                    view = discord.ui.View()
                    view.add_item(
                        discord.ui.Button(
                            label="Abrir Painel", url=dashboard_url, style=discord.ButtonStyle.link
                        )
                    )
            else:
                embed.description = "⚠️ O serviço de Dashboard (Node-RED) parece estar offline."
                embed.add_field(name="Status", value="🔴 OFFLINE", inline=True)
                embed.add_field(name="Ação Requerida", value="Verifique o container `nodered`.", inline=False)

            embed.set_footer(text=f"Requisitado por: {interaction.user.name}")

            if view:
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            log.exception(f"❌ Erro ao montar embed do dashboard: {e}")
            try:
                await interaction.followup.send("❌ Erro ao acessar dashboard.", ephemeral=True)
            except Exception as send_error:
                log.error(f"❌ Falha ao enviar mensagem de erro no dashboard: {send_error}")

    @app_commands.command(name="dashboard", description="Acessa o SOC Dashboard em tempo real")
    async def dashboard(self, interaction: discord.Interaction):
        """Comando principal de acesso ao SOC Dashboard."""
        await self._send_dashboard_embed(interaction)

    @app_commands.command(
        name="monitor",
        description="Mostra o status do SOC e oferece abrir o dashboard em tempo real.",
    )
    async def monitor(self, interaction: discord.Interaction):
        """
        Alias amigável para /dashboard.
        Mantém toda a lógica de healthcheck e link em um único lugar.
        """
        await self._send_dashboard_embed(interaction)

async def setup(bot):
    await bot.add_cog(Dashboard(bot))
