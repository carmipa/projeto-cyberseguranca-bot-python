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

Exibe o status de saúde do SOC Dashboard (Node-RED) e fornece um botão clicável para abrir o painel.

**Configuração:** O link do dashboard é configurável via variável `DASHBOARD_PUBLIC_URL` no arquivo `.env`:
- **Túnel SSH** (recomendado): `DASHBOARD_PUBLIC_URL=http://localhost:1880/ui`
- **IP público direto**: `DASHBOARD_PUBLIC_URL=http://IP_DA_VPS:1880/ui`
- **Domínio com HTTPS**: `DASHBOARD_PUBLIC_URL=https://seu-dominio-soc.com/ui`

Quando você clicar no botão "Abrir Painel" no Discord, ele abrirá automaticamente a URL configurada.

---

## 📡 Inteligência e Varredura

*Disponíveis para todos os analistas no servidor.*

### `/news`

Exibe um resumo das **5 últimas notícias críticas** detectadas pelos filtros de cibersegurança do bot.

### `/cve [id]`

Busca informações técnicas detalhadas sobre uma vulnerabilidade na NVD (NIST).

- **Sem ID:** Lista as vulnerabilidades mais recentes do dia.
- **Com ID:** Trás detalhes como Score CVSS, descrição e links de mitigação.

### `/scan [url]`

Submete uma URL para análise forense externa simultânea no **URLScan.io** e **VirusTotal**.

- Retorna links para os relatórios completos de reputação e comportamento.

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

---

## 💡 Dicas de Especialistas

1. **Compartilhamento SOC**: Utilize os botões `WhatsApp` e `Email` abaixo de cada notícia para encaminhar alertas críticos instantaneamente para equipes de resposta.
2. **Cold Start**: Ao rodar o bot pela primeira vez, ele enviará os 3 destaques mais recentes de cada fonte. Isso é normal e serve para popular seu canal SOC inicial.
3. **Hardening**: Se o `/dashboard` reportar `OFFLINE`, verifique se o túnel SSH está ativo em sua máquina local.

---

<p align="center">
  🔐 <i>Sistema CyberIntel — Defesa Cibernética Baseada em Inteligência.</i>
</p>
