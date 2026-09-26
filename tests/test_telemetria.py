"""Telemetria de ausência: cada regra com o cenário que alarma e o gêmeo que tem de ficar calado."""
import pytest

from core.telemetria import (
    VEREDITO_ANOMALIA, VEREDITO_ATENCAO, VEREDITO_OK, avaliar_varredura, metricas_vazias,
)


def _m(**kw):
    base = metricas_vazias()
    base.update(guilds_configuradas=3, fontes_total=40, fontes_ok=36, fontes_304=4, enviadas=5)
    base.update(kw)
    return base


def _ok(r):
    assert all(isinstance(x, str) and x.strip() for x in r["motivos"]), r
    return r["veredito"]


def test_saudavel_e_ok_com_motivo():
    assert _ok(avaliar_varredura(_m(), 0)) == VEREDITO_OK


def test_zero_legitimo_e_dito():
    r = avaliar_varredura(_m(enviadas=0), 1)
    assert _ok(r) == VEREDITO_OK
    assert any("0 publicadas" in x for x in r["motivos"])


@pytest.mark.parametrize("horas,esperado", [(11.9, VEREDITO_OK), (12, VEREDITO_ATENCAO), (47.9, VEREDITO_ATENCAO), (48, VEREDITO_ANOMALIA)])
def test_tempo_sem_envio_limiares(horas, esperado):
    assert _ok(avaliar_varredura(_m(enviadas=0), horas)) == esperado


def test_tempo_sem_envio_nao_conta_quando_houve_envio():
    assert _ok(avaliar_varredura(_m(enviadas=1), 100)) == VEREDITO_OK


@pytest.mark.parametrize("falha,vazia,esperado", [
    (9, 0, VEREDITO_OK), (10, 0, VEREDITO_ATENCAO), (5, 5, VEREDITO_ATENCAO), (20, 0, VEREDITO_ANOMALIA),
])
def test_proporcao_de_fontes_mudas(falha, vazia, esperado):
    assert _ok(avaliar_varredura(_m(fontes_falha=falha, fontes_vazias=vazia), 0)) == esperado


def test_catalogo_vazio_e_sem_guild_sao_anomalia():
    assert _ok(avaliar_varredura(_m(fontes_total=0), 0)) == VEREDITO_ANOMALIA
    assert _ok(avaliar_varredura(_m(guilds_configuradas=0), 0)) == VEREDITO_ANOMALIA


def test_abortada_por_rede_e_atencao_e_nunca_ok():
    r = avaliar_varredura(_m(enviadas=0), 0, abortada="rede indisponível")
    assert _ok(r) == VEREDITO_ATENCAO
    assert any("rede" in x for x in r["motivos"])


def test_falha_de_entrega_sem_nenhum_envio_e_anomalia_com_envio_e_atencao():
    assert _ok(avaliar_varredura(_m(enviadas=0, falhas_entrega=2), 0)) == VEREDITO_ANOMALIA
    assert _ok(avaliar_varredura(_m(enviadas=3, falhas_entrega=1), 0)) == VEREDITO_ATENCAO


def test_canal_invisivel_alarma():
    assert _ok(avaliar_varredura(_m(canais_nao_resolvidos=1), 0)) == VEREDITO_ATENCAO


def test_sem_data_por_proporcao_e_com_minimo():
    assert _ok(avaliar_varredura(_m(itens_examinados=20, itens_sem_data=10), 0)) == VEREDITO_ATENCAO
    assert _ok(avaliar_varredura(_m(itens_examinados=20, itens_sem_data=9), 0)) == VEREDITO_OK
    assert _ok(avaliar_varredura(_m(itens_examinados=4, itens_sem_data=4), 0)) == VEREDITO_OK


@pytest.mark.parametrize("ruim", [{"enviadas": -1}, {"enviadas": "x"}, {"fontes_total": None}])
def test_contador_invalido_e_anomalia(ruim):
    r = avaliar_varredura(_m(**ruim), 0)
    assert _ok(r) == VEREDITO_ANOMALIA
    assert "inválidos" in r["motivos"][0]


def test_horas_invalidas_e_anomalia():
    assert _ok(avaliar_varredura(_m(), -1)) == VEREDITO_ANOMALIA
