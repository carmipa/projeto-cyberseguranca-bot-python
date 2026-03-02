#!/bin/bash
# Deploy na VPS - execute após git pull
# Uso: cd /opt/projeto-cyberseguranca-bot-python && bash deploy_vps.sh

set -e
cd /opt/projeto-cyberseguranca-bot-python

echo "=== Git pull ==="
git pull origin main

echo "=== Rebuild vps-api (sem cache) ==="
docker compose build --no-cache vps-api

echo "=== Subindo vps-api ==="
docker compose up -d vps-api

echo "=== Logs (últimas 15 linhas) ==="
docker compose logs --tail=15 vps-api
