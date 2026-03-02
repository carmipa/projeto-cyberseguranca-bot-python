import os
import sys
import logging
import asyncio
import pytest
from typing import Optional, Dict, Any

# Adiciona o diretório raiz ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("TestIntegrity")


@pytest.mark.asyncio
async def test_imports():
    try:
        log.info("🧪 Testando importações de Core e Services...")
        from core.scanner import load_history, load_sources
        from src.services.cveService import fetch_nvd_cves
        from src.services.threatService import ThreatService
        from bot.cogs.info import InfoCog
        
        log.info("✅ Importações básicas OK.")
        
        log.info("🧪 Testando cveService (Importação de Optional)...")
        # A linha 107 que causou o crash: 
        # async def get_cve_details(cve_id: str) -> Optional[Dict[str, Any]]:
        from src.services.cveService import get_cve_details
        log.info("✅ cveService.get_cve_details carregado com sucesso.")
        
        return True
    except Exception as e:
        log.error(f"❌ Falha no teste de integridade: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_imports())
    if success:
        print("\nPASSED: Integridade do código restaurada.")
    else:
        print("\nFAILED: O código ainda possui erros de sintaxe ou importação.")
