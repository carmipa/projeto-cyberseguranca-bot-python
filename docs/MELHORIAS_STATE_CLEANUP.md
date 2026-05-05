# 🧹 Melhorias no Sistema de Limpeza do state.json

**Data:** 13 de Fevereiro de 2026  
**Problema:** `state.json` pode crescer excessivamente causando problemas de performance

---

## 🎯 Problema Identificado

O arquivo `state.json` armazena:
- **`dedup`**: Histórico de links processados por feed (pode crescer muito)
- **`http_cache`**: Cache HTTP com ETags e Last-Modified (pode crescer)
- **`html_hashes`**: Hashes de sites monitorados (crescimento moderado)

**Problema:** Quando o arquivo enche (> 10MB), causa:
- Lentidão ao carregar/salvar
- Alto uso de memória
- Possíveis timeouts
- Corrupção em casos extremos

---

## ✅ Solução Implementada

### 1. Módulo Dedicado de Limpeza (`utils/state_cleanup.py`)

Criado módulo especializado com funções:
- `check_and_cleanup_state()` - Verifica e limpa automaticamente
- `cleanup_state()` - Executa limpeza com estatísticas
- `should_cleanup_by_time()` - Verifica limpeza por tempo (7 dias)
- `should_cleanup_by_size()` - Verifica limpeza por tamanho

### 2. Limpeza Inteligente Multi-Critério

**Critérios de Limpeza:**

#### A) Por Tempo (7 dias)
- Limpeza automática a cada 7 dias
- Previne crescimento gradual

#### B) Por Tamanho Crítico (> 10 MB)
- Limpeza imediata se arquivo > 10 MB
- Previne problemas de performance

#### C) Por Tamanho de Aviso (> 5 MB)
- Limpeza parcial se arquivo > 5 MB
- Mantém dados recentes, remove antigos

### 3. Limpeza Seletiva por Seção

**Limites por Seção:**
- **`dedup`**: Máximo 2000 itens totais
  - Se feed individual > 500 itens, mantém últimos 500
- **`http_cache`**: Máximo 1000 itens
- **`html_hashes`**: Máximo 100 itens

**Estratégia:**
- Limpeza completa quando necessário (tempo ou tamanho crítico)
- Limpeza parcial quando arquivo grande mas não crítico
- Preserva `html_hashes` quando possível (importante para monitoramento)

---

## 📊 Estatísticas e Logs

### Logs Detalhados

```
🧹 [Auto-Cleanup] Executando limpeza completa (Ciclo de 7 dias)
📊 Antes: dedup=5000, cache=2000, hashes=50, tamanho=8.50 MB
🧹 Limpando dedup: 5000 itens -> 0
🧹 Limpando http_cache: 2000 itens -> 0
✅ Mantendo html_hashes (50 entradas)
✅ Limpeza concluída. Novo tamanho: 0.15 MB (redução de 8.35 MB)
```

### Métricas Coletadas

- Tamanho do arquivo antes/depois
- Contagem de itens por seção antes/depois
- Motivo da limpeza (tempo/tamanho)
- Redução de tamanho alcançada

---

## 🔧 Configuração

### Limites Configuráveis (`utils/state_cleanup.py`)

```python
# Limites de tamanho de arquivo
MAX_STATE_SIZE = 10 * 1024 * 1024  # 10 MB - crítico
WARN_STATE_SIZE = 5 * 1024 * 1024  # 5 MB - aviso

# Intervalo de limpeza por tempo
CLEANUP_INTERVAL = 604800  # 7 dias em segundos

# Limites de itens por seção
MAX_DEDUP_ITEMS = 2000
MAX_CACHE_ITEMS = 1000
MAX_HASHES_ITEMS = 100
```

### Ajustar Limites

Para ambientes com muitos feeds ou alta frequência:

```python
# Aumentar limites
MAX_DEDUP_ITEMS = 5000
MAX_CACHE_ITEMS = 2000

# Reduzir intervalo de limpeza (mais frequente)
CLEANUP_INTERVAL = 259200  # 3 dias
```

---

## 🚀 Uso

### Automático (Recomendado)

A limpeza acontece automaticamente no scanner:

```python
# Em core/scanner.py
from utils.state_cleanup import check_and_cleanup_state
state = check_and_cleanup_state(force=False)
```

### Manual (Para Debug/Manutenção)

```python
from utils.state_cleanup import check_and_cleanup_state, cleanup_state
from utils.storage import p, load_json_safe, save_json_safe

# Verifica e limpa se necessário
state = check_and_cleanup_state(force=False)

# Força limpeza imediata
state = check_and_cleanup_state(force=True)

# Limpeza manual com controle total
state = load_json_safe(p("state.json"), {})
state, stats = cleanup_state(state, reason="Manutenção manual")
save_json_safe(p("state.json"), state, atomic=True)
```

---

## 📈 Benefícios

### Performance
- ✅ Arquivo sempre em tamanho gerenciável
- ✅ Carregamento/salvamento rápido
- ✅ Menor uso de memória

### Confiabilidade
- ✅ Previne corrupção por arquivo muito grande
- ✅ Evita timeouts em operações de I/O
- ✅ Sistema mais estável

### Manutenção
- ✅ Limpeza automática sem intervenção
- ✅ Logs detalhados para auditoria
- ✅ Configurável para diferentes ambientes

---

## 🔍 Monitoramento

### Verificar Tamanho Atual

```python
from utils.state_cleanup import get_state_size
from utils.storage import p

size = get_state_size(p("state.json"))
print(f"Tamanho atual: {size / 1024 / 1024:.2f} MB")
```

### Verificar Última Limpeza

```python
from utils.storage import p, load_json_safe
from datetime import datetime

state = load_json_safe(p("state.json"), {})
last_clean = state.get("last_cleanup", 0)
if last_clean:
    last_clean_dt = datetime.fromtimestamp(last_clean)
    print(f"Última limpeza: {last_clean_dt}")
else:
    print("Nunca foi limpo")
```

---

## ⚠️ Notas Importantes

1. **Deduplicação Temporária**
   - Após limpeza completa, pode haver posts duplicados temporariamente
   - O sistema se recupera automaticamente na próxima varredura
   - `history.json` ainda previne duplicatas críticas

2. **Cache HTTP**
   - Limpeza do cache HTTP pode causar mais requisições
   - Impacto mínimo, pois feeds são verificados periodicamente
   - Benefício de performance supera custo de requisições extras

3. **HTML Hashes**
   - Preservados quando possível
   - Limpados apenas se muito grandes (> 100)
   - Pode causar detecção de "mudança" em sites monitorados após limpeza

---

## ✅ Conclusão

O sistema de limpeza agora é:
- ✅ **Automático** - Não requer intervenção manual
- ✅ **Inteligente** - Limpa baseado em múltiplos critérios
- ✅ **Seguro** - Preserva dados importantes quando possível
- ✅ **Auditável** - Logs detalhados de todas as operações
- ✅ **Configurável** - Ajustável para diferentes ambientes

**Problema resolvido:** `state.json` não vai mais causar problemas de performance por crescimento excessivo.

---

*Melhorias implementadas em 13 de Fevereiro de 2026*
