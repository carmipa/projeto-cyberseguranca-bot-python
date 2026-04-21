#!/bin/bash
# Deploy na VPS - execute após git pull
# Uso: cd /opt/projeto-cyberseguranca-bot-python && bash deploy_vps.sh

set -e
cd /opt/projeto-cyberseguranca-bot-python

echo "=== Git pull ==="
git pull origin main

echo "=== Rebuild cyber-bot e vps-api (sem cache) ==="
docker compose build --no-cache cyber-bot vps-api

echo "=== Subindo cyber-bot e vps-api ==="
docker compose up -d cyber-bot vps-api

echo "=== Logs (últimas 20 linhas) ==="
docker compose logs --tail=20 cyber-bot vps-api
