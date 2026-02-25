"""
Testes focados em AppSec / Hardening do CyberIntel SOC Bot.

Os testes aqui não invocam o Discord diretamente; eles validam
sanitização de entradas, gestão de segredos e comportamento quando
APIs externas não estão configuradas.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.filters import match_intel
from utils.html import clean_html
from src.services import threatService


def test_clean_html_strips_script_tags_and_entities():
    """
    Garante que entradas potencialmente perigosas sejam normalizadas.
    """

    raw = "<script>alert('xss')</script><b>OK&nbsp;Test</b>"
    sanitized = clean_html(raw)

    assert "script" not in sanitized.lower()
    assert "<" not in sanitized
    assert "OK" in sanitized and "Test" in sanitized


def test_match_intel_blocks_blacklisted_content_even_with_html():
    """
    Simula notícia com HTML + palavras de blacklist; deve ser bloqueada.
    """

    config = {
        "guild1": {
            "filters": ["malware"],
        }
    }

    title = "<b>Casino Promo</b>"
    summary = "Novo malware detectado em campanha <script>alert('x')</script>"

    # Mesmo contendo 'malware', o termo 'casino' em HTML deve ativar blacklist
    allowed = match_intel("guild1", title, summary, config)
    assert allowed is False


@pytest.mark.asyncio
async def test_threat_services_handle_missing_api_keys(monkeypatch):
    """
    Gestão de segredos: serviços de Threat Intel devem falhar de forma graciosa
    quando as API keys não estão configuradas (sem exceções).
    """

    # Zera todas as API keys dentro do módulo
    monkeypatch.setattr(threatService, "URLSCAN_API_KEY", "", raising=False)
    monkeypatch.setattr(threatService, "OTX_API_KEY", "", raising=False)
    monkeypatch.setattr(threatService, "VT_API_KEY", "", raising=False)
    monkeypatch.setattr(threatService, "GREYNOISE_API_KEY", "", raising=False)
    monkeypatch.setattr(threatService, "SHODAN_API_KEY", "", raising=False)

    # 1) URLScan - deve retornar None, não lançar
    resp1 = await threatService.ThreatService.scan_url_urlscan("http://example.com")
    assert resp1 is None

    # 2) OTX - deve retornar lista vazia
    resp2 = await threatService.ThreatService.get_otx_pulses(limit=1)
    assert isinstance(resp2, list)
    assert resp2 == []

    # 3) VT - deve retornar dict vazio
    resp3 = await threatService.ThreatService.check_vt_reputation("http://example.com")
    assert isinstance(resp3, dict)
    assert resp3 == {}

    # 4) GreyNoise / Shodan - devem retornar None
    resp4 = await threatService.ThreatService.lookup_greynoise_ip("1.2.3.4")
    resp5 = await threatService.ThreatService.lookup_shodan_ip("1.2.3.4")
    assert resp4 is None
    assert resp5 is None


def test_no_discord_token_pattern_committed_in_repo():
    """
    Audit simples para garantir que nenhum token de Discord em formato válido
    foi versionado acidentalmente no código-fonte.

    Formato aproximado: XXXXX.YYYYYY.ZZZZZ (3 partes base64-like).
    """

    root = Path(__file__).resolve().parents[1]
    token_regex = re.compile(r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}")

    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not token_regex.search(text), f"Possível token de Discord encontrado em {path}"

