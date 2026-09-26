"""
Guardas de imagem do embed e de SSRF (portadas dos bots irmãos, 2026-09-18).
Cada caso doente tem ao lado o legítimo que carrega o mesmo sinal (A1).
"""
import pytest
import pytest_asyncio
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

import utils.opengraph as og
from core.scanner import _img_candidata, build_news_embed, extrair_imagem_do_feed
from utils.security import imagem_publicavel, is_private_ip, resolve_para_publico, validate_url

import discord


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "data:image/png;base64,AAAA",
    "/relativa/foto.jpg",
    "http://127.0.0.1/x.jpg",
    "http://127.1/x.jpg",
    "http://2130706433/x.jpg",
    "http://[::1]/x.jpg",
    "http://user@10.0.0.1/x.jpg",
    "http://169.254.169.254/latest/meta-data",
    "http://100.64.0.1/x.jpg",
    "http://printer.local/x.jpg",
    "https://cdn.example.com/foto com espaco.jpg",
    "https://nvd.nist.gov/site-media/images/NIST_logo.svg?v=1",
    "",
    None,
])
def test_imagem_recusada(url):
    assert imagem_publicavel(url) is None


@pytest.mark.parametrize("url", [
    "https://cdn.example.com/foto.jpg",
    "https://cdn.example.com/icon-of-ransomware.jpg",
    "http://8.8.8.8/grafico.png",
    "https://i.ytimg.com/vi/abc/hqdefault.jpg?a=1&b=2",
])
def test_imagem_legitima_de_mesmo_sinal_aceita(url):
    assert imagem_publicavel(url) == url


def test_is_private_ip_grafias():
    assert is_private_ip("0x7f.0.0.1")
    assert is_private_ip("0177.0.0.1")
    assert is_private_ip("::ffff:127.0.0.1")
    assert not is_private_ip("8.8.8.8")
    assert not is_private_ip("exemplo.com")


def test_validate_url_devolve_motivo():
    ok, motivo = validate_url("http://localhost/x")
    assert not ok and "local" in motivo
    assert validate_url("https://exemplo.com/x") == (True, None)


@pytest.mark.asyncio
async def test_resolve_para_publico_literal():
    assert (await resolve_para_publico("http://127.0.0.1/"))[0] is False
    assert (await resolve_para_publico("http://8.8.8.8/"))[0] is True


@pytest.mark.parametrize("tag", [
    '<img src="https://t.example.com/p.gif" width="1" height="1">',
    '<img src="data:image/gif;base64,R0lG">',
    '<img src="https://example.com/share-icon.png">',
    '<img src="https://feeds.feedburner.com/~r/x/~4/abc">',
])
def test_img_candidata_descarta_enfeite(tag):
    assert _img_candidata(tag) == ""


@pytest.mark.parametrize("tag,esperado", [
    ('<img src="https://example.com/comiconline.jpg">', "https://example.com/comiconline.jpg"),
    ('<img src="data:image/gif;base64,R0" data-src="https://example.com/real.jpg">', "https://example.com/real.jpg"),
    ('<img srcset="https://example.com/a.jpg 1x, https://example.com/b.jpg 2x">', "https://example.com/a.jpg"),
    ('<img src="https://example.com/f.jpg" width="640">', "https://example.com/f.jpg"),
])
def test_img_candidata_aceita_foto(tag, esperado):
    assert _img_candidata(tag) == esperado


def test_extrair_do_feed_precedencia_e_absoluta():
    entry = {
        "media_thumbnail": [{"url": "/thumbs/a.jpg"}],
        "summary": '<img src="https://example.com/outra.jpg">',
    }
    assert extrair_imagem_do_feed(entry, "https://news.example.com/artigo", entry["summary"]) == \
        "https://news.example.com/thumbs/a.jpg"


def test_extrair_do_feed_ignora_media_content_de_video():
    entry = {"media_content": [{"url": "https://example.com/v.mp4", "type": "video/mp4"}]}
    assert extrair_imagem_do_feed(entry, "https://x.com/a", "") == ""
    entry_img = {"media_content": [{"url": "https://example.com/i.jpg", "type": "image/jpeg"}]}
    assert extrair_imagem_do_feed(entry_img, "https://x.com/a", "") == "https://example.com/i.jpg"


def test_extrair_do_feed_enclosure_e_entidade():
    entry = {"links": [{"rel": "enclosure", "type": "image/png", "href": "https://e.com/i.png?a=1&amp;b=2"}]}
    assert extrair_imagem_do_feed(entry, "https://e.com/a", "") == "https://e.com/i.png?a=1&b=2"


def test_embed_sem_imagem_quando_invalida_e_com_imagem_quando_valida():
    base = dict(titulo="T" * 300, resumo="R", link="https://e.com/a", embed_color=discord.Color.red(),
                author_prefix="X", entry_dt=None, video="")
    ruim, descartada = build_news_embed(None, imagem="javascript:alert(1)", **base)
    assert ruim.image.url is None and descartada is True
    bom, descartada = build_news_embed(None, imagem="https://e.com/i.jpg", **base)
    assert bom.image.url == "https://e.com/i.jpg" and descartada is False
    assert len(bom.title) == 256


def test_embed_video_so_se_url_valida():
    base = dict(titulo="T", resumo="R", link="https://e.com/a", embed_color=discord.Color.red(),
                author_prefix="X", entry_dt=None, imagem="")
    ruim, _ = build_news_embed(None, video="http://127.0.0.1/v.mp4", **base)
    assert not any(f.name.startswith("🎬") for f in ruim.fields)
    bom, _ = build_news_embed(None, video="https://e.com/v.mp4", **base)
    assert any(f.name.startswith("🎬") for f in bom.fields)


@pytest_asyncio.fixture
async def site(monkeypatch):
    async def permite(url):
        return True, None

    monkeypatch.setattr(og, "resolve_para_publico", permite)
    app = web.Application()

    async def artigo(request):
        return web.Response(
            text='<html><head><meta property="og:image" content="/img/capa.jpg?x=1&amp;y=2">'
                 '<meta property="og:video" content="https://e.com/v.mp4"></head></html>',
            content_type="text/html")

    async def redir_interno(request):
        # Destino que RESPONDERIA se fosse seguido (o próprio servidor, por
        # nome local): a guarda só passa se for a validação que o recusa.
        raise web.HTTPFound(f"http://localhost:{request.url.port}/artigo")

    async def redir_legitimo(request):
        raise web.HTTPFound("/artigo")

    app.router.add_get("/artigo", artigo)
    app.router.add_get("/redir-interno", redir_interno)
    app.router.add_get("/redir-legitimo", redir_legitimo)
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest.mark.asyncio
async def test_og_relativa_resolvida_e_entidade_decodificada_uma_vez(site, monkeypatch):
    monkeypatch.setattr(og, "validate_url", lambda u: (True, None))
    async with ClientSession() as s:
        img, video = await og.fetch_og_media(str(site.make_url("/artigo")), s)
    assert img == str(site.make_url("/img/capa.jpg")) + "?x=1&y=2"
    assert video == "https://e.com/v.mp4"


@pytest.mark.asyncio
async def test_og_redirect_para_rede_interna_recusado_e_legitimo_seguido(site, monkeypatch):
    reais = og.validate_url

    def valida(u):
        return (True, None) if u.startswith(str(site.make_url("/"))) else reais(u)

    monkeypatch.setattr(og, "validate_url", valida)
    async with ClientSession() as s:
        assert await og.fetch_og_media(str(site.make_url("/redir-interno")), s) == (None, None)
        img, _ = await og.fetch_og_media(str(site.make_url("/redir-legitimo")), s)
    assert img and img.endswith("/img/capa.jpg?x=1&y=2")


@pytest.mark.asyncio
async def test_og_link_interno_nunca_e_buscado():
    async with ClientSession() as s:
        assert await og.fetch_og_media("http://127.0.0.1:1/x", s) == (None, None)
