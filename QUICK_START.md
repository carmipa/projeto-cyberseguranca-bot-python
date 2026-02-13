# 🚀 Quick Start - CyberIntel SOC Bot

**Bot de Varredura de Informações de Cibersegurança**

Este é um bot automatizado que varre feeds RSS, APIs de segurança e sites oficiais para coletar e distribuir inteligência de ameaças via Discord.

---

## ⚡ Deploy Rápido (Subir e Rodar)

### Pré-requisitos
- Docker e Docker Compose instalados
- Token do Discord Bot
- (Opcional) **API Keys gratuitas** para NVD, OTX, URLScan, VirusTotal, GreyNoise, Shodan
  - Todas têm planos free! Veja links de registro no `.env.example`

### 1. Clone o Repositório

```bash
git clone https://github.com/carmipa/projeto-cyberseguranca-bot.git
cd projeto-cyberseguranca-bot
```

### 2. Configure o `.env`

```bash
cp .env.example .env
# Edite o .env com suas credenciais
nano .env
```

**Mínimo necessário:**
```env
DISCORD_TOKEN=seu_token_discord_aqui
OWNER_ID=seu_id_discord
```

### 3. Suba os Containers

```bash
docker compose up -d --build
```

**Pronto!** O bot está rodando e começará a varrer informações automaticamente.

---

## 📊 Verificar Status

```bash
# Ver logs em tempo real
docker compose logs -f cyber-bot

# Ver status dos containers
docker compose ps

# Ver logs do Node-RED (dashboard)
docker compose logs -f nodered
```

---

## 🛠️ Comandos Úteis

### Parar o Bot
```bash
docker compose down
```

### Reiniciar o Bot
```bash
docker compose restart cyber-bot
```

### Atualizar Código
```bash
git pull
docker compose up -d --build
```

### Ver Logs das Últimas 100 Linhas
```bash
docker compose logs --tail=100 cyber-bot
```

---

## 📁 Estrutura de Dados

Os dados são persistidos em volumes Docker:

```
./data/              # Dados persistentes
  ├── config.json    # Configuração de guilds e filtros
  ├── state.json     # Estado do scanner (limpo automaticamente)
  ├── history.json   # Histórico de links processados
  └── database.json  # Banco de dados de notícias

./logs/              # Logs do sistema
  └── bot.log        # Log rotativo (máx 5MB, 3 backups)
```

---

## 🔧 Configuração Inicial no Discord

Após o bot estar rodando:

1. Adicione o bot ao seu servidor Discord
2. Use o comando `/set_channel` no canal onde quer receber alertas
3. Configure filtros usando `/dashboard` (se disponível)

---

## 🐳 Por Que Docker?

Este bot foi projetado para **simplesmente subir e rodar**:

✅ **Isolamento** - Não interfere com outros serviços do sistema  
✅ **Portabilidade** - Roda igual em qualquer servidor com Docker  
✅ **Persistência** - Dados salvos em volumes, sobrevivem a reinicializações  
✅ **Fácil Manutenção** - Atualizar é só `git pull` + `docker compose up -d --build`  
✅ **Orquestração** - Bot + Node-RED rodam juntos automaticamente  

---

## 🆘 Problemas Comuns

### Bot não conecta ao Discord
- Verifique se `DISCORD_TOKEN` está correto no `.env`
- Veja logs: `docker compose logs cyber-bot`

### Bot não posta notícias
- Verifique se configurou o canal com `/set_channel`
- Use `/forcecheck` para forçar uma varredura
- Verifique logs para erros de API

### Container reinicia constantemente
- Verifique logs: `docker compose logs cyber-bot`
- Verifique se `.env` está configurado corretamente
- Verifique recursos do sistema (memória/CPU)

---

## 📚 Documentação Completa

- **[DEPLOY.md](./DEPLOY.md)** - Guia completo de deploy em VPS
- **[README_PT.md](./README_PT.md)** - Documentação técnica completa
- **[TUTORIAL.md](./TUTORIAL.md)** - Tutorial de comandos e uso

---

**Desenvolvido para varredura automatizada de inteligência em cibersegurança.**
