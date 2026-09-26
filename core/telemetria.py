"""
Telemetria de ausência: cada varredura fecha com veredito e MOTIVO.

Existe porque o painel só media sucesso: `feeds_failed` era declarado em
core/stats.py e nunca incrementado — um campo que sempre diz 0, indistinguível
de "nada falhou". Em produção (VPS, 29/08 a 26/09) 7 das 44 fontes falhavam em
toda varredura e o log fechava com `scan.done sent=0` sem distinguir "dia sem
notícia" de "fonte morta".

Portado da classe 3.6 do manutencao-de-bots (gundam/anime-news), com as regras
deste bot. Limiares de tempo declarados ANTES de qualquer ajuste (A8), como
heurística: não foram calibrados contra a distribuição real de produção.
"""
from datetime import datetime
from typing import Any, Dict, List

VEREDITO_OK = "OK"
VEREDITO_ATENCAO = "ATENCAO"
VEREDITO_ANOMALIA = "ANOMALIA"
_ORDEM = {VEREDITO_OK: 0, VEREDITO_ATENCAO: 1, VEREDITO_ANOMALIA: 2}

HORAS_SEM_ENVIO_ATENCAO = 12
HORAS_SEM_ENVIO_ANOMALIA = 48
PROPORCAO_MUDAS_ATENCAO = 0.25
PROPORCAO_MUDAS_ANOMALIA = 0.5
PROPORCAO_SEM_DATA_ATENCAO = 0.5
MINIMO_ITENS_PARA_PROPORCAO = 10

CONTADORES = (
    "guilds_configuradas", "fontes_total", "fontes_ok", "fontes_304", "fontes_falha",
    "fontes_vazias", "itens_examinados", "itens_sem_data", "enviadas",
    "falhas_entrega", "canais_nao_resolvidos",
)


def metricas_vazias() -> Dict[str, int]:
    """Contadores zerados de uma varredura."""
    return {k: 0 for k in CONTADORES}


def avaliar_varredura(
    metricas: Dict[str, Any],
    horas_sem_envio: float,
    abortada: str = "",
) -> Dict[str, Any]:
    """
    Veredito de uma varredura, medindo ausência e não só sucesso.

    PROPÓSITO DE NEGÓCIO:
        Distinguir "o bot funcionou e não havia notícia" de "o bot não tinha como
        achar notícia" (fonte morta, canal sumido, catálogo vazio, sem guild).

    INVARIANTES DO DOMÍNIO:
        - Veredito diferente de OK sempre traz ao menos um motivo NÃO VAZIO.
        - O zero legítimo é dito: "0 publicadas ... sem novidade" é motivo.
        - Proporção decide, não contador cru: 1 fonte muda em 44 é ruído.
        - Catálogo vazio, nenhuma guild e contador inválido são ANOMALIA, nunca OK.
        - `abortada` (varredura saiu antes de processar) nunca vira OK.
        - `horas_sem_envio` é medido pelo relógio desde o último envio
          registrado, não por contagem de ciclos (varredura manual no meio
          inflaria a contagem).

    COMPORTAMENTO EM CASO DE FALHA:
        Não levanta. Contador ausente, negativo ou não numérico devolve ANOMALIA
        com o motivo "contadores inválidos".
    """
    valores: Dict[str, int] = {}
    invalido = False
    for k in CONTADORES:
        try:
            v = int(metricas.get(k, 0))
        except (TypeError, ValueError, AttributeError):
            v = -1
        if v < 0:
            invalido = True
        valores[k] = v
    try:
        horas = float(horas_sem_envio)
    except (TypeError, ValueError):
        horas, invalido = -1.0, True
    if horas < 0:
        invalido = True

    agora = datetime.now().isoformat(timespec="seconds")
    if invalido:
        return {
            "veredito": VEREDITO_ANOMALIA,
            "motivos": ["contadores inválidos — a medição não é confiável"],
            "metricas": valores,
            "quando": agora,
        }

    motivos: List[str] = []
    veredito = VEREDITO_OK

    def sobe(novo: str, motivo: str) -> None:
        nonlocal veredito
        motivos.append(motivo)
        if _ORDEM[novo] > _ORDEM[veredito]:
            veredito = novo

    if valores["guilds_configuradas"] == 0:
        sobe(VEREDITO_ANOMALIA, "nenhuma guild com canal configurado — nada pode ser entregue")
    if valores["fontes_total"] == 0:
        sobe(VEREDITO_ANOMALIA, "catálogo vazio: nenhuma fonte foi carregada")
    if abortada:
        sobe(VEREDITO_ATENCAO if valores["guilds_configuradas"] and valores["fontes_total"] else VEREDITO_ANOMALIA,
             f"varredura interrompida antes de processar: {abortada}")

    total = valores["fontes_total"]
    if total > 0 and not abortada:
        mudas = valores["fontes_falha"] + valores["fontes_vazias"]
        proporcao = mudas / total
        texto = (f"{mudas} de {total} fontes não entregaram nada "
                 f"({valores['fontes_falha']} falharam, {valores['fontes_vazias']} responderam vazias)")
        if proporcao >= PROPORCAO_MUDAS_ANOMALIA:
            sobe(VEREDITO_ANOMALIA, texto)
        elif proporcao >= PROPORCAO_MUDAS_ATENCAO:
            sobe(VEREDITO_ATENCAO, texto)

    if valores["falhas_entrega"] > 0:
        grau = VEREDITO_ANOMALIA if valores["enviadas"] == 0 else VEREDITO_ATENCAO
        sobe(grau, f"{valores['falhas_entrega']} envio(s) ao Discord falharam — ficam pendentes e são retentados")
    if valores["canais_nao_resolvidos"] > 0:
        sobe(VEREDITO_ATENCAO, f"{valores['canais_nao_resolvidos']} guild(s) com canal configurado que o bot não enxerga")

    exam = valores["itens_examinados"]
    if exam >= MINIMO_ITENS_PARA_PROPORCAO and valores["itens_sem_data"] / exam >= PROPORCAO_SEM_DATA_ATENCAO:
        sobe(VEREDITO_ATENCAO, f"{valores['itens_sem_data']} de {exam} itens sem data — filtro de idade não se aplica a eles")

    if valores["enviadas"] == 0 and not abortada:
        if horas >= HORAS_SEM_ENVIO_ANOMALIA:
            sobe(VEREDITO_ANOMALIA, f"~{horas:.0f}h sem publicar nada")
        elif horas >= HORAS_SEM_ENVIO_ATENCAO:
            sobe(VEREDITO_ATENCAO, f"~{horas:.0f}h sem publicar nada")
        elif veredito == VEREDITO_OK:
            motivos.append("0 publicadas neste ciclo — sem novidade nas fontes que responderam")

    if not motivos:
        entregaram = total - valores["fontes_falha"] - valores["fontes_vazias"]
        motivos.append(f"{valores['enviadas']} publicadas, {entregaram} de {total} fontes responderam")

    return {"veredito": veredito, "motivos": motivos, "metricas": valores, "quando": agora}
