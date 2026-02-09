# 🛡️ CyberIntel SOC Bot

### Sistema Avançado de Threat Intelligence & Defesa Ativa

<p align="center">
  <img alt="CyberIntel Bot" src="./icon.png" width="200">
</p>

O **CyberIntel SOC Bot** é uma solução de engenharia de segurança de alta performance desenvolvida para automatizar a coleta, análise e triagem de inteligência cibernética global. O sistema atua como o núcleo de um SOC (Security Operations Center) pessoal, integrando APIs de segurança Tier 1 e monitoramento regulatório internacional em uma interface unificada via Discord e Node-RED.

---

## 🚀 Funcionalidades de Engenharia

### 🛰️ Agregação de Inteligência Multicamadas

* **NVD (NIST)**: Monitoramento em tempo real de novas CVEs com filtragem inteligente por score CVSS v3.1 (Alertas Críticos).
* **Eixo Regulatório Global**: Feed especializado em mudanças legislativas da União Europeia (ENISA/EDPB), EUA (CISA/NIST) e Brasil (ANPD/CERT.br).
* **Threat Feeds Comunitários**: Integração com The Hacker News, BleepingComputer e AlienVault OTX para detecção de campanhas de ataques ativos.

### 🔍 Engine de Análise e Reputação

* **Scanner de URL/Arquivos**: Comandos integrados para consultas via VirusTotal e URLScan.io com retorno de vereditos, screenshots e análise de IoCs (Indicadores de Comprometimento).
* **Visual Severity Mapping**: Sistema de cores dinâmico nos embeds para triagem visual imediata:
  * 🔴 **Crítico**: Vulnerabilidades graves (Ação Imediata).
  * 🔵 **Regulatório**: Mudanças em Compliance e GRC.
  * 🟢 **Intel**: Notícias e tendências de cibersegurança.

### 🛡️ Defesa Ativa (Active Defense)

* **Malandro Protocol**: Lógica proprietária de detecção de intrusão interna para proteger comandos administrativos, com logs de auditoria e resposta automática a usuários não autorizados.
* **Hardening de Infraestrutura**: Deploy totalmente containerizado com Docker, garantindo isolamento de processos e segurança do host.

### 🛠️ Stack Tecnológica

* **Backend**: Python (Asyncio / Discord.py)
* **Containers**: Docker & Docker Compose
* **Telemetria**: Node-RED Dashboard (Monitoramento visual em tempo real)
* **APIs Integradas**: NVD (NIST), VirusTotal, URLScan.io, AlienVault OTX
* **Protocolos de Acesso**: Túnel SSH para acesso seguro ao dashboard de telemetria

---

## ⚡ Início Rápido (Instalação)

### 🐳 Via Docker (Recomendado)

```bash
git clone https://github.com/carmipa/projeto-cyberseguranca-bot.git
cd projeto-cyberseguranca-bot
# Configure seu .env
docker compose up -d --build
```

### 🐍 Via Python Local

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
python main.py
```

---

## 🧰 Guia de Comandos Slash

| Comando | Descrição |
|---------|-----------|
| `/news` | Exibe os 5 últimos alertas de inteligência. |
| `/cve [id]` | Detalha uma vulnerabilidade via NVD. |
| `/scan [url]` | Analisa uma URL suspeita (URLScan.io + VirusTotal). |
| `/status` | Saúde do bot (Uptime, Memória, Stats). |
| `/forcecheck` | [Admin] Força a busca imediata em todos os feeds. |
| `/post_latest`| [Admin] Força a postagem da última notícia (Bypass Cache). |
| `/set_channel`| [Admin] Define o canal oficial do SOC. |
| `/dashboard` | [Admin] Status e link do SOC Dashboard. |

---

## 🌍 Documentação Completa

* 📖 **[Guia Técnico Detalhado (PT-BR)](./README_PT.md)**
* 🐳 **[Guia de Deploy em VPS (Docker)](./DEPLOY.md)**
* 🎮 **[Tutorial de Comandos e Uso](./TUTORIAL.md)**
* 🇺🇸 **[English Documentation](./README_EN.md)**

---

<p align="center">
  🔐 <i>Protegendo o que importa com inteligência proativa.</i>
</p>
