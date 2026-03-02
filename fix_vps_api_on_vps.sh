#!/bin/bash
# Execute na VPS: bash fix_vps_api_on_vps.sh
# Corrige o vps_api.py para usar logging padrão em vez de core.logger

cd /opt/projeto-cyberseguranca-bot-python || exit 1
cp vps_api.py vps_api.py.bak 2>/dev/null

python3 << 'PYEOF'
import re
with open("vps_api.py", "r", encoding="utf-8") as f:
    content = f.read()

if "from core.logger" not in content:
    print("vps_api.py já usa logging padrão.")
    exit(0)

content = content.replace(
    "from core.logger import get_logger, log_exception",
    "import logging\nlogging.basicConfig(level=logging.INFO)"
)
content = content.replace("logger = get_logger(__name__)", 'logger = logging.getLogger("vps_api")')
content = re.sub(r'log_exception\(logger,\s*e,\s*', 'logger.exception(', content)

with open("vps_api.py", "w", encoding="utf-8") as f:
    f.write(content)
print("vps_api.py corrigido.")
PYEOF

docker compose build --no-cache vps-api && docker compose up -d vps-api
echo "Verifique: docker compose logs --tail=15 vps-api"
