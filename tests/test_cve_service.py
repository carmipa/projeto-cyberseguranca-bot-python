import asyncio

import pytest

from src.services.cveService import fetch_nvd_cves


@pytest.mark.network
def test_cve_service():
    """Consulta real à NVD: devolve lista (vazia é legítimo: rate limit ou semana sem CVE >= 7.0)."""
    results = asyncio.run(fetch_nvd_cves(limit=3))
    assert isinstance(results, list)
    for item in results:
        assert item["link"].startswith("https://nvd.nist.gov/vuln/detail/CVE-")
