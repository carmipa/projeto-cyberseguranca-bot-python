#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste simples de persistência de dados via volumes Docker.

Como usar (dentro do container):

1. Primeira execução (antes do `docker restart`):

       python scripts/test_persistence.py

   Deve exibir mensagem indicando que o arquivo de teste foi criado.

2. Reinicie o container:

       docker restart cyber-bot

3. Segunda execução (depois do restart):

       python scripts/test_persistence.py

   Se os volumes estiverem montados corretamente, o script detectará
   o arquivo existente e confirmará que os dados sobreviveram ao restart.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from utils.storage import p


def main() -> None:
    data_dir = Path(p("data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    marker_path = data_dir / "persistence_test.json"

    if not marker_path.exists():
        payload = {"created": True}
        marker_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[PHASE 1] Arquivo de teste criado em: {marker_path}")
        print("Reinicie o container Docker e execute este script novamente.")
        return

    try:
        raw = marker_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as exc:  # pragma: no cover - apenas mensagem de diagnóstico
        print(f"[ERRO] Não foi possível ler o arquivo de teste: {exc}")
        return

    if data.get("created"):
        print("[PHASE 2] Arquivo de teste encontrado após docker restart.")
        print("✅ Persistência via volume Docker está funcionando corretamente.")
    else:
        print("[ERRO] Arquivo encontrado, mas conteúdo inesperado:", data)


if __name__ == "__main__":
    main()

