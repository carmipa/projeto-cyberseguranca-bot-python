FROM python:3.10-slim

LABEL maintainer="Paulo André Carminati"
LABEL description="CyberIntel SOC Bot - Sistema de Varredura de Inteligência em Cibersegurança"
LABEL version="1.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Catálogo versionado fora do volume: o bind `./data:/app/data` sombreia /app/data
# inteiro, e o bot lia o sources.json velho do HOST mesmo depois do rebuild.
RUN mkdir -p /app/data /app/logs /app/catalog \
    && cp /app/data/sources.json /app/catalog/sources.json
ENV CATALOG_DIR=/app/catalog

# Saudável só se a última varredura terminou há menos de 2 x LOOP_MINUTES + 15 min.
# O anterior (`import discord`) passava com o bot travado ou desconectado.
HEALTHCHECK --interval=5m --timeout=20s --start-period=20m --retries=2 \
    CMD python scripts/healthcheck.py || exit 1

CMD ["python", "-u", "-m", "app.main"]
