# 🧰 Referência de Comandos — CyberIntel SOC Bot

<div align="center">

![CyberIntel Bot](https://img.shields.io/badge/CyberIntel-SOC%20Bot-00FFCC?style=for-the-badge&logo=shield-check&logoColor=white)
![Discord](https://img.shields.io/badge/Discord-Slash%20Commands-5865F2?style=for-the-badge&logo=discord&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)

**Tabela de referência: cada comando e para que serve**

[⬆ Voltar ao README](../README.md) • [🎮 Tutorial de uso](./TUTORIAL.md)

</div>

---

## 📡 Inteligência e Status

| Comando | Para que serve | Quem pode usar |
|---------|----------------|----------------|
| `/news` | Exibe as **5 últimas notícias** de cibersegurança agregadas dos feeds (The Hacker News, BleepingComputer, NVD, etc.). | Todos |
| `/cve [id]` | Busca **detalhes de uma CVE** na base NVD (NIST): score CVSS, descrição, referências. Ex.: `/cve CVE-2021-44228`. | Todos |
| `/scan [url]` | **Analisa uma URL suspeita**: envia para URLScan.io e VirusTotal e devolve links dos relatórios. Requer `URLSCAN_API_KEY` e `VT_API_KEY` no `.env` (veja `.env.example`). | Todos |
| `/status` | Mostra **saúde do bot**: uptime, uso de CPU/RAM, total de notícias postadas e varreduras concluídas. | Todos |
| `/soc_status` | Verifica se as **APIs de inteligência** (NVD, OTX, VirusTotal) estão acessíveis e configuradas. | Todos |
| `/ping` | Mede a **latência** entre o servidor do bot e os servidores do Discord. | Todos |
| `/about` | Exibe **informações técnicas** do sistema (versão, stack, links do projeto). | Todos |
| `/feeds` | Lista **todas as fontes monitoradas** (feeds RSS, APIs, sites) configuradas em `data/sources.json`. | Todos |
| `/help` | Mostra a **lista de comandos** disponíveis, agrupados por categoria. | Todos |

---

## 🖥️ Dashboard e Monitoramento

| Comando | Para que serve | Quem pode usar |
|---------|----------------|----------------|
| `/dashboard` | Abre o **SOC Dashboard** (Node-RED): link para o painel, métricas NVD das últimas 24h (críticas/altas) e status do Node-RED. | Todos |
| `/monitor` | Mostra o **status do SOC** e o link para abrir o painel em tempo real; equivalente ao `/dashboard`. | Todos |

---

## ⚙️ Configuração e Administração

| Comando | Para que serve | Quem pode usar |
|---------|----------------|----------------|
| `/set_channel` | Define o **canal atual** como o canal oficial para receber todos os alertas do SOC. | Admin |
| `/forcecheck` | **Força uma varredura imediata** em todos os feeds e APIs (sem aguardar o intervalo de 30 min). | Admin |
| `/force_scan` | Força a **varredura e posta** as novidades encontradas no canal SOC. | Admin |
| `/post_latest` | **Força a postagem** da notícia mais recente, ignorando o cache (útil para testes). | Admin |
| `/now` | Dispara a **varredura manual** e mostra o progresso no chat. | Admin |
| `/server_log` | Envia as **últimas linhas do log** do servidor (`logs/bot.log`) no Discord (ephemeral). | Admin |
| `/status_db` | Exibe **estatísticas do banco de dados** de inteligência (persistência, métricas). | Admin |

---

## 🔐 Segurança (Defesa Ativa)

| Comando | Para que serve | Quem pode usar |
|---------|----------------|----------------|
| `/admin_panel` | **Painel restrito ao dono**: só o usuário com ID igual ao `OWNER_ID` (configurado no `.env`) tem acesso. Quem mais usar é registrado como intruso (honeypot). | Apenas dono (OWNER_ID) |

---

## 📋 Resumo por permissão

| Permissão | Comandos |
|-----------|----------|
| **Todos** | `/news`, `/cve`, `/scan`, `/status`, `/soc_status`, `/ping`, `/about`, `/feeds`, `/help`, `/dashboard`, `/monitor` |
| **Admin** | `/set_channel`, `/forcecheck`, `/force_scan`, `/post_latest`, `/now`, `/server_log`, `/status_db` |
| **Dono (OWNER_ID)** | `/admin_panel` |

---

<p align="center">
  <sub>CyberIntel SOC Bot — Threat Intelligence & Active Defense</sub><br>
  <sub>Documentação em <a href="../README.md">README</a> • <a href="./TUTORIAL.md">Tutorial</a> • <a href="./DEPLOY.md">Deploy</a></sub>
</p>
