import discord
from discord import app_commands
from discord.ext import commands
import json
import logging
from utils.storage import p, load_json_safe, save_json_safe

log = logging.getLogger("CyberIntel")

class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set_channel", description="Fixa o canal atual para receber os alertas do SOC")
    @app_commands.checks.has_permissions(administrator=True) # Apenas você (Admin) pode rodar
    async def set_channel(self, interaction: discord.Interaction):
        """Define o canal de postagem oficial do bot para este servidor."""
        
        # Validação básica
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
            return
        
        if not interaction.channel_id:
            await interaction.response.send_message("❌ Erro ao obter ID do canal.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            config_path = p("config.json")
            config_data = load_json_safe(config_path, {})
            
            guild_id_str = str(interaction.guild_id)
            
            # Preserva configs existentes ou cria nova
            if guild_id_str not in config_data:
                config_data[guild_id_str] = {
                    "filters": ["security", "cyber", "hacker", "breach"], # Default filters
                    "language": "pt_BR" 
                }
                
            config_data[guild_id_str]["channel_id"] = interaction.channel_id

            # Salva a configuração para persistência
            save_json_safe(config_path, config_data, atomic=True)
            
            embed = discord.Embed(
                title="🛡️ Canal Configurado",
                description=f"Este canal (**{interaction.channel.name}**) agora é a central oficial de Intel.",
                color=0x00FFCC # Seu Ciano Mecha
            )
            embed.add_field(name="ID do Canal", value=interaction.channel_id)
            embed.set_footer(text="CyberIntel SOC | Persistência Ativa")
            
            log.info(f"✅ Canal de alertas definido para: {interaction.channel.id} na guild {interaction.guild.name}")
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            log.exception(f"❌ Erro ao salvar configuração de canal: {e}")
            try:
                await interaction.response.send_message("❌ Erro ao salvar configuração.", ephemeral=True)
            except:
                await interaction.followup.send("❌ Erro ao salvar configuração.", ephemeral=True)

    @app_commands.command(name="soc_status", description="Status dos serviços de inteligência")
    async def soc_status_command(self, interaction: discord.Interaction):
        """Mostra o status atual do bot e serviços conectados."""
        try:
            await interaction.response.defer()
            
            embed = discord.Embed(title="📊 CyberIntel System Status", color=0x00FFCC)
            
            # 1. Canal Configurado
            config_data = load_json_safe(p("config.json"), {})
            guild_id_str = str(interaction.guild_id) if interaction.guild_id else "0"
            guild_data = config_data.get(guild_id_str, {})
            channel_id = guild_data.get("channel_id")
            
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                channel_name = channel.name if channel else "Desconhecido/Inacessível"
                embed.add_field(name="📡 Canal Alvo", value=f"#{channel_name} (`{channel_id}`)", inline=False)
            else:
                embed.add_field(name="📡 Canal Alvo", value="⚠️ Não configurado. Use `/set_channel`.", inline=False)

            # 2. Filtros Negativos
            neg_filters = guild_data.get("negative_filters", [])
            if neg_filters:
                embed.add_field(name="🚫 Filtros Negativos", value=", ".join(neg_filters), inline=False)

            # 3. APIs
            from app.settings import NVD_API_KEY, URLSCAN_API_KEY, OTX_API_KEY, VT_API_KEY
            
            api_status = []
            api_status.append("✅ NVD (NIST)" if NVD_API_KEY else "⚠️ NVD (Sem Key - Limite Baixo)")
            api_status.append("✅ URLScan.io" if URLSCAN_API_KEY else "❌ URLScan.io")
            api_status.append("✅ AlienVault OTX" if OTX_API_KEY else "❌ AlienVault OTX")
            api_status.append("✅ VirusTotal" if VT_API_KEY else "❌ VirusTotal")
            
            embed.add_field(name="🌐 APIs Conectadas", value="\n".join(api_status), inline=False)
            embed.set_footer(text="CyberIntel SOC | System Status")
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            log.exception(f"❌ Erro no comando /soc_status: {e}")
            try:
                await interaction.followup.send("❌ Erro ao verificar status dos serviços.", ephemeral=True)
            except Exception as send_error:
                log.error(f"❌ Falha ao enviar mensagem de erro no /soc_status: {send_error}")

    @app_commands.command(name="filter_negative", description="Gerencia palavras-chave proibidas para evitar ruído (ex: marketing, crypto)")
    @app_commands.describe(action="add / remove / list", keyword="A palavra-chave para adicionar ou remover")
    @app_commands.checks.has_permissions(administrator=True)
    async def filter_negative(self, interaction: discord.Interaction, action: str, keyword: str = None):
        """Gerencia os filtros negativos da guild."""
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Comando apenas para servidores.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        config_path = p("config.json")
        config_data = load_json_safe(config_path, {})
        guild_id_str = str(interaction.guild_id)
        
        if guild_id_str not in config_data:
            config_data[guild_id_str] = {"filters": ["security"], "language": "pt_BR", "negative_filters": []}
        
        if "negative_filters" not in config_data[guild_id_str]:
            config_data[guild_id_str]["negative_filters"] = []
            
        neg_filters = config_data[guild_id_str]["negative_filters"]
        action = action.lower()

        if action == "add":
            if not keyword:
                await interaction.followup.send("❌ Você precisa informar a palavra-chave.")
                return
            kw = keyword.lower().strip()
            if kw not in neg_filters:
                neg_filters.append(kw)
                save_json_safe(config_path, config_data)
                await interaction.followup.send(f"✅ Palavra-chave **'{kw}'** adicionada aos filtros negativos.")
            else:
                await interaction.followup.send(f"⚠️ **'{kw}'** já está nos filtros.")

        elif action == "remove":
            if not keyword:
                await interaction.followup.send("❌ Você precisa informar a palavra-chave.")
                return
            kw = keyword.lower().strip()
            if kw in neg_filters:
                neg_filters.remove(kw)
                save_json_safe(config_path, config_data)
                await interaction.followup.send(f"✅ Palavra-chave **'{kw}'** removida.")
            else:
                await interaction.followup.send(f"❌ **'{kw}'** não encontrada nos filtros.")

        elif action == "list":
            if not neg_filters:
                await interaction.followup.send("📝 Nenhum filtro negativo configurado.")
            else:
                await interaction.followup.send(f"📝 **Filtros Negativos Ativos:**\n`{', '.join(neg_filters)}`")
        else:
            await interaction.followup.send("❌ Ação inválida. Use `add`, `remove` ou `list`.")

async def setup(bot):
    await bot.add_cog(Setup(bot))
