import asyncio
import logging

from app.bootstrap import run_bot


log = logging.getLogger("CyberIntel")


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log.info("🛑 Bot encerrado pelo usuário.")
    except Exception as exc:
        log.exception("🔥 Erro fatal: %s", exc)
