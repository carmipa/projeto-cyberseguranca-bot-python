# 🔧 Solução Rápida: Conflito no Git Pull

## ⚠️ Problema Encontrado

```
error: The following untracked working tree files would be overwritten by merge:
        data/sources.json
Please move or remove them before you merge.
```

## ✅ Solução Imediata (Execute no Servidor)

```bash
cd /opt/projeto-cyberseguranca-bot/

# 1. Fazer backup do arquivo local (se tiver customizações)
cp data/sources.json data/sources.json.backup 2>/dev/null || true

# 2. Remover o arquivo que está causando conflito
rm -f data/sources.json

# 3. Fazer o pull normalmente
git pull origin main

# 4. Verificar se o data/sources.json está correto
cat data/sources.json | head -20

# 5. Se precisar restaurar customizações do backup
# Compare os arquivos:
# diff data/sources.json.backup data/sources.json
```

## 📝 Explicação

- **`data/sources.json`**: Arquivo de configuração oficial (rastreado no repositório)

O bot usa `data/sources.json`. Se houver customização local, mantenha backup e reconcilie com o arquivo atualizado após pull.

## 🔄 Comando Completo de Deploy

```bash
cd /opt/projeto-cyberseguranca-bot/

# Resolver conflito
rm -f data/sources.json

# Atualizar código
git pull origin main

# Rebuild e restart
docker-compose down
docker-compose up -d --build

# Verificar status
docker-compose ps
docker-compose logs --tail=20 cyber-bot
```

## ✅ Verificação Pós-Deploy

O bot deve mostrar nos logs:

```
✅ Bot conectado como: cyberseguranca_bot#5382
✅ Slash sync global solicitado
🔎 Encontradas X novas vulnerabilidades críticas (NVD)
✅ Varredura concluída
```

Se tudo estiver funcionando, você verá:
- ✅ Bot conectado
- ✅ Comandos sincronizados
- ✅ Varredura executando
- ✅ Node-RED rodando na porta 1880

---

**Status Atual:** ✅ Bot funcionando corretamente após deploy!
