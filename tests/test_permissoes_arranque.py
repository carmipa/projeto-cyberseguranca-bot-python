"""
Permissões (estado global não é de admin de uma guild), porta única de varredura
manual, arranque idempotente e rede fora do event loop.
"""
import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import app.bootstrap as bootstrap
import bot.permissoes as perm
import core.scanner as scanner
from bot.cogs.admin import AdminCog
from bot.cogs.info import InfoCog
from bot.cogs.status import ScanButton
from utils.storage import p

pytestmark = pytest.mark.asyncio


class Resposta:
    def __init__(self):
        self.mensagens = []
        self._feito = False

    async def send_message(self, texto=None, **kw):
        self.mensagens.append(texto)
        self._feito = True

    async def defer(self, **kw):
        self._feito = True

    def is_done(self):
        return self._feito


class Followup:
    def __init__(self):
        self.mensagens = []

    async def send(self, texto=None, **kw):
        self.mensagens.append(texto)


def _interacao(user_id=5, admin=False, dono_app=False, is_owner_levanta=False):
    async def is_owner(user):
        if is_owner_levanta:
            raise RuntimeError("application info indisponível")
        return dono_app

    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, name="u", guild_permissions=SimpleNamespace(administrator=admin)),
        client=SimpleNamespace(is_owner=is_owner),
        response=Resposta(),
        followup=Followup(),
        guild_id=1,
    )


@pytest.fixture(autouse=True)
def zera_porta(monkeypatch):
    monkeypatch.setattr(perm, "_ultima_manual", 0.0)


async def test_dono_por_owner_id_e_por_aplicacao(monkeypatch):
    monkeypatch.setattr(perm, "OWNER_ID", 42)
    assert await perm.eh_dono(_interacao(user_id=42))
    assert await perm.eh_dono(_interacao(user_id=7, dono_app=True))
    assert not await perm.eh_dono(_interacao(user_id=7, admin=True))
    assert not await perm.eh_dono(_interacao(user_id=7, is_owner_levanta=True))


async def test_post_latest_negado_a_admin_de_guild(monkeypatch):
    monkeypatch.setattr(perm, "OWNER_ID", 42)
    chamadas = []

    async def varre(*a, **k):
        chamadas.append(k)

    monkeypatch.setattr(scanner, "run_scan_once", varre)
    i = _interacao(user_id=7, admin=True)
    await AdminCog.post_latest.callback(AdminCog(None), i)
    assert chamadas == []
    assert "dono" in i.response.mensagens[0]


async def test_post_latest_do_dono_usa_bypass(monkeypatch):
    monkeypatch.setattr(perm, "OWNER_ID", 42)
    chamadas = []

    async def varre(bot, **k):
        chamadas.append(k)

    monkeypatch.setattr(scanner, "run_scan_once", varre)
    await AdminCog.post_latest.callback(AdminCog(None), _interacao(user_id=42))
    assert chamadas == [{"trigger": "post_latest", "bypass_cache": True}]


async def test_server_log_negado_a_admin_e_liberado_ao_dono(monkeypatch):
    monkeypatch.setattr(perm, "OWNER_ID", 42)
    import bot.cogs.info as info
    monkeypatch.setattr(info, "eh_dono", perm.eh_dono)
    admin = _interacao(user_id=7, admin=True)
    await InfoCog.server_log.callback(InfoCog(None), admin, 10)
    assert "dono" in admin.response.mensagens[0]
    dono = _interacao(user_id=42)
    await InfoCog.server_log.callback(InfoCog(None), dono, 10)
    assert dono.response.mensagens == []
    assert dono.followup.mensagens


async def test_porta_unica_nunca_usa_bypass_e_respeita_intervalo(monkeypatch):
    chamadas = []

    async def varre(bot, **k):
        chamadas.append(k)

    monkeypatch.setattr(scanner, "run_scan_once", varre)
    ok1, _ = await perm.solicitar_varredura_manual(None, "a")
    ok2, texto = await perm.solicitar_varredura_manual(None, "b")
    assert ok1 and not ok2 and "min" in texto
    assert chamadas == [{"trigger": "a"}]
    monkeypatch.setattr(perm, "_ultima_manual", time.monotonic() - perm.INTERVALO_MINIMO_MANUAL_S - 1)
    ok3, _ = await perm.solicitar_varredura_manual(None, "c")
    assert ok3 and len(chamadas) == 2


async def test_porta_unica_recusa_com_varredura_em_andamento(monkeypatch):
    async def varre(bot, **k):
        raise AssertionError("não deveria varrer")

    monkeypatch.setattr(scanner, "run_scan_once", varre)
    async with scanner.scan_lock:
        ok, texto = await perm.solicitar_varredura_manual(None, "a")
    assert not ok and "andamento" in texto


async def test_botao_do_status_exige_admin(monkeypatch):
    chamadas = []

    async def porta(bot, trigger):
        chamadas.append(trigger)
        return True, "OK"

    import bot.cogs.status as status
    monkeypatch.setattr(status, "solicitar_varredura_manual", porta)
    view = ScanButton(None)
    membro = _interacao(admin=False)
    await view.scan_now.callback(membro)
    assert chamadas == [] and "administradores" in membro.response.mensagens[0]
    admin = _interacao(admin=True)
    await view.scan_now.callback(admin)
    assert chamadas == ["manual_button"]


class _Tree:
    def __init__(self, global_falha):
        self.global_falha = global_falha
        self.sync_global = 0

    def copy_global_to(self, guild):
        pass

    async def sync(self, guild=None):
        if guild is None:
            self.sync_global += 1
            if self.global_falha:
                raise RuntimeError("500 Internal Server Error")


async def test_ready_flow_roda_uma_vez_e_sync_global_nao_derruba(monkeypatch):
    web_calls, syncs = [], []

    async def sobe_web(**k):
        web_calls.append(1)

    async def sync_discord(bot):
        syncs.append(1)

    monkeypatch.setattr(bootstrap, "start_web_server", sobe_web)
    monkeypatch.setattr(bootstrap, "sync_from_discord", sync_discord)
    bot = SimpleNamespace(user=None, guilds=[SimpleNamespace(name="g", id=1)], tree=_Tree(global_falha=True),
                          add_view=lambda v: None)
    await bootstrap.register_ready_flow(bot)
    await bootstrap.register_ready_flow(bot)
    assert web_calls == [1]
    assert syncs == [1]
    assert bot.tree.sync_global == 1


async def test_news_service_com_fonte_lenta_nao_trava(monkeypatch):
    import src.services.newsService as ns

    async def lenta(request):
        await asyncio.sleep(5)
        return web.Response(text="")

    async def rapida(request):
        return web.Response(
            text='<rss><channel><item><title>T</title><link>https://e.com/a</link></item></channel></rss>',
            content_type="application/rss+xml")

    app = web.Application()
    app.router.add_get("/lenta", lenta)
    app.router.add_get("/rapida", rapida)
    server = TestServer(app)
    await server.start_server()
    try:
        monkeypatch.setattr(ns, "FEEDS", (str(server.make_url("/lenta")), str(server.make_url("/rapida"))))
        monkeypatch.setattr(ns, "_TIMEOUT_S", 0.5)
        inicio = time.monotonic()
        itens = await ns.get_latest_security_news()
        assert time.monotonic() - inicio < 3
        assert [i["link"] for i in itens] == ["https://e.com/a"]
    finally:
        await server.close()


async def test_monitor_rapido_nao_publica_em_canal_que_ja_e_de_guild(monkeypatch):
    from bot.cogs import monitor

    enviados = []

    class Canal:
        id = 555

        async def send(self, **kw):
            enviados.append(kw)

    async def noticias():
        return [{"title": "T", "link": "https://e.com/x", "summary": "S"}]

    monkeypatch.setattr(monitor, "get_latest_security_news", noticias)
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "0")
    cog = monitor.Monitor(SimpleNamespace(get_channel=lambda cid: Canal()))
    cog.channel_id = 555
    with open(p("config.json"), "w", encoding="utf-8") as f:
        json.dump({"1": {"channel_id": 555}}, f)
    await monitor.Monitor.monitor_cyber_news.coro(cog)
    assert enviados == []
    with open(p("config.json"), "w", encoding="utf-8") as f:
        json.dump({"1": {"channel_id": 999}}, f)
    await monitor.Monitor.monitor_cyber_news.coro(cog)
    assert len(enviados) == 1
