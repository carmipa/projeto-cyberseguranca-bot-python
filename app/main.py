import asyncio
import logging
import signal

from app.bootstrap import run_bot


log = logging.getLogger("CyberIntel")


async def _principal() -> None:
    """
    Roda o bot tratando SIGTERM como encerramento ordenado.

    O `docker stop` manda SIGTERM ao PID 1; sem tratador, o Python morre na hora
    e o `finally` da varredura em curso não grava o estado (tudo o que ela já
    enviou seria repostado depois do deploy). Cancelando a tarefa principal, o
    asyncio.run cancela as demais e os `finally` rodam dentro dos 30 s do
    stop_grace_period. No Windows não há add_signal_handler: segue sem ele.
    """
    tarefa = asyncio.current_task()
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, tarefa.cancel)
    except (NotImplementedError, RuntimeError, AttributeError):
        pass
    await run_bot()


if __name__ == "__main__":
    try:
        asyncio.run(_principal())
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("🛑 Bot encerrado (sinal de parada).")
    except Exception as exc:
        log.exception("🔥 Erro fatal: %s", exc)
