"""
Risk classification helpers for the CyberIntel SOC.

This module centraliza a lógica de faixas de risco usada no cockpit
e facilita criar testes formais das regras de GRC (0–10, 10–30, 30–50).
"""

from __future__ import annotations

from enum import Enum
from typing import Dict


class ThreatPhase(str, Enum):
    """
    Fases de risco usadas no painel.

    Os valores em string são pensados para serem consumidos por
    front-ends (Node-RED, dashboards, etc.).
    """

    STABLE = "PHAS_STABLE"
    CAUTION = "PHAS_CAUTION"
    CRITICAL = "PHAS_CRITICAL"


def classify_risk(score: float, whitelisted: bool = False) -> ThreatPhase:
    """
    Classifica o score de risco nas faixas 0–10, 10–30, 30–50.

    Regras:
    - Se `whitelisted` for True, sempre retorna STABLE (falso positivo controlado).
    - 0 <= score < 10  -> STABLE
    - 10 <= score < 30 -> CAUTION
    - 30 <= score <= 50 (ou mais) -> CRITICAL
    """

    if whitelisted:
        return ThreatPhase.STABLE

    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 0.0

    if value < 10:
        return ThreatPhase.STABLE
    if value < 30:
        return ThreatPhase.CAUTION
    return ThreatPhase.CRITICAL


def describe_phase(phase: ThreatPhase) -> Dict[str, str]:
    """
    Fornece metadados humanos sobre cada fase de risco.

    Os textos são alinhados com a legenda usada no dashboard:
    - STABLE:  00 // 10  — "Atividade nominal."
    - CAUTION: 10 // 30  — "Tráfego elevado detectado."
    - CRITICAL:30 // 50  — "Intercepção autorizada."
    """

    if phase is ThreatPhase.CRITICAL:
        return {
            "label": "CRITICAL",
            # Magenta para casar com o alerta visual do cockpit
            "color": "#FF00FF",
            "message": "Intercepção autorizada.",
        }

    if phase is ThreatPhase.CAUTION:
        return {
            "label": "CAUTION",
            "color": "#E6E600",
            "message": "Tráfego elevado detectado.",
        }

    return {
        "label": "STABLE",
        "color": "#00FF00",
        "message": "Atividade nominal.",
    }

