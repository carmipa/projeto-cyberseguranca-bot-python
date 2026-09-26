"""
Guardas do motor de varredura, executando o run_scan_once REAL contra um
servidor HTTP local e um Discord falso, e lendo o estado gravado em disco.

Cada cenário doente tem o gêmeo legítimo ao lado (A1).
"""
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

import core.scanner as scanner
from utils.storage import p

pytestmark = pytest.mark.asyncio


class Canal:
    def __init__(self, cid, falha=False):
        self.id = cid
        self.falha = falha
        self.enviados = []

    async def send(self, content=None, embed=None, view=None):
        if self.falha:
            raise RuntimeError("Missing Permissions (simulado)")
        self.enviados.append({"content": content, "embed": embed})


class Bot:
    def __init__(self, canais):
        self.canais = {c.id: c for c in canais}
        self.user = None

    def get_channel(self, cid):
        return self.canais.get(cid)


def _rss(itens):
    corpo = "".join(
        f"<item><title>{t}</title><link>{l}</link>"
        + (f"<pubDate>{format_datetime(d)}</pubDate>" if d else "")
        + f"<description>{desc}</description></item>"
        for t, l, d, desc in itens
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{corpo}</channel></rss>'


class Servidor:
    """Serve /feed com ETag e responde 304 a If-None-Match igual."""

    def __init__(self):
        self.xml = _rss([])
        self.status = 200
        self.pedidos = []

    async def feed(self, request):
        self.pedidos.append(dict(request.headers))
        if self.status != 200:
            return web.Response(status=self.status)
        if request.headers.get("If-None-Match") == '"v1"':
            return web.Response(status=304)
        return web.Response(text=self.xml, content_type="application/rss+xml", headers={"ETag": '"v1"'})


AGORA = datetime.now(timezone.utc)
RECENTE = AGORA - timedelta(hours=2)
ANTIGO = AGORA - timedelta(days=30)
TEXTO_CYBER = "New ransomware malware exploit vulnerability breach"


@pytest_asyncio.fixture
async def ambiente(dados_isolados, monkeypatch):
    srv = Servidor()
    app = web.Application()
    app.router.add_get("/feed", srv.feed)
    server = TestServer(app)
    await server.start_server()
    url = str(server.make_url("/feed"))
    monkeypatch.setattr(scanner, "load_sources", lambda: [url])
    monkeypatch.setattr(scanner, "load_sources_meta", lambda: {url: {"name": "teste"}})
    monkeypatch.setattr(scanner, "FEED_FETCH_JITTER_MIN", 0.0)
    monkeypatch.setattr(scanner, "FEED_FETCH_JITTER_MAX", 0.0)
    monkeypatch.setattr(scanner, "FEED_FETCH_MAX_RETRIES", 1)
    monkeypatch.setattr(scanner, "PAUSA_ENTRE_ENVIOS_S", 0)

    async def rede_ok():
        return True

    async def vazio(*a, **k):
        return []

    async def sem_og(*a, **k):
        return None, None

    async def sem_node_red(*a, **k):
        return None

    monkeypatch.setattr(scanner, "check_network_connectivity", rede_ok)
    monkeypatch.setattr(scanner, "fetch_nvd_cves", vazio)
    monkeypatch.setattr(scanner.ThreatService, "get_otx_pulses", staticmethod(vazio))
    monkeypatch.setattr(scanner, "fetch_og_media", sem_og)
    monkeypatch.setattr(scanner, "_push_node_red", sem_node_red)
    monkeypatch.setattr(scanner, "mark_news_as_sent", lambda *a, **k: None)
    monkeypatch.setattr(scanner, "check_official_sites", _html_nao_configurado)
    yield srv, url
    await server.close()


async def _html_nao_configurado(estado):
    return [], estado, scanner.ESTADO_NAO_CONFIGURADO


def _config(*guilds):
    cfg = {str(gid): {"channel_id": cid, "filters": ["todos"]} for gid, cid in guilds}
    with open(p("config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def _state():
    with open(p("state.json"), encoding="utf-8") as f:
        return json.load(f)


def _history():
    with open(p("history.json"), encoding="utf-8") as f:
        return json.load(f)


async def test_entrega_ok_grava_etag_e_nao_reposta(ambiente):
    srv, url = ambiente
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    canal = Canal(100)
    _config((1, 100))
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    assert len(canal.enviados) == 1
    assert _state()["http_cache"][url]["etag"] == '"v1"'
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    assert srv.pedidos[-1].get("If-None-Match") == '"v1"'
    assert len(canal.enviados) == 1


async def test_falha_de_entrega_nao_grava_cache_nem_history(ambiente):
    srv, url = ambiente
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    _config((1, 100))
    await scanner.run_scan_once(Bot([Canal(100, falha=True)]), trigger="teste")
    st = _state()
    assert url not in st["http_cache"]
    assert "https://news.example.com/a1" not in _history()
    assert "https://news.example.com/a1" in st["pendentes"]
    assert st["_meta"]["ultimo_veredito"]["veredito"] == "ANOMALIA"
    canal_ok = Canal(100)
    await scanner.run_scan_once(Bot([canal_ok]), trigger="teste")
    assert len(canal_ok.enviados) == 1
    assert "https://news.example.com/a1" in _history()
    assert _state()["pendentes"] == {}


async def test_guild_que_recebeu_nao_recebe_de_novo_quando_outra_falhou(ambiente):
    srv, url = ambiente
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    _config((1, 100), (2, 200))
    a, b_ruim = Canal(100), Canal(200, falha=True)
    await scanner.run_scan_once(Bot([a, b_ruim]), trigger="teste")
    assert len(a.enviados) == 1
    assert _state()["pendentes"]["https://news.example.com/a1"]["guilds_ok"] == ["1"]
    b_bom = Canal(200)
    await scanner.run_scan_once(Bot([a, b_bom]), trigger="teste")
    assert len(a.enviados) == 1
    assert len(b_bom.enviados) == 1
    assert "https://news.example.com/a1" in _history()


async def test_partida_a_frio_nao_publica_historico_antigo_nem_sem_data(ambiente):
    srv, url = ambiente
    srv.xml = _rss([
        ("Ransomware recente", "https://news.example.com/novo", RECENTE, TEXTO_CYBER),
        ("Ransomware velho", "https://news.example.com/velho", ANTIGO, TEXTO_CYBER),
        ("Ransomware sem data", "https://news.example.com/semdata", None, TEXTO_CYBER),
    ])
    canal = Canal(100)
    _config((1, 100))
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    titulos = [e["embed"].title for e in canal.enviados]
    assert titulos == ["Ransomware recente"]
    assert "https://news.example.com/semdata" in _state()["sem_data_vistos"]


async def test_item_sem_data_nao_volta_depois_que_o_ttl_do_history_vence(ambiente):
    """Sem data não há filtro de idade: vencido o TTL do history, só o registro sem_data impede a repostagem."""
    srv, url = ambiente
    srv.xml = _rss([("Ransomware recente", "https://news.example.com/novo", RECENTE, TEXTO_CYBER)])
    canal = Canal(100)
    _config((1, 100))
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    srv.xml = _rss([("Ransomware sem data", "https://news.example.com/semdata", None, TEXTO_CYBER)])

    def _esquece_cache_e_envelhece():
        st = _state()
        st["http_cache"] = {}
        for link in st.get("history_seen_at", {}):
            st["history_seen_at"][link] = 0
        with open(p("state.json"), "w", encoding="utf-8") as f:
            json.dump(st, f)

    _esquece_cache_e_envelhece()
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    _esquece_cache_e_envelhece()
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    assert [e["embed"].title for e in canal.enviados].count("Ransomware sem data") == 1


async def test_bypass_publica_no_maximo_uma(ambiente):
    srv, url = ambiente
    srv.xml = _rss([
        (f"Ransomware {i}", f"https://news.example.com/b{i}", RECENTE, TEXTO_CYBER) for i in range(5)
    ])
    canal = Canal(100)
    _config((1, 100))
    await scanner.run_scan_once(Bot([canal]), trigger="teste", bypass_cache=True)
    assert len(canal.enviados) == 1


async def test_sem_guild_emite_anomalia_e_bate(ambiente):
    srv, url = ambiente
    await scanner.run_scan_once(Bot([]), trigger="teste")
    ver = _state()["_meta"]["ultimo_veredito"]
    assert ver["veredito"] == "ANOMALIA"
    assert any("guild" in m for m in ver["motivos"])
    with open(p("heartbeat.json"), encoding="utf-8") as f:
        assert json.load(f)["veredito"] == "ANOMALIA"


async def test_fonte_404_e_contada_como_falha(ambiente):
    srv, url = ambiente
    srv.status = 404
    _config((1, 100))
    await scanner.run_scan_once(Bot([Canal(100)]), trigger="teste")
    met = _state()["_meta"]["ultimo_veredito"]["metricas"]
    assert met["fontes_falha"] == 1 and met["fontes_ok"] == 0


async def test_200_sem_entradas_e_vazia_nao_ok(ambiente):
    srv, url = ambiente
    srv.xml = _rss([])
    _config((1, 100))
    await scanner.run_scan_once(Bot([Canal(100)]), trigger="teste")
    met = _state()["_meta"]["ultimo_veredito"]["metricas"]
    assert met["fontes_vazias"] == 1 and met["fontes_ok"] == 0


async def test_imagem_invalida_nao_impede_a_noticia(ambiente, monkeypatch):
    srv, url = ambiente

    async def og_quebrada(*a, **k):
        return "javascript:alert(1)", None

    monkeypatch.setattr(scanner, "fetch_og_media", og_quebrada)
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    canal = Canal(100)
    _config((1, 100))
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    assert len(canal.enviados) == 1
    assert canal.enviados[0]["embed"].image.url is None


async def test_imagem_do_feed_vai_grande_e_absoluta(ambiente):
    srv, url = ambiente
    desc = TEXTO_CYBER + ' &lt;img src="/img/foto.jpg?a=1&amp;b=2" width="600"&gt;'
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, desc)])
    canal = Canal(100)
    _config((1, 100))
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    assert canal.enviados[0]["embed"].image.url == "https://news.example.com/img/foto.jpg?a=1&b=2"


async def test_video_do_youtube_sai_como_link_para_o_player(ambiente):
    srv, url = ambiente
    srv.xml = _rss([("Malware analysis", "https://www.youtube.com/watch?v=abc123", RECENTE, TEXTO_CYBER)])
    canal = Canal(100)
    _config((1, 100))
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    assert canal.enviados[0]["embed"] is None
    assert "https://www.youtube.com/watch?v=abc123" in canal.enviados[0]["content"]
