#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de teste para validar comandos do bot Discord.
Testa estrutura, validações e tratamento de erros.
"""
import sys
import io
import os

# Fix encoding para Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import importlib.util
import inspect
import re
from typing import List, Tuple

# Cores para output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")

def print_error(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")

def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")

def test_imports() -> Tuple[bool, List[str]]:
    """Testa se todos os módulos podem ser importados."""
    print_info("Testando imports dos módulos...")
    errors = []
    
    modules = [
        'bot.cogs.admin',
        'bot.cogs.news',
        'bot.cogs.cve',
        'bot.cogs.monitor',
        'bot.cogs.status',
        'bot.cogs.setup',
        'bot.cogs.info',
        'bot.cogs.dashboard',
        'bot.cogs.security',
        'bot.cogs.stats',
    ]
    
    for module_name in modules:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                errors.append(f"Módulo {module_name} não encontrado")
                continue
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            print_success(f"Import de {module_name} OK")
        except Exception as e:
            errors.append(f"Erro ao importar {module_name}: {e}")
            print_error(f"Falha ao importar {module_name}: {e}")
    
    return len(errors) == 0, errors

def test_command_structure() -> Tuple[bool, List[str]]:
    """Testa estrutura dos comandos."""
    print_info("Testando estrutura dos comandos...")
    errors = []
    
    # Mapeamento de comandos esperados
    expected_commands = {
        'bot.cogs.admin': ['forcecheck', 'post_latest'],
        'bot.cogs.news': ['news'],
        'bot.cogs.cve': ['cve'],
        'bot.cogs.monitor': ['force_scan', 'scan'],
        'bot.cogs.status': ['status', 'now'],
        'bot.cogs.setup': ['set_channel', 'soc_status'],
        'bot.cogs.info': ['ping', 'about', 'feeds', 'help', 'server_log'],
        'bot.cogs.dashboard': ['dashboard'],
        'bot.cogs.security': ['admin_panel'],
        'bot.cogs.stats': ['status_db'],
    }
    
    for module_name, expected_cmds in expected_commands.items():
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                errors.append(f"Módulo {module_name} não encontrado")
                continue
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Encontra a classe Cog
            cog_class = None
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and hasattr(obj, '__module__') and obj.__module__ == module_name:
                    if hasattr(obj, '__cog_name__') or 'Cog' in name or 'Cog' in str(obj):
                        cog_class = obj
                        break
            
            if cog_class is None:
                # Tenta encontrar qualquer classe que seja uma Cog
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if hasattr(obj, '__cog_commands__') or 'commands.Cog' in str(inspect.getmro(obj)):
                        cog_class = obj
                        break
            
            if cog_class is None:
                errors.append(f"Nenhuma classe Cog encontrada em {module_name}")
                continue
            
            # Verifica métodos de comando lendo o código-fonte
            found_commands = []
            try:
                # Lê o arquivo fonte diretamente
                file_path = spec.origin
                if file_path and os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        source_code = f.read()
                    
                    # Procura por decorators @app_commands.command
                    pattern = r'@app_commands\.command\(name=["\'](\w+)["\']'
                    matches = re.findall(pattern, source_code)
                    found_commands.extend(matches)
                    
                    # Também procura por comandos sem name explícito (usa nome da função)
                    # Procura por padrão: @app_commands.command(...) seguido de async def nome_funcao
                    pattern2 = r'@app_commands\.command\([^)]*\)\s+async def (\w+)'
                    matches2 = re.findall(pattern2, source_code)
                    found_commands.extend(matches2)
                    
                    # Remove duplicatas
                    found_commands = list(set(found_commands))
            except Exception as e:
                # Fallback: tenta usar inspect
                for name, method in inspect.getmembers(cog_class, inspect.isfunction):
                    if name.startswith('_'):
                        continue
                    if inspect.iscoroutinefunction(method):
                        try:
                            source = inspect.getsource(method)
                            if '@app_commands.command' in source:
                                match = re.search(r'@app_commands\.command\(name=["\'](\w+)["\']', source)
                                if match:
                                    found_commands.append(match.group(1))
                                else:
                                    found_commands.append(name)
                        except:
                            pass
            
            # Verifica se todos os comandos esperados estão presentes
            missing = set(expected_cmds) - set(found_commands)
            if missing:
                errors.append(f"{module_name}: Comandos faltando: {', '.join(missing)}")
                print_warning(f"{module_name}: Comandos faltando: {', '.join(missing)}")
            else:
                print_success(f"{module_name}: Todos os comandos presentes")
                
        except Exception as e:
            errors.append(f"Erro ao testar {module_name}: {e}")
            print_error(f"Erro ao testar {module_name}: {e}")
    
    return len(errors) == 0, errors

def test_error_handling() -> Tuple[bool, List[str]]:
    """Testa se os comandos têm tratamento de erro adequado."""
    print_info("Testando tratamento de erros...")
    errors = []
    
    modules = [
        'bot.cogs.admin',
        'bot.cogs.news',
        'bot.cogs.cve',
        'bot.cogs.monitor',
        'bot.cogs.status',
        'bot.cogs.setup',
        'bot.cogs.info',
        'bot.cogs.dashboard',
        'bot.cogs.security',
        'bot.cogs.stats',
    ]
    
    for module_name in modules:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                continue
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Encontra a classe Cog
            cog_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if 'Cog' in name or hasattr(obj, '__cog_commands__'):
                    cog_class = obj
                    break
            
            if cog_class is None:
                continue
            
            # Verifica métodos async que são comandos
            for name, method in inspect.getmembers(cog_class, inspect.isfunction):
                # Ignora métodos internos
                if name.startswith('_'):
                    continue
                    
                if inspect.iscoroutinefunction(method):
                    try:
                        source = inspect.getsource(method)
                        
                        # Verifica se é um comando (tem decorator @app_commands.command)
                        is_command = '@app_commands.command' in source
                        
                        if is_command:
                            # Verifica se tem try-except
                            if 'try:' in source and 'except' in source:
                                # Verifica se usa log.exception
                                if 'log.exception' in source or 'logger.exception' in source:
                                    print_success(f"{module_name}.{name}: Tratamento de erro OK")
                                else:
                                    # Não é erro crítico, apenas aviso
                                    print_warning(f"{module_name}.{name}: Tem try-except mas não usa log.exception")
                            elif 'interaction.response' in source or 'interaction.followup' in source:
                                # Comando Discord sem tratamento de erro
                                errors.append(f"{module_name}.{name}: Sem tratamento de erro (try-except)")
                                print_error(f"{module_name}.{name}: Sem tratamento de erro")
                    except:
                        pass
                        
        except Exception as e:
            errors.append(f"Erro ao testar tratamento de erros em {module_name}: {e}")
    
    return len(errors) == 0, errors

def test_validations() -> Tuple[bool, List[str]]:
    """Testa validações de entrada nos comandos."""
    print_info("Testando validações de entrada...")
    errors = []
    
    # Testa validações específicas
    validation_tests = {
        'bot.cogs.cve': {
            'cve': ['cve_id', 'startswith("CVE-")', 'len(cve_id)']
        },
        'bot.cogs.monitor': {
            'scan_command': ['url', 'startswith(("http://", "https://"))']
        },
        'bot.cogs.setup': {
            'set_channel': ['guild_id', 'channel_id']
        },
    }
    
    for module_name, validations in validation_tests.items():
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                continue
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            for cmd_name, checks in validations.items():
                # Tenta encontrar o método
                cog_class = None
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if 'Cog' in name:
                        cog_class = obj
                        break
                
                if cog_class and hasattr(cog_class, cmd_name):
                    method = getattr(cog_class, cmd_name)
                    source = inspect.getsource(method)
                    
                    # Verifica se as validações estão presentes
                    for check in checks:
                        if check in source:
                            print_success(f"{module_name}.{cmd_name}: Validação '{check}' presente")
                        else:
                            errors.append(f"{module_name}.{cmd_name}: Validação '{check}' faltando")
                            print_warning(f"{module_name}.{cmd_name}: Validação '{check}' faltando")
                            
        except Exception as e:
            errors.append(f"Erro ao testar validações em {module_name}: {e}")
    
    return len(errors) == 0, errors

def test_discord_limits() -> Tuple[bool, List[str]]:
    """Testa se os comandos respeitam limites do Discord."""
    print_info("Testando limites do Discord...")
    errors = []
    
    modules = [
        'bot.cogs.news',
        'bot.cogs.cve',
        'bot.cogs.info',
    ]
    
    for module_name in modules:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                continue
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Encontra a classe Cog
            cog_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if 'Cog' in name:
                    cog_class = obj
                    break
            
            if cog_class is None:
                continue
            
            # Verifica métodos que criam embeds
            for name, method in inspect.getmembers(cog_class, inspect.isfunction):
                if inspect.iscoroutinefunction(method):
                    source = inspect.getsource(method)
                    
                    # Verifica limites em add_field
                    if 'add_field' in source:
                        # Verifica se há limitação de tamanho
                        if '[:1024]' in source or '[:256]' in source or '[:4096]' in source:
                            print_success(f"{module_name}.{name}: Limites do Discord aplicados")
                        else:
                            # Verifica se é um campo que pode exceder limites
                            if 'description' in source.lower() or 'value' in source.lower():
                                errors.append(f"{module_name}.{name}: Pode exceder limites do Discord")
                                print_warning(f"{module_name}.{name}: Considerar limitar tamanho dos campos")
                                
        except Exception as e:
            errors.append(f"Erro ao testar limites em {module_name}: {e}")
    
    return len(errors) == 0, errors

def test_logger_consistency() -> Tuple[bool, List[str]]:
    """Testa consistência do logger."""
    print_info("Testando consistência do logger...")
    errors = []
    
    modules = [
        'bot.cogs.admin',
        'bot.cogs.news',
        'bot.cogs.cve',
        'bot.cogs.monitor',
        'bot.cogs.status',
        'bot.cogs.setup',
        'bot.cogs.info',
        'bot.cogs.dashboard',
        'bot.cogs.security',
        'bot.cogs.stats',
    ]
    
    for module_name in modules:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                continue
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Verifica se usa 'log' ou 'logger'
            source = inspect.getsource(module)
            
            # Verifica imports
            if 'logging.getLogger' in source:
                # Verifica se usa 'log' consistentemente
                if 'logger =' in source and 'log =' not in source:
                    # Verifica se usa 'logger' em todo o código
                    if 'logger.' in source and 'log.' not in source:
                        print_warning(f"{module_name}: Usa 'logger' em vez de 'log'")
                    elif 'logger.' in source and 'log.' in source:
                        errors.append(f"{module_name}: Mistura 'log' e 'logger'")
                        print_error(f"{module_name}: Inconsistência entre 'log' e 'logger'")
                    else:
                        print_success(f"{module_name}: Logger OK")
                elif 'log =' in source:
                    print_success(f"{module_name}: Logger OK (usa 'log')")
                else:
                    print_warning(f"{module_name}: Logger não inicializado")
            else:
                print_warning(f"{module_name}: Sem import de logging")
                
        except Exception as e:
            errors.append(f"Erro ao testar logger em {module_name}: {e}")
    
    return len(errors) == 0, errors

def main():
    """Executa todos os testes."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print("🧪 TESTES DE COMANDOS DO BOT DISCORD")
    print(f"{'='*60}{Colors.RESET}\n")
    
    results = []
    
    # Teste 1: Imports
    print(f"\n{Colors.BOLD}1. Teste de Imports{Colors.RESET}")
    print("-" * 60)
    success, errors = test_imports()
    results.append(("Imports", success, errors))
    
    # Teste 2: Estrutura dos comandos
    print(f"\n{Colors.BOLD}2. Teste de Estrutura dos Comandos{Colors.RESET}")
    print("-" * 60)
    success, errors = test_command_structure()
    results.append(("Estrutura", success, errors))
    
    # Teste 3: Tratamento de erros
    print(f"\n{Colors.BOLD}3. Teste de Tratamento de Erros{Colors.RESET}")
    print("-" * 60)
    success, errors = test_error_handling()
    results.append(("Tratamento de Erros", success, errors))
    
    # Teste 4: Validações
    print(f"\n{Colors.BOLD}4. Teste de Validações{Colors.RESET}")
    print("-" * 60)
    success, errors = test_validations()
    results.append(("Validações", success, errors))
    
    # Teste 5: Limites do Discord
    print(f"\n{Colors.BOLD}5. Teste de Limites do Discord{Colors.RESET}")
    print("-" * 60)
    success, errors = test_discord_limits()
    results.append(("Limites Discord", success, errors))
    
    # Teste 6: Consistência do Logger
    print(f"\n{Colors.BOLD}6. Teste de Consistência do Logger{Colors.RESET}")
    print("-" * 60)
    success, errors = test_logger_consistency()
    results.append(("Logger", success, errors))
    
    # Resumo
    print(f"\n{Colors.BOLD}{'='*60}")
    print("📊 RESUMO DOS TESTES")
    print(f"{'='*60}{Colors.RESET}\n")
    
    total_tests = len(results)
    passed_tests = sum(1 for _, success, _ in results if success)
    
    for test_name, success, errors in results:
        if success:
            print_success(f"{test_name}: PASSOU")
        else:
            print_error(f"{test_name}: FALHOU ({len(errors)} erro(s))")
            for error in errors[:3]:  # Mostra apenas os 3 primeiros erros
                print(f"   • {error}")
            if len(errors) > 3:
                print(f"   ... e mais {len(errors) - 3} erro(s)")
    
    print(f"\n{Colors.BOLD}Resultado Final: {passed_tests}/{total_tests} testes passaram{Colors.RESET}\n")
    
    if passed_tests == total_tests:
        print_success("🎉 Todos os testes passaram!")
        return 0
    else:
        print_error(f"⚠️  {total_tests - passed_tests} teste(s) falharam")
        return 1

if __name__ == "__main__":
    sys.exit(main())
