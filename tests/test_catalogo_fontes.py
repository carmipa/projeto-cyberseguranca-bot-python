"""
Guardas estruturais do catálogo (data/sources.json).

Em 2026-08-30 e de novo em 2026-09-26: 10 fontes do YouTube apontavam para a
PÁGINA do canal (feedparser rende zero entradas) com status "✅ Validated", e o
channel_id do NetworkChuck entregava o canal Computerphile.
"""
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from core.scanner import load_sources

CATALOGO = Path(__file__).resolve().parents[1] / "data" / "sources.json"


def _itens(secao):
    d = json.loads(CATALOGO.read_text(encoding="utf-8"))
    v = d.get(secao, [])
    if isinstance(v, dict):
        for grupo in v.values():
            yield from (i for i in grupo if isinstance(i, dict))
    else:
        yield from (i for i in v if isinstance(i, dict))


def test_youtube_e_feed_atom_com_channel_id_coerente():
    for it in _itens("youtube_feeds"):
        if it.get("enabled") is False:
            continue
        u = urlparse(it["url"])
        assert u.netloc == "www.youtube.com" and u.path == "/feeds/videos.xml", it["name"]
        assert parse_qs(u.query).get("channel_id") == [it["channel_id"]], it["name"]
        assert re.fullmatch(r"UC[0-9A-Za-z_-]{22}", it["channel_id"]), it["name"]


def test_desativada_tem_motivo_e_ativa_nao_tem():
    for secao in ("rss_feeds", "youtube_feeds"):
        for it in _itens(secao):
            if it.get("enabled") is False:
                assert str(it.get("motivo_desativacao", "")).strip(), it["name"]
            else:
                assert "motivo_desativacao" not in it, it["name"]


def test_load_sources_exclui_desativadas_e_nao_duplica():
    urls = load_sources()
    ativas = [it["url"] for s in ("rss_feeds", "youtube_feeds") for it in _itens(s) if it.get("enabled") is not False]
    desativadas = {it["url"] for s in ("rss_feeds", "youtube_feeds") for it in _itens(s) if it.get("enabled") is False}
    assert sorted(urls) == sorted(set(ativas))
    assert not desativadas & set(urls)
    assert len(urls) == len(set(urls))
    assert len(urls) >= 30


@pytest.mark.parametrize("secao", ["rss_feeds", "youtube_feeds"])
def test_url_http_e_nome_presente(secao):
    for it in _itens(secao):
        assert it["url"].startswith(("http://", "https://")), it
        assert str(it.get("name", "")).strip(), it


def test_impressao_do_catalogo_distingue_real_de_ausente(tmp_path, monkeypatch):
    from core.scanner import impressao_do_catalogo
    real = impressao_do_catalogo()
    assert real["fontes"] >= 30 and len(real["sha"]) == 16
    monkeypatch.setenv("CATALOG_DIR", str(tmp_path))
    ausente = impressao_do_catalogo()
    assert ausente["fontes"] == 0 and ausente["sha"] == "" and not ausente["existe"]


def test_requirements_da_raiz_e_do_deploy_sao_iguais():
    raiz = Path(__file__).resolve().parents[1]
    a = (raiz / "requirements.txt").read_text(encoding="utf-8").split()
    b = (raiz / "deploy" / "requirements.txt").read_text(encoding="utf-8").split()
    assert a == b
    assert not any("deep-translator" in x for x in a)
