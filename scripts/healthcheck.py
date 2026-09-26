"""
Healthcheck do contêiner: saudável só se a última varredura terminou há menos
de 2 x LOOP_MINUTES + 15 min. Sai 0 (saudável) ou 1 (doente, incluindo batimento
ausente). No arranque o Docker usa start_period para a primeira varredura.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time  # noqa: E402

from utils.heartbeat import ler  # noqa: E402
from utils.storage import p  # noqa: E402


def main() -> int:
    try:
        loop_min = max(5, int(os.getenv("LOOP_MINUTES", "720")))
    except ValueError:
        loop_min = 60
    limite = (2 * loop_min + 15) * 60
    try:
        batimento = ler(p("heartbeat.json"))
        idade = time.time() - float(batimento["ts"])
    except Exception as e:
        print(f"doente: batimento ilegível ({type(e).__name__})")
        return 1
    if batimento.get("conectado") is False:
        print("doente: a última varredura rodou com o Discord desconectado")
        return 1
    if idade > limite:
        print(f"doente: última varredura há {idade/60:.0f} min (limite {limite/60:.0f})")
        return 1
    print(f"saudável: última varredura há {idade/60:.0f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
