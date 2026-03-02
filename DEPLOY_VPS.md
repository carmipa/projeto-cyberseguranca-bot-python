# Deploy na VPS – Bot + API para o Painel Windows

Para o painel CyberBot GRC exibir as notícias, **dois processos** devem rodar na VPS:

## Serviço systemd (cyberbot-api)

O unit file `cyberbot-api.service` deve ter **WorkingDirectory** definido:

```bash
sudo cp cyberbot-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart cyberbot-api
```

Se o serviço falhar, rode manualmente para ver o erro:
```bash
cd /opt/projeto-cyberseguranca-bot-python
./run_vps_api.sh
# ou: .venv/bin/python3 -m uvicorn vps_api:app --host 0.0.0.0 --port 8000
```

## 1. Bot do Discord (porta 8080)

```bash
cd /opt/projeto-cyberseguranca-bot-python  # ou seu caminho
source .venv/bin/activate
python main.py
```

O bot inicia o web server na porta **8080** (trigger_scan, sync_from_discord).

## 2. API para o painel (porta 8000)

Em **outro terminal** na mesma VPS:

```bash
cd /opt/projeto-cyberseguranca-bot-python
source .venv/bin/activate
pip install fastapi uvicorn httpx  # se ainda não tiver
uvicorn vps_api:app --host 0.0.0.0 --port 8000
```

## Checklist

| Item | Verificar |
|------|-----------|
| `config.json` | Tem `channel_id` do canal de notícias? |
| `sources.json` | Tem feeds configurados? |
| Firewall | Portas 8000 e 8080 abertas? |
| Bot online | Conectado ao Discord? |

## Teste rápido

```bash
# Deve retornar JSON com sent_news
curl http://localhost:8000/data

# Deve retornar {"status":"ok","added":N}
curl -X POST http://localhost:8000/sync_from_discord
```
