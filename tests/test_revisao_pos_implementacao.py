"""
Guardas dos achados da revisão pós-implementação de 2026-09-26 (três revisores
independentes: adversarial, boa-fé, falha operacional). Cada teste reproduz o
cenário descrito pelo revisor e fixa o comportamento corrigido.
"""
import json
import os
import time
from datetime import timedelta
from types import SimpleNamespace

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

import bot.permissoes as perm
import core.scanner as scanner
import utils.storage as storage
from tests.test_scan_engine import (  # noqa: F401  (fixture reaproveitada)
    AGORA, RECENTE, TEXTO_CYBER, Bot, Canal, _config, _history, _rss, _state, ambiente,
)
from utils.security import imagem_publicavel, is_private_ip
from utils.storage import load_json_safe, p

pytestmark = pytest.mark.asyncio


def _forbidden():
    return discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), {"code": 50013, "message": "Missing Permissions"})


def _http(status, code, cls=discord.HTTPException):
    return cls(SimpleNamespace(status=status, reason="x"), {"code": code, "message": "simulado"})


class CanalQueLevanta(Canal):
    def __init__(self, cid, fabrica, so_para=None):
        super().__init__(cid)
        self.fabrica = fabrica
        self.so_para = so_para
        self.tentativas = 0

    async def send(self, **kw):
        self.tentativas += 1
        embed = kw.get("embed")
        if self.so_para is None or (embed is not None and self.so_para in (embed.title or "")):
            raise self.fabrica()
        await Canal.send(self, **kw)


class CanalProibido(Canal):
    async def send(self, **kw):
        raise _forbidden()


class CanalContador(Canal):
    """Falha transitória contando tentativas."""

    def __init__(self, cid):
        super().__init__(cid, falha=True)
        self.tentativas = 0

    async def send(self, **kw):
        self.tentativas += 1
        raise RuntimeError("503 Service Unavailable (simulado)")


def _envelhece_e_esquece_cache(horas_atras):
    st = _state()
    st["http_cache"] = {}
    for link in st.get("history_seen_at", {}):
        st["history_seen_at"][link] = time.time() - horas_atras * 3600
    with open(p("state.json"), "w", encoding="utf-8") as f:
        json.dump(st, f)


async def test_guild_sem_permissao_nao_vira_pendencia_nem_trava_o_cache(ambiente):
    srv, url = ambiente
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    _config((1, 100), (2, 200))
    bom = Canal(100)
    await scanner.run_scan_once(Bot([bom, CanalProibido(200)]), trigger="teste")
    st = _state()
    assert len(bom.enviados) == 1
    assert st["pendentes"] == {}
    assert url in st["http_cache"]
    assert "https://news.example.com/a1" in _history()
    assert st["_meta"]["ultimo_veredito"]["metricas"]["canais_sem_permissao"] == 1
    assert st["_meta"]["guilds_sem_permissao"] == ["2"]


async def test_link_com_espaco_e_codificado_e_link_invalido_nao_derruba_os_outros(ambiente):
    srv, url = ambiente
    srv.xml = _rss([
        ("Ransomware espaco", "https://news.example.com/noticia com espaco", RECENTE, TEXTO_CYBER),
        ("Ransomware js", "javascript:alert(1)", RECENTE, TEXTO_CYBER),
        ("Ransomware relativo", "/relativa", RECENTE, TEXTO_CYBER),
    ])
    canal = Canal(100)
    _config((1, 100))
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    # O relativo resolve contra o feed (aqui 127.0.0.1) e é recusado pela
    # checagem anti-SSRF — o que prova que ele não chega cru ao embed.
    assert [e["embed"].url for e in canal.enviados] == ["https://news.example.com/noticia%20com%20espaco"]


async def test_link_relativo_resolve_contra_a_fonte():
    from urllib.parse import urljoin
    assert urljoin("https://site.com/feed/", "/artigo 1".replace(" ", "%20")) == "https://site.com/artigo%201"


async def test_item_de_quase_sete_dias_nao_volta_quando_o_ttl_antigo_venceria(ambiente):
    srv, url = ambiente
    quase_sete = AGORA - timedelta(days=6, hours=20)
    srv.xml = _rss([("Ransomware velho", "https://news.example.com/v1", quase_sete, TEXTO_CYBER)])
    canal = Canal(100)
    _config((1, 100))
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    _envelhece_e_esquece_cache(169)
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    assert len(canal.enviados) == 1


async def test_post_latest_com_canais_quebrados_nao_enfileira_o_feed(ambiente):
    srv, url = ambiente
    srv.xml = _rss([(f"Ransomware {i}", f"https://news.example.com/b{i}", RECENTE, TEXTO_CYBER) for i in range(6)])
    _config((1, 100))
    ruim = CanalContador(100)
    await scanner.run_scan_once(Bot([ruim]), trigger="teste", bypass_cache=True)
    assert ruim.tentativas == 1
    assert _state()["pendentes"] == {}


async def test_disjuntor_limita_tentativas_de_guild_em_falha_transitoria(ambiente):
    srv, url = ambiente
    srv.xml = _rss([(f"Ransomware {i}", f"https://news.example.com/c{i}", RECENTE, TEXTO_CYBER) for i in range(8)])
    _config((1, 100), (2, 200))
    bom, ruim = Canal(100), CanalContador(200)
    await scanner.run_scan_once(Bot([bom, ruim]), trigger="teste")
    assert len(bom.enviados) == 8
    assert ruim.tentativas == scanner.FALHAS_TRANSITORIAS_POR_GUILD
    assert len(_state()["pendentes"]) == 8


async def test_pendencia_orfa_e_consolidada_e_nao_reposta(ambiente):
    srv, url = ambiente
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    _config((1, 100), (2, 200))
    a = Canal(100)
    await scanner.run_scan_once(Bot([a, Canal(200, falha=True)]), trigger="teste")
    _config((1, 100))
    _envelhece_e_esquece_cache(0)
    await scanner.run_scan_once(Bot([a]), trigger="teste")
    _envelhece_e_esquece_cache(0)
    await scanner.run_scan_once(Bot([a]), trigger="teste")
    assert len(a.enviados) == 1
    assert "https://news.example.com/a1" in _history()


async def test_dados_nao_graveis_suspendem_envios(ambiente, monkeypatch):
    srv, url = ambiente
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    _config((1, 100))
    monkeypatch.setattr(scanner, "save_json_safe", lambda *a, **k: False)
    monkeypatch.setattr(scanner, "save_history", lambda *a, **k: False)
    canal = Canal(100)
    await scanner.run_scan_once(Bot([canal]), trigger="teste")
    assert canal.enviados == []
    assert scanner.stats.ultimo_veredito["veredito"] == "ANOMALIA"


async def test_disco_quase_cheio_nao_envia_nada(ambiente, monkeypatch):
    """Arquivo pequeno grava, state/history não: nenhum envio (antes: 1 repostagem por ciclo)."""
    srv, url = ambiente
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    _config((1, 100))
    real = scanner.save_json_safe
    monkeypatch.setattr(scanner, "save_json_safe", lambda caminho, *a, **k: False if caminho.endswith("state.json") else real(caminho, *a, **k))
    monkeypatch.setattr(scanner, "save_history", lambda *a, **k: False)
    canal = Canal(100)
    for _ in range(3):
        await scanner.run_scan_once(Bot([canal]), trigger="teste")
    assert canal.enviados == []


async def test_estado_gravado_a_cada_noticia_entregue(ambiente):
    srv, url = ambiente
    srv.xml = _rss([
        ("Ransomware um", "https://news.example.com/n1", RECENTE, TEXTO_CYBER),
        ("Ransomware dois", "https://news.example.com/n2", RECENTE - timedelta(minutes=5), TEXTO_CYBER),
    ])
    _config((1, 100))
    vistos_no_disco = []

    class CanalEspiao(Canal):
        async def send(self, **kw):
            if self.enviados:
                with open(p("history.json"), encoding="utf-8") as f:
                    vistos_no_disco.extend(json.load(f))
            await super().send(**kw)

    await scanner.run_scan_once(Bot([CanalEspiao(100)]), trigger="teste")
    assert len(vistos_no_disco) == 1


async def test_batimento_registra_desconexao_e_healthcheck_reprova(ambiente, monkeypatch):
    srv, url = ambiente
    _config((1, 100))
    bot = Bot([Canal(100)])
    bot.is_ready = lambda: False
    bot.is_closed = lambda: True
    await scanner.run_scan_once(bot, trigger="teste")
    with open(p("heartbeat.json"), encoding="utf-8") as f:
        assert json.load(f)["conectado"] is False
    import importlib.util
    spec = importlib.util.spec_from_file_location("hc", os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "healthcheck.py"))
    hc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hc)
    assert hc.main() == 1
    bot.is_ready = lambda: True
    bot.is_closed = lambda: False
    bot.latency = float("inf")
    await scanner.run_scan_once(bot, trigger="teste")
    assert hc.main() == 1
    bot.latency = 0.08
    await scanner.run_scan_once(bot, trigger="teste")
    assert hc.main() == 0


async def test_batimento_zerado_no_arranque():
    from utils.heartbeat import bater, zerar
    bater("OK", conectado=True)
    assert os.path.exists(p("heartbeat.json"))
    zerar()
    assert not os.path.exists(p("heartbeat.json"))


async def test_admin_de_guild_nao_recebe_motivos_globais(monkeypatch):
    async def varre(bot, **k):
        scanner.stats.ultimo_veredito = {"veredito": "ATENCAO", "motivos": ["2 guild(s) com canal que o bot não enxerga"]}

    monkeypatch.setattr(perm, "_ultima_manual", 0.0)
    monkeypatch.setattr(scanner, "run_scan_once", varre)
    ok, texto = await perm.solicitar_varredura_manual(None, "a")
    assert ok and "ATENCAO" in texto and "guild" not in texto
    monkeypatch.setattr(perm, "_ultima_manual", 0.0)
    ok, texto = await perm.solicitar_varredura_manual(None, "b", detalhado=True)
    assert "guild" in texto


async def test_dono_ignora_intervalo_admin_nao(monkeypatch):
    async def varre(bot, **k):
        return None

    monkeypatch.setattr(scanner, "run_scan_once", varre)
    monkeypatch.setattr(perm, "_ultima_manual", time.monotonic())
    assert (await perm.solicitar_varredura_manual(None, "x"))[0] is False
    assert (await perm.solicitar_varredura_manual(None, "x", ignora_intervalo=True))[0] is True


def _escreve(caminho, texto):
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


async def test_arquivo_zero_byte_recupera_do_backup(dados_isolados):
    pasta = dados_isolados / "backups"
    pasta.mkdir()
    _escreve(pasta / "history.json_20260925_000000_auto.json.backup", json.dumps(["bom"]))
    _escreve(p("history.json"), "")
    assert load_json_safe(p("history.json"), "PADRAO") == ["bom"]


async def test_backup_mais_novo_vence_emergencia_velha(dados_isolados):
    pasta = dados_isolados / "backups"
    pasta.mkdir()
    emergencia = p("history.json") + ".backup"
    _escreve(emergencia, json.dumps(["VELHO"]))
    t = time.time() - 90 * 86400
    os.utime(emergencia, (t, t))
    _escreve(pasta / "history.json_20260926_000000_auto.json.backup", json.dumps(["NOVO"]))
    _escreve(p("history.json"), "[corrompido")
    assert load_json_safe(p("history.json"), "PADRAO") == ["NOVO"]


async def test_emergencia_mais_nova_ainda_vence(dados_isolados):
    pasta = dados_isolados / "backups"
    pasta.mkdir()
    auto = pasta / "history.json_20260101_000000_auto.json.backup"
    _escreve(auto, json.dumps(["AUTO_VELHO"]))
    t = time.time() - 90 * 86400
    os.utime(auto, (t, t))
    _escreve(p("history.json") + ".backup", json.dumps(["EMERGENCIA_NOVA"]))
    _escreve(p("history.json"), "[corrompido")
    assert load_json_safe(p("history.json"), "PADRAO") == ["EMERGENCIA_NOVA"]


@pytest.mark.parametrize("host", ["2002:7f00:1::", "64:ff9b::7f00:1", "2002:0a00:0001::"])
async def test_ipv6_que_embute_ipv4_privado_e_recusado(host):
    assert is_private_ip(host)
    assert imagem_publicavel(f"http://[{host}]/x.jpg") is None


async def test_ipv6_que_embute_ipv4_publico_passa():
    assert not is_private_ip("2002:0808:0808::")
    assert not is_private_ip("64:ff9b::808:808")


async def test_html_monitor_nao_segue_redirecionamento(monkeypatch):
    import core.html_monitor as hm

    async def permite(url):
        return True, None

    monkeypatch.setattr(hm, "resolve_para_publico", permite)
    app = web.Application()

    async def redir(request):
        raise web.HTTPFound("/interno")

    async def interno(request):
        return web.Response(text="<title>SEGREDO</title>", content_type="text/html")

    app.router.add_get("/", redir)
    app.router.add_get("/interno", interno)
    server = TestServer(app)
    await server.start_server()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            _, titulo, h = await hm.fetch_page_hash(s, str(server.make_url("/")))
            assert titulo == "" and h == ""
            _, titulo_ok, h_ok = await hm.fetch_page_hash(s, str(server.make_url("/interno")))
            assert titulo_ok == "SEGREDO" and h_ok
    finally:
        await server.close()


async def test_conteudo_recusado_nao_apaga_a_entrega_das_outras_noticias(ambiente):
    """3 itens com 50035 não podem disparar o disjuntor e apagar os 5 bons (2ª revisão adversarial)."""
    srv, url = ambiente
    itens = [(f"Ransomware ruim {i}", f"https://news.example.com/r{i}", RECENTE, TEXTO_CYBER) for i in range(3)]
    itens += [(f"Ransomware bom {i}", f"https://news.example.com/g{i}", RECENTE - timedelta(minutes=i + 1), TEXTO_CYBER) for i in range(5)]
    srv.xml = _rss(itens)
    _config((1, 100), (2, 200))
    a = CanalQueLevanta(100, lambda: _http(400, 50035), so_para="ruim")
    b = CanalQueLevanta(200, lambda: _http(400, 50035), so_para="ruim")
    await scanner.run_scan_once(Bot([a, b]), trigger="teste")
    assert len(a.enviados) == 5 and len(b.enviados) == 5
    st = _state()
    assert st["pendentes"] == {}
    assert st["_meta"]["ultimo_veredito"]["metricas"]["itens_recusados_discord"] == 3


async def test_403_de_borda_sem_codigo_e_transitorio_e_nao_consolida(ambiente):
    srv, url = ambiente
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    _config((1, 100))
    borda = CanalQueLevanta(100, lambda: _http(403, 0, discord.Forbidden))
    await scanner.run_scan_once(Bot([borda]), trigger="teste")
    assert "https://news.example.com/a1" in _state()["pendentes"]
    assert "https://news.example.com/a1" not in _history()
    ok = Canal(100)
    _envelhece_e_esquece_cache(0)
    await scanner.run_scan_once(Bot([ok]), trigger="teste")
    assert len(ok.enviados) == 1


async def test_guild_sem_permissao_custa_uma_tentativa_por_varredura(ambiente):
    srv, url = ambiente
    srv.xml = _rss([(f"Ransomware {i}", f"https://news.example.com/p{i}", RECENTE, TEXTO_CYBER) for i in range(6)])
    _config((1, 100), (2, 200))
    bom = Canal(100)
    proibido = CanalQueLevanta(200, _forbidden)
    await scanner.run_scan_once(Bot([bom, proibido]), trigger="teste")
    assert len(bom.enviados) == 6
    assert proibido.tentativas == 1


async def test_canal_momentaneamente_invisivel_mantem_a_pendencia(ambiente):
    srv, url = ambiente
    srv.xml = _rss([("Ransomware hits", "https://news.example.com/a1", RECENTE, TEXTO_CYBER)])
    _config((1, 100), (2, 200))
    a = Canal(100)
    await scanner.run_scan_once(Bot([a, Canal(200, falha=True)]), trigger="teste")
    _envelhece_e_esquece_cache(0)
    await scanner.run_scan_once(Bot([a]), trigger="teste")  # guild 2 some por um instante
    assert "https://news.example.com/a1" in _state()["pendentes"]
    b = Canal(200)
    _envelhece_e_esquece_cache(0)
    await scanner.run_scan_once(Bot([a, b]), trigger="teste")
    assert len(a.enviados) == 1 and len(b.enviados) == 1


@pytest.mark.parametrize("host", ["64:ff9b:1::a9fe:a9fe", "::7f00:1"])
async def test_nat64_local_e_ipv6_compativel_recusados(host):
    assert is_private_ip(host)


async def test_admin_da_guild_recusada_e_avisado(monkeypatch):
    async def varre(bot, **k):
        scanner.stats.ultimo_veredito = {"veredito": "ATENCAO", "motivos": ["x"]}

    with open(p("state.json"), "w", encoding="utf-8") as f:
        json.dump({"_meta": {"guilds_sem_permissao": ["7"]}}, f)
    monkeypatch.setattr(perm, "_ultima_manual", 0.0)
    monkeypatch.setattr(scanner, "run_scan_once", varre)
    _, texto = await perm.solicitar_varredura_manual(None, "a", guild_id=7)
    assert "ESTE servidor" in texto
    monkeypatch.setattr(perm, "_ultima_manual", 0.0)
    _, texto = await perm.solicitar_varredura_manual(None, "a", guild_id=8)
    assert "ESTE servidor" not in texto
