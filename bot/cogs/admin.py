"""
Admin cog - varredura manual (/forcecheck) e repostagem (/post_latest).
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.permissoes import eh_dono, solicitar_varredura_manual

log = logging.getLogger("CyberIntel")


class AdminCog(commands.Cog):
    """Comandos administrativos."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="forcecheck", description="Força varredura imediata de feeds (respeita o intervalo mínimo).")
    @app_commands.checks.has_permissions(administrator=True)
    async def forcecheck(self, interaction: discord.Interaction):
        """Varredura manual pela porta única (sem bypass, com intervalo mínimo)."""
        await interaction.response.defer(ephemeral=True)
        ok, texto = await solicitar_varredura_manual(self.bot, "forcecheck", ignora_intervalo=(dono := await eh_dono(interaction)), detalhado=dono)
        await interaction.followup.send(("✅ Varredura concluída. " if ok else "⏳ Não executada: ") + texto, ephemeral=True)

    @app_commands.command(name="post_latest", description="[DONO] Reposta UMA notícia ignorando o dedup, em todos os servidores.")
    async def post_latest(self, interaction: discord.Interaction):
        """
        Publica no máximo uma notícia ignorando o dedup.

        PROPÓSITO DE NEGÓCIO: teste de ponta a ponta da publicação.
        INVARIANTES DO DOMÍNIO: só o dono (o efeito atinge todos os servidores);
        no máximo uma notícia (antes publicava o feed inteiro dos últimos 7 dias
        em todas as guilds).
        COMPORTAMENTO EM CASO DE FALHA: nega com mensagem; erro vai ao log.
        """
        if not await eh_dono(interaction):
            await interaction.response.send_message("❌ Apenas o dono do bot pode repostar: o efeito atinge todos os servidores.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        from core.scanner import run_scan_once, scan_lock
        if scan_lock.locked():
            await interaction.followup.send("⏳ Já existe uma varredura em andamento.", ephemeral=True)
            return
        try:
            await run_scan_once(self.bot, trigger="post_latest", bypass_cache=True)
            await interaction.followup.send("✅ Operação finalizada (no máximo uma notícia). Verifique o canal.", ephemeral=True)
        except Exception as e:
            log.exception(f"❌ Erro em /post_latest: {e}")
            await interaction.followup.send("❌ Falha ao repostar; detalhes no log.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
