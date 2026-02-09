<p align="center">
  <img src="icon.png" alt="CyberIntel Bot" width="200"/>
</p>

<h1 align="center">🐳 Guia de Deploy — CyberIntel SOC System</h1>

<p align="center">
  <b>Deploy do ecossistema de Inteligência em VPS Linux com Docker</b><br>
  <i>Infraestrutura como Código • Segurança por Design • Monitoramento SOC</i>
</p>

---

## 📋 Pré-requisitos Técnicos

Antes de iniciar a implantação em produção, valide seu ambiente:

| Recurso | Requisito Mínimo | Comando de Verificação |
|---------|------------------|------------------------|
| 🖥️ **VPS** | 1 vCPU, 2GB RAM (Ubuntu 22.04 LTS) | `lsb_release -a` |
| 🐳 **Docker Engine** | v24.0.0+ | `docker --version` |
| 🔧 **Docker Compose** | v2.20.0+ (V2 Plugin) | `docker compose version` |
| 🔑 **Tokens APIs** | Discord, NVD, OTX | `cat .env` |
| 📡 **Rede** | Portas 22 (SSH) e 8080 (Opcional Web) | `ufw status` |

---

## 🚀 Instalação e Orquestração (Docker Compose)

O sistema CyberIntel utiliza **Docker Compose** para orquestrar o Bot (Python) e o Dashboard (Node-RED) de forma isolada.

### 1. Preparação do Servidor

```bash
# Atualização de pacotes e dependências
sudo apt update && sudo apt upgrade -y
sudo apt install curl git ufw -y

# Instalação rápida do Docker Engine via Script Oficial
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Re-login necessário para aplicar grupo docker
exit
```

### 2. Implantação do Código

```bash
cd /opt
sudo git clone https://github.com/carmipa/projeto-cyberseguranca-bot.git cyberintel
sudo chown -R $USER:$USER cyberintel
cd cyberintel
```

### 3. Configuração de Inteligência (.env)

O arquivo `.env` é o coração da segurança do bot. Nunca o exponha publicamente.

```bash
cat <<EOF > .env
DISCORD_TOKEN='seu_token_aqui'
OWNER_ID='seu_id_discord_para_bypass_honeypot'
NVD_API_KEY='sua_chave_nvd'
OTX_API_KEY='sua_chave_alienvault'
DEPLOY_ENV='production'
EOF

chmod 600 .env
```

### 4. Inicialização do Cluster

```bash
# Build e Start em modo Detached (Background)
docker compose up -d --build

# Validação de Saúde (Healthcheck)
docker compose ps
```

---

## 🔒 Hardening & Segurança (VPS)

Para operar um SOC em VPS pública, o **Hardening** é obrigatório para evitar que seu bot seja alvo de ataques.

### 1. Firewall Restritivo (UFW)

O bot Discord não precisa de portas abertas (ele abre conexões de saída). Apenas o SSH e o Dashboard precisam de atenção.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp  # SSH
sudo ufw enable
```

### 2. Dashboard SOC Seguro (Acesso via Túnel)

Por segurança, o painel Node-RED (`port 1880`) **não deve ser aberto no firewall**. Use um Túnel SSH para acessá-lo localmente:

**No seu computador pessoal:**

```bash
ssh -L 1880:localhost:1880 usuario@ip-da-vps
```

Agora acesse `http://localhost:1880/ui` no seu navegador local. O tráfego estará criptografado pelo SSH.

---

## 📊 Manutenção SOC

### Logs em Tempo Real

```bash
docker compose logs -f bot       # Logs do Bot e varreduras
docker compose logs -f nodered   # Logs do processamento visual
```

### Atualização Expressa

Sempre que houver melhorias no repositório:

```bash
git pull
docker compose up -d --build
```

### Persistência de Dados

Os dados são salvos em volumes Docker ou bind-mounts:

- `history.json`: Histórico de deduplicação (Dedupe).
- `data/database.json`: Registro de notícias enviadas (Persistência).
- `config.json`: Configurações de filtros por servidor.

---

## 🆘 Troubleshooting Comum

| Sintoma | Causa Provável | Solução |
|---------|----------------|---------|
| `Connection Refused` | Node-RED offline | `docker compose restart nodered` |
| `403 Forbidden` | Honeypot Discord | Verifique se você é o `OWNER_ID` no `.env` |
| `News not posting` | Cache de Dedupe | Use `/post_latest` para forçar ou limpe `state.json` |
| `API Rate Limit` | Falta de NVD Key | Adicione `NVD_API_KEY` para aumentar o limite |

---

<p align="center">
  🔐 <b>CyberIntel SOC Deployment Guide</b><br>
  <i>Desenvolvido para ambientes de alta disponibilidade e segurança.</i>
</p>
