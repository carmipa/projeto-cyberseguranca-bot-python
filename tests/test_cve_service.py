
import sys
import os
import asyncio

# Adiciona o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.services.cveService import fetch_nvd_cves

def test_cve_service():
    """Wrapper síncrono para testar função assíncrona."""
    async def _run_test():
        print(f"Testando consulta NVD...")
        
        # Busca 3 CVEs para teste
        results = await fetch_nvd_cves(limit=3)
        
        if not results:
            print("[WARN] Nenhuma CVE retornada (pode ser rate limit ou falta de novas CVEs criticas).")
            return

        print(f"[OK] Recebidas {len(results)} CVEs:")
        for item in results:
            safe_title = str(item["title"]).encode("cp1252", errors="replace").decode("cp1252")
            print(f"- {safe_title}")
            print(f"  Link: {item['link']}")
            
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(_run_test())

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_cve_service())
