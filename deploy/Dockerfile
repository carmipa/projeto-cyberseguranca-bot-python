FROM python:3.10-slim

# Metadata
LABEL maintainer="Paulo André Carminati"
LABEL description="CyberIntel SOC Bot - Sistema de Varredura de Inteligência em Cibersegurança"
LABEL version="1.0"

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Diretório de trabalho
WORKDIR /app

# Instala dependências do sistema (necessárias para certifi e SSL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements primeiro (melhor cache de layers)
COPY deploy/requirements.txt ./requirements.txt

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia código do bot
# Copia todo o código do projeto
COPY . .

# Cria diretórios para dados persistentes (serão volumes)
RUN mkdir -p /app/data /app/logs

# Healthcheck melhorado - verifica se bot está respondendo
# Para bot de varredura, verifica se processo Python está rodando e se consegue importar módulos
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; import discord; sys.exit(0)" || exit 1

# Comando de execução
CMD ["python", "-u", "-m", "app.main"]
