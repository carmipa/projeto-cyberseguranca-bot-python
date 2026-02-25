#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script auxiliar para testar reconexão do bot ao Discord dentro do container Docker.

Uso recomendado (dentro do container `cyber-bot`):

    python scripts/test_discord_reconnect.py

O script conecta ao Discord usando o mesmo TOKEN do bot e registra eventos
de desconexão e retomada. Em outro terminal, você pode simular uma perda
de rede temporária (por exemplo, bloqueando a saída na porta 443) e depois
removendo a regra. A biblioteca discord.py deve automaticamente tentar
reconectar.

Este script **não altera** a configuração do sistema de rede; ele apenas
observa o comportamento de reconexão.
"""

import asyncio
import logging
import os

import discord

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("DiscordReconnectTest")


async def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN não definido no ambiente do container.")

    intents = discord.Intents.none()
    intents.guilds = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        log.info("✅ Cliente de teste conectado como %s", client.user)
        log.info(
            "Simule agora uma queda de rede (ex.: bloquear saída TCP 443) "
            "e volte a liberar após alguns segundos para observar a reconexão."
        )

    @client.event
    async def on_disconnect():
        log.warning("⚠️ on_disconnect disparado – conexão com Discord perdida.")

    @client.event
    async def on_resumed():
        log.info("🔁 on_resumed disparado – sessão com Discord foi retomada.")

    await client.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Encerrado pelo usuário.")

