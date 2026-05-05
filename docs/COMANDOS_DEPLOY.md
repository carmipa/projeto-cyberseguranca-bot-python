# 🚀 Comandos de Deploy - Resolução Rápida

## ⚡ Solução Imediata para o Conflito Git

Execute estes comandos **no servidor**:

```bash
cd /opt/projeto-cyberseguranca-bot/

# 1. Remover arquivo local que causa conflito
rm -f data/sources.json

# 2. Atualizar código
git pull origin main

# 3. Rebuild e restart
docker-compose down
docker-compose up -d --build

# 4. Verificar logs
docker-compose logs --tail=30 cyber-bot
```

## ✅ Status Atual do Deploy

Pelos logs mostrados, o bot está **funcionando corretamente**:

- ✅ Bot conectado ao Discord (`cyberseguranca_bot#5382`)
- ✅ Todos os Cogs carregados
- ✅ Comandos sincronizados
- ✅ Monitoramento iniciado
- ✅ Varredura executada com sucesso (5 vulnerabilidades encontradas)
- ✅ Node-RED rodando na porta 1880

## 📋 Comandos Úteis para Monitoramento

### Ver logs em tempo real
```bash
docker-compose logs -f cyber-bot
```

### Ver status dos containers
```bash
docker-compose ps
```

### Ver últimas 50 linhas de log
```bash
docker-compose logs --tail=50 cyber-bot
```

### Reiniciar apenas o bot
```bash
docker-compose restart cyber-bot
```

### Verificar saúde do bot
```bash
docker-compose exec cyber-bot python -c "import sys; print('OK')"
```

## 🔍 Verificação de Funcionamento

### 1. Bot Conectado
```bash
docker-compose logs cyber-bot | grep "Bot conectado"
```
Deve mostrar: `✅ Bot conectado como: cyberseguranca_bot#5382`

### 2. Comandos Sincronizados
```bash
docker-compose logs cyber-bot | grep "Sync concluído"
```
Deve mostrar: `✅ Sync concluído para guild: ...`

### 3. Varredura Funcionando
```bash
docker-compose logs cyber-bot | grep "Varredura concluída"
```
Deve mostrar varreduras periódicas sendo executadas.

### 4. Node-RED Acessível
```bash
curl -s http://localhost:1880 | head -5
```
Deve retornar HTML do Node-RED.

## 🛠️ Próximos Passos

1. ✅ **Resolver conflito do git** (comandos acima)
2. ✅ **Verificar funcionamento** (já está OK pelos logs)
3. ⏭️ **Testar comandos no Discord**:
   - `/ping` - Testar latência
   - `/status` - Ver estatísticas
   - `/soc_status` - Verificar APIs
   - `/news` - Testar busca de notícias

## 📝 Nota sobre o Conflito

O arquivo `data/sources.json` no servidor é uma cópia local que não precisa estar no git. O bot usa `sources.json` da raiz do projeto, que já está no repositório.

**Solução aplicada:** Adicionado `data/sources.json` ao `.gitignore` para evitar conflitos futuros.

---

**Status:** ✅ Bot funcionando | ⚠️ Conflito git resolvido no próximo pull
