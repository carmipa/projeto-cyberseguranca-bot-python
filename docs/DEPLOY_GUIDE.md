# 🚀 Guia de Deploy e Resolução de Conflitos

## ⚠️ Problema: Conflito no Git Pull

Se você encontrar o erro:
```
error: The following untracked working tree files would be overwritten by merge:
        data/sources.json
Please move or remove them before you merge.
```

### 🔧 Solução Rápida

Execute no servidor:

```bash
# Opção 1: Fazer backup e remover o arquivo local
mv data/sources.json data/sources.json.backup
git pull origin main

# Opção 2: Se o arquivo local tem configurações importantes, mescle manualmente
# 1. Faça backup
cp data/sources.json data/sources.json.backup

# 2. Remova o arquivo
rm data/sources.json

# 3. Faça o pull
git pull origin main

# 4. Compare e mescle se necessário
diff data/sources.json.backup data/sources.json
```

### 📝 Explicação

- `data/sources.json`: arquivo oficial de configuração de feeds (versionado no projeto)
- Se houver customizações locais no servidor, faça backup antes do pull.

O bot usa `data/sources.json` como fonte principal. Se você tem customizações locais, faça merge com o arquivo atualizado após o pull.

---

## 🔄 Processo de Deploy Completo

### 1. Preparação

```bash
cd /opt/projeto-cyberseguranca-bot/

# Verificar status do git
git status

# Verificar se há mudanças locais importantes
git diff
```

### 2. Resolver Conflitos (se houver)

```bash
# Se houver arquivos não rastreados que causam conflito
# Listar arquivos não rastreados
git status --untracked-files=all

# Para arquivos de dados locais (não devem estar no git):
# - data/sources.json (se for cópia local)
# - data/config.json (configuração local)
# - state.json (cache do bot)
# - history.json (histórico do bot)

# Fazer backup se necessário
mkdir -p backups/$(date +%Y%m%d)
cp data/sources.json backups/$(date +%Y%m%d)/ 2>/dev/null || true
```

### 3. Atualizar Código

```bash
# Pull das atualizações
git pull origin main

# Se ainda houver conflito, force a remoção de arquivos locais
git clean -fd
git pull origin main
```

### 4. Rebuild e Restart

```bash
# Parar containers
docker-compose down

# Rebuild com cache limpo (se necessário)
docker-compose build --no-cache

# Ou rebuild normal
docker-compose build

# Subir containers
docker-compose up -d

# Verificar logs
docker-compose logs -f --tail=50
```

### 5. Verificar Status

```bash
# Status dos containers
docker-compose ps

# Logs do bot
docker-compose logs cyber-bot --tail=50 -f

# Logs do Node-RED
docker-compose logs nodered --tail=50 -f

# Verificar saúde dos containers
docker-compose ps
```

---

## 📋 Arquivos que NÃO devem estar no Git

Estes arquivos são gerados localmente e não devem ser commitados:

- ✅ `config.json` - Configuração local (já no .gitignore)
- ✅ `state.json` - Cache do bot (já no .gitignore)
- ✅ `history.json` - Histórico do bot (já no .gitignore)
- ✅ `data/sources.json` - Se for cópia local customizada
- ✅ `.env` - Variáveis de ambiente (já no .gitignore)
- ✅ `*.log` - Logs (já no .gitignore)

## 📋 Arquivos que DEVEM estar no Git

- ✅ `data/sources.json` - Configuração padrão de feeds
- ✅ `requirements.txt` - Dependências Python
- ✅ `Dockerfile` - Configuração Docker
- ✅ `docker-compose.yml` - Orquestração
- ✅ Todo código fonte (`bot/`, `core/`, `src/`, `utils/`)

---

## 🔍 Verificação Pós-Deploy

### 1. Verificar Conexão do Bot

```bash
docker-compose logs cyber-bot | grep -i "connected\|ready\|error"
```

Deve mostrar:
- ✅ Bot conectado ao Discord
- ✅ Cogs carregados
- ✅ Comandos sincronizados

### 2. Verificar Node-RED

```bash
docker-compose logs nodered | grep -i "started\|running\|error"
```

Deve mostrar:
- ✅ Node-RED iniciado
- ✅ Servidor rodando na porta 1880

### 3. Testar Comandos no Discord

- `/ping` - Verificar latência
- `/status` - Verificar estatísticas
- `/soc_status` - Verificar APIs

### 4. Verificar Varredura Automática

```bash
docker-compose logs cyber-bot | grep -i "varredura\|scan\|vulnerabilidade"
```

Deve mostrar varreduras sendo executadas periodicamente.

---

## 🛠️ Troubleshooting

### Problema: Bot não conecta ao Discord

```bash
# Verificar variáveis de ambiente
docker-compose exec cyber-bot env | grep DISCORD

# Verificar token
docker-compose exec cyber-bot env | grep TOKEN

# Verificar logs de erro
docker-compose logs cyber-bot | grep -i error
```

### Problema: Comandos não aparecem no Discord

```bash
# Verificar sincronização
docker-compose logs cyber-bot | grep -i "sync\|command"

# Forçar reinicialização
docker-compose restart cyber-bot
```

### Problema: Node-RED não acessível

```bash
# Verificar porta
netstat -tlnp | grep 1880

# Verificar logs
docker-compose logs nodered

# Verificar firewall
sudo ufw status
```

### Problema: Varredura não executa

```bash
# Verificar sources.json
docker-compose exec cyber-bot cat data/sources.json

# Verificar config.json
docker-compose exec cyber-bot cat data/config.json

# Verificar logs de varredura
docker-compose logs cyber-bot | grep -i "varredura\|scan"
```

---

## 📊 Monitoramento Contínuo

### Logs em Tempo Real

```bash
# Todos os serviços
docker-compose logs -f

# Apenas bot
docker-compose logs -f cyber-bot

# Apenas Node-RED
docker-compose logs -f nodered
```

### Estatísticas

```bash
# Uso de recursos
docker stats

# Espaço em disco
df -h

# Logs do sistema
journalctl -u docker -f
```

---

## 🔄 Atualização Automática (Opcional)

Para atualizar automaticamente, você pode criar um script:

```bash
#!/bin/bash
# /opt/projeto-cyberseguranca-bot/update.sh

cd /opt/projeto-cyberseguranca-bot/

# Backup
mkdir -p backups/$(date +%Y%m%d_%H%M%S)
cp -r data backups/$(date +%Y%m%d_%H%M%S)/ 2>/dev/null || true

# Pull
git pull origin main

# Rebuild e restart
docker-compose down
docker-compose up -d --build

# Verificar
sleep 10
docker-compose ps
```

Tornar executável:
```bash
chmod +x update.sh
```

---

## ✅ Checklist de Deploy

- [ ] Backup de arquivos locais importantes
- [ ] Resolver conflitos do git
- [ ] `git pull` executado com sucesso
- [ ] Containers rebuildados
- [ ] Containers iniciados e rodando
- [ ] Bot conectado ao Discord
- [ ] Comandos sincronizados
- [ ] Node-RED acessível
- [ ] Varredura automática funcionando
- [ ] Logs sem erros críticos

---

**Última atualização:** 13 de Fevereiro de 2026
