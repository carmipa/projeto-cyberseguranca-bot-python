"""
Isolamento da suíte: nenhum teste escreve no data/ versionado do repositório.

Em 2026-08-30 um teste com DATA_DIR temporário escreveu no database.json REAL,
porque o caminho era congelado no import; e os 7 test_backup*.backup que estão
versionados em data/backups/ nasceram de testes rodando sobre o diretório real.
"""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


@pytest.fixture(autouse=True)
def dados_isolados(tmp_path, monkeypatch):
    """
    PROPÓSITO DE NEGÓCIO: cada teste roda com o estado do bot (config, state,
    history, database, backups) num diretório temporário próprio.

    INVARIANTES DO DOMÍNIO: DATA_DIR aponta para tmp; o CATÁLOGO (sources.json)
    continua vindo do repositório via CATALOG_DIR, porque é dado versionado e não
    estado de execução.

    COMPORTAMENTO EM CASO DE FALHA: se o diretório não puder ser criado o pytest
    falha o teste na preparação, nunca cai no data/ real.
    """
    dados = tmp_path / "data"
    dados.mkdir()
    monkeypatch.setenv("DATA_DIR", str(dados))
    monkeypatch.setenv("CATALOG_DIR", str(RAIZ / "data"))
    yield dados
