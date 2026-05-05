
import asyncio
import logging
import os
import sys
from unittest.mock import MagicMock

# Adiciona o diretório raiz ao path para importar os módulos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configura o log para sair no console
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger("CyberIntel")

from core.scanner import run_scan_once

async def test_scan():
    log.info("🚀 Iniciando Simulação de Scan (Dry Run)...")
    
    # Mock do Bot do Discord
    mock_bot = MagicMock()
    mock_channel = MagicMock()
    
    # Simula o envio de mensagens (apenas loga)
    async def mock_send(embed=None, view=None):
        log.info(f"📤 [SIMULAÇÃO] News capturada: {embed.title}")
        return MagicMock()
    
    mock_channel.send = mock_send
    mock_bot.get_channel.return_value = mock_channel
    
    # Executa o scan (bypass_cache=True para forçar busca de tudo)
    await run_scan_once(mock_bot, trigger="dry_run_test", bypass_cache=True)
    
    log.info("✅ Simulação concluída.")

if __name__ == "__main__":
    asyncio.run(test_scan())
