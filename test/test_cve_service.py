
import sys
import os
import asyncio

# Adiciona o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.services.cveService import fetch_nvd_cves

import asyncio
from src.services.cveService import fetch_nvd_cves

def test_cve_service():
    """Wrapper síncrono para testar função assíncrona."""
    async def _run_test():
        print(f"Testando consulta NVD...")
        
        # Busca 3 CVEs para teste
        results = await fetch_nvd_cves(limit=3)
        
        if not results:
            print("⚠️ Nenhuma CVE retornada (pode ser rate limit ou falta de novas CVEs criticas).")
            return

        print(f"✅ Recebidas {len(results)} CVEs:")
        for item in results:
            print(f"- {item['title']}")
            print(f"  Link: {item['link']}")
            
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(_run_test())

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_cve_service())
