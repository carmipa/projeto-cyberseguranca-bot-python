"""
Quem pode o quê. O estado do bot (dedup, log, catálogo) é ÚNICO para todos os
servidores: permissão de administrador de UMA guild não pode agir sobre as
outras. Mesmo defeito corrigido no gundam-news em 2026-09-25 (6a55fb8).
"""
import logging
import time
from typing import Tuple

import discord

from app.settings import OWNER_ID

log = logging.getLogger("CyberIntel")

INTERVALO_MINIMO_MANUAL_S = 10 * 60
_ultima_manual = 0.0


async def eh_dono(interaction: discord.Interaction) -> bool:
    """
    Diz se quem interage é o dono do bot.

    PROPÓSITO DE NEGÓCIO: ações com efeito em TODOS os servidores (repostar,
    ler o log global) são do dono, não do admin de um servidor qualquer.

    INVARIANTES DO DOMÍNIO: OWNER_ID do .env ou o dono da aplicação no Discord.

    COMPORTAMENTO EM CASO DE FALHA: qualquer erro na consulta devolve False
    (falha fechada). Nunca levanta.
    """
    try:
        if OWNER_ID and interaction.user.id == OWNER_ID:
            return True
        return bool(await interaction.client.is_owner(interaction.user))
    except Exception as e:
        log.warning(f"Checagem de dono falhou (negado): {type(e).__name__}: {e}")
        return False


def eh_admin(interaction: discord.Interaction) -> bool:
    """Administrador DESTE servidor. Falha fechada."""
    try:
        return bool(interaction.user.guild_permissions.administrator)
    except Exception:
        return False


async def solicitar_varredura_manual(bot, trigger: str) -> Tuple[bool, str]:
    """
    Porta única para toda varredura fora do agendador.

    PROPÓSITO DE NEGÓCIO:
        /forcecheck, /force_scan, /now, o botão "Verificar Agora" e a API do
        painel chamavam run_scan_once direto, sem intervalo: cinco admins de
        cinco servidores (ou cliques repetidos na lentidão) disparavam cinco
        varreduras globais, martelando as fontes do mesmo IP.

    INVARIANTES DO DOMÍNIO:
        - Nunca em modo bypass: varredura manual respeita o dedup.
        - Intervalo mínimo INTERVALO_MINIMO_MANUAL_S entre manuais.
        - Com uma varredura em andamento, recusa em vez de enfileirar.

    COMPORTAMENTO EM CASO DE FALHA:
        Devolve (False, motivo legível) quando recusa; (True, resumo do
        veredito) quando executou. Exceção da varredura é logada e vira
        (False, motivo). Nunca levanta.
    """
    global _ultima_manual
    from core.scanner import run_scan_once, scan_lock
    from core.stats import stats

    if scan_lock.locked():
        return False, "já existe uma varredura em andamento; aguarde ela terminar."
    espera = INTERVALO_MINIMO_MANUAL_S - (time.monotonic() - _ultima_manual)
    if _ultima_manual and espera > 0:
        return False, f"a última varredura manual foi há pouco; tente de novo em {int(espera // 60) + 1} min."
    _ultima_manual = time.monotonic()
    try:
        await run_scan_once(bot, trigger=trigger)
    except Exception as e:
        log.exception(f"❌ Varredura manual ({trigger}) falhou: {e}")
        return False, "a varredura falhou; detalhes no log do servidor."
    v = stats.ultimo_veredito or {}
    return True, f"{v.get('veredito', '?')}: " + " | ".join(v.get("motivos", []))[:1500]
