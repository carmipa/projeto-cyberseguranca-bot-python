# 🎮 Tutorial de Comandos — CyberIntel SOC System

Este guia explica detalhadamente como utilizar todos os comandos do sistema **CyberIntel** para monitoramento de ameaças.

---

## 🔐 Comandos de Administração

*Exigem permissão de **Administrador** no servidor.*

### `/set_channel`

Define o canal atual para onde o bot enviará todos os alertas de inteligência em tempo real.

- **Uso:** Digite o comando no canal onde deseja centralizar os logs.

### `/forcecheck`

Força o bot a realizar uma varredura completa em todos os feeds RSS e APIs imediatamente.

- **Uso:** Útil para testes ou quando uma notícia urgente acaba de ser publicada.

### `/post_latest`

Força a postagem da notícia **mais recente** encontrada, mesmo que ela já tenha sido postada anteriormente.

- **Uso:** Ideal para validar se os embeds e botões (WhatsApp/Email) estão aparecendo corretamente no SOC.

### `/dashboard`

Exibe o status de saúde do SOC Dashboard (Node-RED), **métricas NVD das últimas 24h** (CVEs críticas e altas) e um botão para abrir o painel. As métricas são obtidas em tempo real da API NIST NVD e também enviadas ao Node-RED para o gauge do painel.

**Configuração:** O link do dashboard é configurável via variável `DASHBOARD_PUBLIC_URL` no arquivo `.env`:
- **Túnel SSH** (recomendado): `DASHBOARD_PUBLIC_URL=http://localhost:1880/ui`
- **IP público direto**: `DASHBOARD_PUBLIC_URL=http://IP_DA_VPS:1880/ui`
- **Domínio com HTTPS**: `DASHBOARD_PUBLIC_URL=https://seu-dominio-soc.com/ui`

Quando você clicar no botão "Abrir Painel" no Discord, ele abrirá automaticamente a URL configurada.

### `/monitor`

Alias do `/dashboard`: mostra o status do SOC e oferece o link para abrir o dashboard em tempo real, incluindo as métricas NVD (24h).

### `/server_log`

Exibe diretamente no Discord as **últimas linhas do log do servidor** (`logs/bot.log`), facilitando troubleshooting sem precisar acessar o terminal ou a VPS.

- **Uso:** Ideal para inspecionar rapidamente erros recentes, falhas de integração de APIs ou problemas de permissão.
- **Segurança:** Saída é enviada como mensagem *ephemeral* e o comando é restrito a administradores.
---

## 📡 Inteligência e Varredura

*Disponíveis para todos os analistas no servidor.*

### `/news`

Exibe um resumo das **5 últimas notícias críticas** detectadas pelos filtros de cibersegurança do bot.

### `/cve [id]`

Busca informações técnicas detalhadas sobre uma vulnerabilidade na **NVD (NIST)**. O ID é obrigatório no formato `CVE-ANO-NÚMERO` (ex.: `CVE-2021-44228`).

- Retorna: score CVSS, severidade, descrição, data de publicação e referências.
- Requer API NVD configurada (opcional; sem chave o rate limit é menor).

### `/scan [url]`

Submete uma URL para análise forense externa simultânea no **URLScan.io** e **VirusTotal**.

- Retorna links para os relatórios completos de reputação e comportamento.
- **Configuração:** Para o comando funcionar, adicione no `.env` as chaves `URLSCAN_API_KEY` e `VT_API_KEY` (ambas gratuitas; links de registro estão no `.env.example`).

### `/soc_status`

Checa a conectividade do bot com os serviços externos de inteligência (NVD, OTX, VT).

---

## 📊 Sistema e Utilitários

### `/status`

Relatório de saúde do sistema:

- **Uptime:** Há quanto tempo o bot está rodando sem quedas.
- **Recursus:** Uso atual de RAM e CPU na VPS.
- **Stats:** Total de notícias processadas e enviadas.

### `/now`

Dispara a varredura manual e dá um feedback visual imediato no chat do progresso da coleta de dados.

### `/ping`

Verifica a latência entre o servidor da sua VPS e os servidores do Discord.

### `/help`

Exibe no Discord a lista de comandos disponíveis, agrupados por categoria (Inteligência, Configuração, Sistema).

### `/about`

Mostra informações técnicas do CyberIntel (versão, stack, links).

### `/feeds`

Lista todas as fontes monitoradas (feeds RSS, APIs, sites) configuradas em `data/sources.json`.

### `/status_db`

Exibe estatísticas do banco de dados de inteligência (persistência, métricas). Apenas administradores.

### `/force_scan`

Força uma varredura imediata de todas as fontes e posta as novidades no canal SOC. Equivalente operacional a `/forcecheck` com postagem automática.

---

## 🔐 Segurança (Defesa Ativa)

### `/admin_panel`

Painel **restrito ao dono** do bot. Só o usuário cujo ID do Discord for igual ao `OWNER_ID` (configurado no `.env`) tem acesso.

- **Uso:** Configure `OWNER_ID=seu_id` no `.env`. Quem não for o dono e usar o comando é registrado como intruso (honeypot de defesa ativa).
- **Resposta ao dono:** "✅ Bem-vindo, Comandante. Sistemas operacionais."

📖 **Tabela completa:** [COMANDOS_BOT.md](./COMANDOS_BOT.md) — todos os comandos em tabela com "para que serve".

---

## 💡 Dicas de Especialistas

1. **Compartilhamento SOC**: Utilize os botões `WhatsApp` e `Email` abaixo de cada notícia para encaminhar alertas críticos instantaneamente para equipes de resposta.
2. **Cold Start**: Ao rodar o bot pela primeira vez, ele enviará os 3 destaques mais recentes de cada fonte. Isso é normal e serve para popular seu canal SOC inicial.
3. **Hardening**: Se o `/dashboard` reportar `OFFLINE`, verifique se o túnel SSH está ativo em sua máquina local.

---

<p align="center">
  🔐 <i>Sistema CyberIntel — Defesa Cibernética Baseada em Inteligência.</i>
</p>
