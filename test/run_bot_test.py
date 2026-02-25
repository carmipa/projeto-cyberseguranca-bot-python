#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para testar inicialização do bot sem conectar ao Discord
"""
import sys
import os
import asyncio

# Fix encoding para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from utils.logger import setup_logger
setup_logger('INFO')
log = logging.getLogger('CyberIntel')

def test_bot_init():
    """Testa inicialização do bot sem conectar"""
    log.info("🧪 Testando inicialização do bot...")
    
    try:
        # Testa imports principais
        from settings import TOKEN, OWNER_ID
        from main import main
        
        if not TOKEN:
            log.error("❌ DISCORD_TOKEN não configurado no .env")
            return False
        
        if not OWNER_ID:
            log.warning("⚠️ OWNER_ID não configurado")
        
        log.info("✅ Configuração básica OK")
        log.info(f"   TOKEN: {'Configurado' if TOKEN else 'NÃO'}")
        log.info(f"   OWNER_ID: {OWNER_ID if OWNER_ID else 'NÃO'}")
        
        # Testa carregamento de componentes
        from core.scanner import load_sources, load_history
        from utils.storage import p, load_json_safe
        
        sources = load_sources()
        history_list, history_set = load_history()
        config = load_json_safe(p("config.json"), {})
        
        log.info(f"✅ Componentes carregados:")
        log.info(f"   Fontes: {len(sources)}")
        log.info(f"   Histórico: {len(history_list)} links")
        log.info(f"   Guilds configuradas: {len(config)}")
        
        # Testa cogs
        from bot.cogs import admin, news, cve, monitor, security, status, dashboard, setup
        
        log.info("✅ Todos os cogs importados com sucesso")
        
        log.info("🎉 Bot pronto para iniciar!")
        log.info("")
        log.info("Para iniciar o bot, execute:")
        log.info("  python main.py")
        log.info("")
        log.info("Ou via Docker:")
        log.info("  docker compose up -d --build")
        
        return True
        
    except Exception as e:
        log.exception(f"❌ Erro ao testar inicialização: {e}")
        return False

if __name__ == "__main__":
    success = test_bot_init()
    sys.exit(0 if success else 1)
