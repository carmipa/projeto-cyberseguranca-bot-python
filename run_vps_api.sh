#!/bin/bash
# Script para rodar vps_api manualmente (debug)
# Uso: ./run_vps_api.sh
cd "$(dirname "$0")"
.venv/bin/python3 -m uvicorn vps_api:app --host 0.0.0.0 --port 8000
