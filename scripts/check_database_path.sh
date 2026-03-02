#!/bin/bash
# Verifica se host e container veem o mesmo database.json
echo "=== Host ==="
HOST_FILE="/opt/projeto-cyberseguranca-bot-python/data/database.json"
ls -la "$HOST_FILE" 2>/dev/null || echo "Arquivo não existe"
echo "Itens sent_news:"
python3 -c "
import json
try:
    with open('$HOST_FILE') as f:
        d = json.load(f)
    print(len(d.get('sent_news', [])))
except Exception as e:
    print(e)
" 2>/dev/null

echo ""
echo "=== Container ==="
docker exec cyber-intel-bot python3 -c "
import json, os
path = '/app/data/database.json'
print('Path:', path)
print('Exists:', os.path.exists(path))
try:
    with open(path) as f:
        d = json.load(f)
    print('sent_news count:', len(d.get('sent_news', [])))
except Exception as e:
    print('Erro:', e)
" 2>/dev/null || echo "Container não está rodando"
