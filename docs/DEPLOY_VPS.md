# Deploy na VPS – Bot + API para o Painel Windows

Para o painel CyberBot GRC exibir as notícias, **dois processos** devem rodar na VPS:

## Serviço systemd (cyberbot-api)

O unit file `cyberbot-api.service` deve ter **WorkingDirectory** definido:

```bash
sudo cp deploy/cyberbot-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart cyberbot-api
```

Se o serviço falhar, rode manualmente para ver o erro:
```bash
cd /opt/projeto-cyberseguranca-bot-python
./deploy/run_vps_api.sh
# ou: .venv/bin/python3 -m uvicorn web.vps_api:app --host 0.0.0.0 --port 8000
```

## 1. Bot do Discord (porta 8080)

```bash
cd /opt/projeto-cyberseguranca-bot-python  # ou seu caminho
source .venv/bin/activate
python app/main.py
```

O bot inicia o web server na porta **8080** (trigger_scan, sync_from_discord).

## 2. API para o painel (porta 8000)

**Opção A - Docker (recomendado):** A vps_api agora roda no docker-compose e compartilha o volume `./data` com o bot. Não é necessário rodar cyberbot-api via systemd.

```bash
# Desabilite o systemd se estiver usando Docker para vps_api
sudo systemctl stop cyberbot-api
sudo systemctl disable cyberbot-api
```

**Opção B - Systemd:** Em outro terminal na mesma VPS:

```bash
cd /opt/projeto-cyberseguranca-bot-python
source .venv/bin/activate
pip install fastapi uvicorn httpx  # se ainda não tiver
uvicorn web.vps_api:app --host 0.0.0.0 --port 8000
```

## Checklist

| Item | Verificar |
|------|-----------|
| `data/config.json` | Tem `channel_id` do canal de notícias? |
| `data/sources.json` | Tem feeds configurados? |
| Portas | 8080, 8000 e 1880 publicadas só em 127.0.0.1 (a vps_api não tem autenticação); acesso por túnel SSH |
| Bot online | Conectado ao Discord? |

## Teste rápido

```bash
# Deve retornar JSON com sent_news
curl http://localhost:8000/data

# Deve retornar {"status":"ok","added":N}
curl -X POST http://localhost:8000/sync_from_discord
```

## Deploy da versão de 2026-09-26 (auditoria) — procedimento exato

A VPS tinha, em 26/09/2026, **duas alterações locais** que fazem o `git pull`
abortar: `docker-compose.yml` (portas em 127.0.0.1, agora no repositório) e
`data/database.json` (dado vivo, 5,5 MB, que deixou de ser versionado). Pare o
bot antes, para ele não gravar no `database.json` durante a troca.

```bash
cd /opt/projeto-cyberseguranca-bot-python
TS=$(date +%Y%m%d-%H%M%S)
docker compose stop cyber-bot vps-api
tar czf /root/backup-cyberbot-$TS.tgz data logs docker-compose.yml .env
git rev-parse HEAD > /root/backup-cyberbot-$TS-commit.txt
cp -a data/database.json /root/database-$TS.json
git checkout -- docker-compose.yml data/database.json   # só para o pull passar
git pull --ff-only
cp -a /root/database-$TS.json data/database.json        # dado vivo de volta (agora ignorado pelo git)
docker compose build cyber-bot vps-api
docker compose up -d cyber-bot vps-api
```

**Conferir depois (cada linha tem de aparecer):**

```bash
docker compose logs cyber-bot | grep "catálogo caminho=/app/catalog/sources.json"   # fontes=34
docker compose logs cyber-bot | grep "scan.veredito"                                 # OK/ATENCAO/ANOMALIA com motivo
ss -ltnp | grep -E ':(8080|8000|1880) '                                              # só 127.0.0.1
docker ps --format '{{.Names}} {{.Status}}' | grep cyber-intel-bot                   # healthy após a 1ª varredura (até 20 min)
```

**Primeira varredura:** as 8 fontes do YouTube e o Ars Technica mudaram de
endereço e entram em partida a frio — publicam só itens dos últimos 7 dias.

**Rollback:** `docker compose stop cyber-bot vps-api`, `git checkout $(cat /root/backup-cyberbot-$TS-commit.txt)`,
`tar xzf /root/backup-cyberbot-$TS.tgz -C /opt/projeto-cyberseguranca-bot-python`, `docker compose up -d --build cyber-bot vps-api`.

**Node-RED:** o endpoint `/cyber-intel` responde 404 na VPS (747 avisos entre
29/08 e 26/09): o fluxo não está carregado em `node-red-data/`. O `deploy/flows.json`
do repositório era **JSON inválido** (`True`/`False` do Python) até 26/09 — o
Node-RED não o importaria; corrigido e guardado por teste. Importar esse arquivo
no Node-RED deve criar o endpoint (não verificado na VPS). Enquanto isso o bot
pausa o push por 6 h e avisa uma vez.
