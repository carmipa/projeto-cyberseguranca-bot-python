"""
Canal do monitor rápido (DISCORD_CHANNEL_ID) inválido.

Medido na VPS em 2026-10-29: o .env tinha o ID do PRÓPRIO bot no lugar do canal.
O monitor nunca publicou nada e escreveu "canal não encontrado" 48 vezes por dia.

Cada regra tem o caso que tem de reagir e o gêmeo que tem de seguir normal.
"""
import logging
from types import SimpleNamespace

import pytest

from bot.cogs import monitor

pytestmark = pytest.mark.asyncio

ID_DO_BOT = 1470402817884684474


class Canal:
    id = 555

    def __init__(self):
        self.enviados = []

    async def send(self, **kw):
        self.enviados.append(kw)


@pytest.fixture
def cog(monkeypatch):
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "0")  # não dispara o loop real no __init__

    async def noticias():
        return [{"title": "T", "link": "https://e.com/x", "summary": "S"}]

    monkeypatch.setattr(monitor, "get_latest_security_news", noticias)
    canais = {}
    bot = SimpleNamespace(user=SimpleNamespace(id=ID_DO_BOT), get_channel=lambda cid: canais.get(cid))
    c = monitor.Monitor(bot)
    paradas = []
    monkeypatch.setattr(c.monitor_cyber_news, "stop", lambda: paradas.append(True))
    return c, canais, paradas


async def rodar(c):
    await monitor.Monitor.monitor_cyber_news.coro(c)


async def test_id_do_proprio_bot_desliga_o_monitor_com_erro(cog, caplog):
    c, canais, paradas = cog
    c.channel_id = ID_DO_BOT
    with caplog.at_level(logging.DEBUG, logger="CyberIntel"):
        await rodar(c)
        await rodar(c)
    erros = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(erros) == 1 and "ID do próprio bot" in erros[0].getMessage()
    assert paradas == [True]
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


async def test_gemeo_canal_valido_publica(cog):
    c, canais, paradas = cog
    canal = Canal()
    canais[555] = canal
    c.channel_id = 555
    await rodar(c)
    assert len(canal.enviados) == 1
    assert paradas == []


async def test_canal_ausente_avisa_uma_vez_por_dia(cog, caplog, monkeypatch):
    c, canais, paradas = cog
    c.channel_id = 777
    relogio = [1000.0]
    monkeypatch.setattr(monitor.time, "monotonic", lambda: relogio[0])
    with caplog.at_level(logging.DEBUG, logger="CyberIntel"):
        for _ in range(48):
            await rodar(c)
            relogio[0] += 30 * 60 - 1
        relogio[0] += 3600
        await rodar(c)
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avisos) == 2, "48 ciclos em ~24h dão um aviso; passado um dia, mais um"
    assert "não está visível" in avisos[0].getMessage()
    assert paradas == [], "canal ausente não desliga: a permissão pode voltar sem reinício"


async def test_canal_que_volta_e_anunciado_e_publica(cog, caplog):
    c, canais, _ = cog
    c.channel_id = 555
    with caplog.at_level(logging.INFO, logger="CyberIntel"):
        await rodar(c)
        canal = Canal()
        canais[555] = canal
        await rodar(c)
    assert any("voltou a ficar visível" in r.getMessage() for r in caplog.records)
    assert len(canal.enviados) == 1


async def test_bot_sem_user_ainda_nao_e_confundido_com_o_id(cog):
    # Antes do login `bot.user` é None: não pode desligar por engano.
    c, canais, paradas = cog
    c.bot.user = None
    c.channel_id = ID_DO_BOT
    await rodar(c)
    assert paradas == []
    assert c._desligado is False
