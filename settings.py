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
LOOP_MINUTES = max(5, LOOP_MINUTES)

# Logging Level (INFO, DEBUG, WARNING, ERROR)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Node-RED Integration
NODE_RED_ENDPOINT = os.getenv("NODE_RED_ENDPOINT", "http://cyber-nodered:1880/cyber-intel")

# URL pública (ou via túnel) do Dashboard
# - Produção (VPS): configure, por exemplo, como "https://seu-dominio-soc/ui"
# - Acesso via túnel SSH: mantenha como "http://localhost:1880/ui" (padrão)
DASHBOARD_PUBLIC_URL = os.getenv("DASHBOARD_PUBLIC_URL", "http://localhost:1880/ui")

# HTTP / Feeds – User-Agent rotativo para se parecer com usuário navegando real
BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0"
]

# Threat Intel APIs
NVD_API_KEY = os.getenv("NVD_API_KEY", "")
URLSCAN_API_KEY = os.getenv("URLSCAN_API_KEY", "")
OTX_API_KEY = os.getenv("OTX_API_KEY", "")
VT_API_KEY = os.getenv("VT_API_KEY", "")
GREYNOISE_API_KEY = os.getenv("GREYNOISE_API_KEY", "")
SHODAN_API_KEY = os.getenv("SHODAN_API_KEY", "")

# Scanner hardening
try:
    FEED_FETCH_MAX_RETRIES = int(os.getenv("FEED_FETCH_MAX_RETRIES", "3"))
except ValueError:
    FEED_FETCH_MAX_RETRIES = 3
FEED_FETCH_MAX_RETRIES = max(1, FEED_FETCH_MAX_RETRIES)

try:
    FEED_FETCH_RETRY_BASE_DELAY = float(os.getenv("FEED_FETCH_RETRY_BASE_DELAY", "3.0"))
except ValueError:
    FEED_FETCH_RETRY_BASE_DELAY = 3.0
FEED_FETCH_RETRY_BASE_DELAY = max(1.0, FEED_FETCH_RETRY_BASE_DELAY)

try:
    MAX_CONCURRENT_FEEDS = int(os.getenv("MAX_CONCURRENT_FEEDS", "3"))
except ValueError:
    MAX_CONCURRENT_FEEDS = 3
MAX_CONCURRENT_FEEDS = max(1, MAX_CONCURRENT_FEEDS)
