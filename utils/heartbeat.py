"""
Batimento do bot: prova de que o laço de varredura está vivo.

O healthcheck antigo do Docker era `import discord` — passa com o bot travado,
desconectado ou com o agendador morto (verde e cego). Este arquivo é regravado
no fim de TODA varredura, inclusive as que saem cedo, e o healthcheck confere a
idade dele.
"""
import json
import logging
import time

from utils.storage import p, save_json_safe

log = logging.getLogger("CyberIntel")


def bater(veredito: str = "") -> None:
    """Registra o instante da última varredura concluída. Nunca levanta."""
    try:
        save_json_safe(p("heartbeat.json"), {"ts": time.time(), "veredito": veredito})
    except Exception as e:
        log.warning(f"Falha ao gravar batimento: {e}")


def idade_segundos(caminho: str) -> float:
    """Idade do batimento em segundos; levanta se ausente/ilegível (o healthcheck trata como doente)."""
    with open(caminho, encoding="utf-8") as f:
        return time.time() - float(json.load(f)["ts"])
