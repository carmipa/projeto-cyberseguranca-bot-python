"""
Testes de lógica de risco (faixas 0–10, 10–30, 30–50).

Estes testes não dependem do Discord nem de chamadas externas.
"""

import pytest

from core.risk import ThreatPhase, classify_risk, describe_phase


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, ThreatPhase.STABLE),
        (5, ThreatPhase.STABLE),
        (9.9, ThreatPhase.STABLE),
        (10, ThreatPhase.CAUTION),
        (15, ThreatPhase.CAUTION),
        (29.9, ThreatPhase.CAUTION),
        (30, ThreatPhase.CRITICAL),
        (45, ThreatPhase.CRITICAL),
        (50, ThreatPhase.CRITICAL),
    ],
)
def test_classify_risk_boundaries(score, expected):
    """
    Garante que os limiares 0–10, 10–30, 30–50 estejam corretos.
    """

    assert classify_risk(score) is expected


def test_classify_risk_whitelist_keeps_stable():
    """
    Mesmo com score alto, se estiver em whitelist o estado deve ser STABLE.
    """

    assert classify_risk(45, whitelisted=True) is ThreatPhase.STABLE


def test_describe_phase_critical_has_interception_message():
    """
    Para um risco crítico (30–50), a mensagem deve conter 'Intercepção autorizada'.
    """

    info = describe_phase(ThreatPhase.CRITICAL)
    assert info["label"] == "CRITICAL"
    assert "Intercepção autorizada" in info["message"]
    # Cor magenta (aceita variações de caixa)
    assert info["color"].lower() in {"#ff00ff", "#f0f"}

