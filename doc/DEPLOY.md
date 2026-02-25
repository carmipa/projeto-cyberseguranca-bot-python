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
DEPLOY_ENV='production'

# APIs Gratuitas (todas têm planos free - opcional)
# NVD: Opcional - funciona sem chave, mas com limite menor
# Obtenha em: https://nvd.nist.gov/developers/request-an-api-key
NVD_API_KEY=''
# OTX: Gratuita - Registre em: https://otx.alienvault.com/api
OTX_API_KEY=''
# URLScan: Gratuita - Registre em: https://urlscan.io/user/signup
URLSCAN_API_KEY=''
# VirusTotal: Gratuita (limitada) - Registre em: https://www.virustotal.com/gui/join-us
VT_API_KEY=''
# GreyNoise Community: Gratuita - Registre em: https://www.greynoise.io/viz/signup
GREYNOISE_API_KEY=''
# Shodan: Gratuita (limitada) - Registre em: https://account.shodan.io/register
SHODAN_API_KEY=''

# Dashboard Node-RED (escolha uma opção abaixo)
# Opção 1: Túnel SSH (recomendado - mais seguro)
DASHBOARD_PUBLIC_URL='http://localhost:1880/ui'
# Opção 2: IP público direto (menos seguro, apenas para testes)
# DASHBOARD_PUBLIC_URL='http://IP_DA_SUA_VPS:1880/ui'
# Opção 3: Domínio com HTTPS (produção com reverse proxy)
# DASHBOARD_PUBLIC_URL='https://seu-dominio-soc.com/ui'
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

### 2. Dashboard SOC Seguro (Configuração de Acesso)

O painel Node-RED pode ser acessado de três formas diferentes, dependendo do seu nível de segurança:

#### 🔒 Opção 1: Túnel SSH (Recomendado - Mais Seguro)

Por segurança, o painel Node-RED (`port 1880`) **não deve ser aberto no firewall**. Use um Túnel SSH para acessá-lo localmente:

**No seu computador pessoal:**

```bash
ssh -L 1880:localhost:1880 usuario@ip-da-vps
```

**Configuração no `.env`:**
```env
DASHBOARD_PUBLIC_URL=http://localhost:1880/ui
```

Agora, quando você usar o comando `/dashboard` no Discord, o botão abrirá `http://localhost:1880/ui` no seu navegador local. O tráfego estará criptografado pelo SSH.

#### 🌐 Opção 2: IP Público Direto (Menos Seguro - Apenas para Testes)

⚠️ **Atenção:** Esta opção expõe o dashboard publicamente. Use apenas em ambientes de teste.

**1. Abra a porta no firewall:**
```bash
sudo ufw allow 1880/tcp
```

**2. Configure no `.env`:**
```env
DASHBOARD_PUBLIC_URL=http://IP_DA_SUA_VPS:1880/ui
```

**3. Reinicie os containers:**
```bash
docker compose restart cyber-bot
```

Agora o comando `/dashboard` no Discord abrirá diretamente o IP da VPS.

#### 🔐 Opção 3: Domínio com HTTPS (Produção - Mais Seguro)

Para produção, configure um reverse proxy (Nginx/Traefik) com HTTPS:

**1. Configure seu reverse proxy para apontar para `nodered:1880`**

**2. Configure no `.env`:**
```env
DASHBOARD_PUBLIC_URL=https://seu-dominio-soc.com/ui
```

**3. Reinicie os containers:**
```bash
docker compose restart cyber-bot
```

Agora o comando `/dashboard` no Discord abrirá seu domínio seguro com HTTPS.

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
