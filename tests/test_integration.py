import pytest

from src.services.cveService import fetch_nvd_cves


@pytest.mark.network
@pytest.mark.asyncio
async def test_cve_fetch():
    results = await fetch_nvd_cves(limit=1)
    assert isinstance(results, list)
