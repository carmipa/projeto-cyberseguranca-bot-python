import os
import sys
import logging
import asyncio
import aiohttp

# Adiciona o diretório raiz ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.cveService import fetch_nvd_cves

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("TestIntegration")

async def test_cve_fetch():
    log.info("🧪 Iniciando Teste de Integração: NIST NVD API...")
    try:
        results = await fetch_nvd_cves(limit=1)
        if isinstance(results, list):
            log.info(f"✅ Sucesso! Recebidos {len(results)} resultados.")
            if len(results) > 0:
                log.info(f"📊 Exemplo de Título: {results[0].get('title')}")
            return True
        else:
            log.error("❌ Erro: O serviço não retornou uma lista.")
            return False
    except Exception as e:
        log.error(f"❌ Falha na integração com NVD: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_cve_fetch())
    if success:
        print("\nINTEGRATION PASSED: NVD Service is UP.")
    else:
        print("\nINTEGRATION FAILED: Verifique chaves de API ou conexão.")
