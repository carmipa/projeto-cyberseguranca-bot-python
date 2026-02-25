#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de teste do CyberIntel SOC Bot
Testa componentes principais sem precisar de token Discord
"""
import sys
import os
import asyncio
import logging

# Fix encoding para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configura logging
from utils.logger import setup_logger
setup_logger('INFO')
log = logging.getLogger('CyberIntel_Test')

def test_imports():
    """Testa importações principais"""
    log.info("🧪 Testando importações...")
    try:
        from settings import TOKEN, OWNER_ID, COMMAND_PREFIX, LOOP_MINUTES
        from core.scanner import load_sources, load_history
        from core.filters import match_intel, FILTER_OPTIONS
        from utils.storage import p, load_json_safe, save_json_safe
        from utils.state_cleanup import check_and_cleanup_state
        from src.services.cveService import fetch_nvd_cves
        from src.services.threatService import ThreatService
        
        log.info("✅ Todas as importações funcionando")
        return True
    except Exception as e:
        log.error(f"❌ Erro nas importações: {e}")
        return False

def test_storage():
    """Testa sistema de storage"""
    log.info("🧪 Testando sistema de storage...")
    try:
        from utils.storage import p, load_json_safe, save_json_safe
        
        # Testa escrita e leitura
        test_data = {"test": "data", "timestamp": "2026-02-13"}
        test_file = p("test_storage.json")
        
        save_json_safe(test_file, test_data, atomic=True)
        loaded = load_json_safe(test_file, {})
        
        if loaded == test_data:
            log.info("✅ Storage funcionando corretamente")
            # Limpa arquivo de teste
            if os.path.exists(test_file):
                os.remove(test_file)
            return True
        else:
            log.error("❌ Dados não correspondem")
            return False
    except Exception as e:
        log.error(f"❌ Erro no storage: {e}")
        return False

def test_filters():
    """Testa sistema de filtros"""
    log.info("🧪 Testando sistema de filtros...")
    try:
        from core.filters import match_intel, FILTER_OPTIONS
        
        config = {
            "123": {
                "filters": ["malware", "ransomware"]
            }
        }
        
        # Teste positivo
        result1 = match_intel("123", "malware detected", "ransomware attack", config)
        # Teste negativo (blacklist)
        result2 = match_intel("123", "casino bonus", "gambling", config)
        # Teste negativo (sem match)
        result3 = match_intel("123", "weather forecast", "sunny day", config)
        
        if result1 and not result2 and not result3:
            log.info("✅ Filtros funcionando corretamente")
            return True
        else:
            log.warning(f"⚠️ Resultados inesperados: {result1}, {result2}, {result3}")
            return False
    except Exception as e:
        log.error(f"❌ Erro nos filtros: {e}")
        return False

def test_sources():
    """Testa carregamento de fontes"""
    log.info("🧪 Testando carregamento de fontes...")
    try:
        from core.scanner import load_sources
        
        sources = load_sources()
        log.info(f"✅ {len(sources)} fontes carregadas")
        if sources:
            log.info(f"   Primeiras 3: {sources[:3]}")
        return True
    except Exception as e:
        log.error(f"❌ Erro ao carregar fontes: {e}")
        return False

async def test_nvd_api():
    """Testa API NVD"""
    log.info("🧪 Testando API NVD...")
    try:
        from src.services.cveService import fetch_nvd_cves
        
        cves = await fetch_nvd_cves(limit=1)
        if cves:
            log.info(f"✅ NVD API funcionando - {len(cves)} CVE(s) encontrada(s)")
            log.info(f"   Exemplo: {cves[0].get('title', 'N/A')[:50]}...")
        else:
            log.warning("⚠️ NVD API não retornou resultados (pode ser normal)")
        return True
    except Exception as e:
        log.error(f"❌ Erro na API NVD: {e}")
        return False

def test_state_cleanup():
    """Testa sistema de limpeza"""
    log.info("🧪 Testando sistema de limpeza de state.json...")
    try:
        from utils.state_cleanup import check_and_cleanup_state
        
        state = check_and_cleanup_state(force=False)
        log.info("✅ Sistema de limpeza funcionando")
        log.info(f"   Dedup: {len(state.get('dedup', {}))} feeds")
        log.info(f"   Cache: {len(state.get('http_cache', {}))} entradas")
        return True
    except Exception as e:
        log.error(f"❌ Erro no sistema de limpeza: {e}")
        return False

def test_backup():
    """Testa sistema de backup"""
    log.info("🧪 Testando sistema de backup...")
    try:
        from utils.backup import create_backup, list_backups
        from utils.storage import p
        import os
        
        # Cria arquivo de teste
        test_file = p("test_backup.json")
        os.makedirs(os.path.dirname(test_file), exist_ok=True)
        with open(test_file, 'w') as f:
            f.write('{"test": true}')
        
        # Testa backup
        backup_path = create_backup(test_file, "test")
        
        if backup_path:
            log.info(f"✅ Backup criado: {backup_path}")
            # Limpa
            if os.path.exists(test_file):
                os.remove(test_file)
            return True
        else:
            log.warning("⚠️ Backup não foi criado")
            return False
    except Exception as e:
        log.error(f"❌ Erro no backup: {e}")
        return False

def main():
    """Executa todos os testes"""
    log.info("🚀 Iniciando testes do CyberIntel SOC Bot...")
    log.info("=" * 60)
    
    results = {}
    
    # Testes síncronos
    results['imports'] = test_imports()
    results['storage'] = test_storage()
    results['filters'] = test_filters()
    results['sources'] = test_sources()
    results['state_cleanup'] = test_state_cleanup()
    results['backup'] = test_backup()
    
    # Testes assíncronos
    results['nvd_api'] = asyncio.run(test_nvd_api())
    
    # Resumo
    log.info("=" * 60)
    log.info("📊 Resumo dos Testes:")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSOU" if result else "❌ FALHOU"
        log.info(f"  {test_name}: {status}")
    
    log.info(f"\n🎯 Resultado Final: {passed}/{total} testes passaram")
    
    if passed == total:
        log.info("🎉 Todos os testes passaram! Bot pronto para uso.")
        return 0
    else:
        log.warning(f"⚠️ {total - passed} teste(s) falharam. Verifique os logs acima.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
