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


def bater(veredito: str = "", conectado=None) -> None:
    """
    Registra o instante da última varredura concluída e se o Discord estava
    conectado (None = desconhecido). Nunca levanta.
    """
    try:
        save_json_safe(p("heartbeat.json"), {"ts": time.time(), "veredito": veredito, "conectado": conectado})
    except Exception as e:
        log.warning(f"Falha ao gravar batimento: {e}")


def zerar() -> None:
    """
    Apaga o batimento no arranque: o arquivo mora no volume e sobrevive ao
    deploy — sem isto um contêiner novo que nem conecta herdaria o batimento
    do anterior e ficaria "healthy" por até 2 x LOOP_MINUTES (revisões de 26/09).
    """
    import os
    try:
        os.remove(p("heartbeat.json"))
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning(f"Não foi possível zerar o batimento: {e}")


def ler(caminho: str) -> dict:
    """Batimento como dict; levanta se ausente/ilegível (o healthcheck trata como doente)."""
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    float(dados["ts"])
    return dados


def idade_segundos(caminho: str) -> float:
    """Idade do batimento em segundos; levanta se ausente/ilegível."""
    return time.time() - float(ler(caminho)["ts"])
