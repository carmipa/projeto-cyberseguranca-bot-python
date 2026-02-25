# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# Obrigatório
TOKEN = os.getenv("DISCORD_TOKEN")
# ID do Dono para comandos restritos (Active Defense)
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Operação (opcional via env)
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
try:
    LOOP_MINUTES = int(os.getenv("LOOP_MINUTES", "30"))
except ValueError:
    LOOP_MINUTES = 60

# Logging Level (INFO, DEBUG, WARNING, ERROR)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Node-RED Integration
NODE_RED_ENDPOINT = os.getenv("NODE_RED_ENDPOINT", "http://cyber-nodered:1880/cyber-intel")

# URL pública (ou via túnel) do Dashboard
# - Produção (VPS): configure, por exemplo, como "https://seu-dominio-soc/ui"
# - Acesso via túnel SSH: mantenha como "http://localhost:1880/ui" (padrão)
DASHBOARD_PUBLIC_URL = os.getenv("DASHBOARD_PUBLIC_URL", "http://localhost:1880/ui")

# HTTP / Feeds – User-Agent para evitar bloqueio em feeds e sites
# Padrão: identificação tipo Googlebot (muitos sites liberam para crawlers legítimos)
# Para voltar a um browser genérico: FEED_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ..."
FEED_USER_AGENT = os.getenv(
    "FEED_USER_AGENT",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
).strip()

# Threat Intel APIs
NVD_API_KEY = os.getenv("NVD_API_KEY", "")
URLSCAN_API_KEY = os.getenv("URLSCAN_API_KEY", "")
OTX_API_KEY = os.getenv("OTX_API_KEY", "")
VT_API_KEY = os.getenv("VT_API_KEY", "")
GREYNOISE_API_KEY = os.getenv("GREYNOISE_API_KEY", "")
SHODAN_API_KEY = os.getenv("SHODAN_API_KEY", "")
