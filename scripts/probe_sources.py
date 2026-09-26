"""
Sonda de fontes do catálogo, pelo MESMO caminho de download da produção
(core.scanner._baixar_feed), com estado HTTP vazio (sem cache: 304 esconderia
fonte morta).

Critério de saúde (manutencao-de-bots §4): desfecho ok, >= 1 entrada, item mais
recente com < 180 dias, e o TÍTULO do feed impresso ao lado do nome configurado
(fonte que "funciona" entregando o canal de outra pessoa só aparece assim).

Calibração antes do veredito: um controle positivo que TEM de passar e um
negativo que TEM de reprovar; se qualquer um errar, a sonda sai 2 (NÃO
VERIFICOU) sem julgar o catálogo.

Saída: 0 todas saudáveis · 1 alguma fora do critério · 2 não verificou.

ATENÇÃO: 403 e páginas HTML dependem do IP de quem pergunta. Medição feita do
desktop não decide o destino de fonte que roda na VPS.

Uso: python scripts/probe_sources.py [--youtube] [--url URL ...]
"""
import argparse
import asyncio
import os
import ssl
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp  # noqa: E402
import certifi  # noqa: E402

from core import scanner  # noqa: E402

CONTROLE_POSITIVO = "https://krebsonsecurity.com/feed/"
CONTROLE_NEGATIVO = "https://feed.dominio-que-nao-existe.invalid/rss"
IDADE_MAXIMA_DIAS = 180


async def sondar(urls, meta):
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    sem = asyncio.Semaphore(2)
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_ctx),
        timeout=aiohttp.ClientTimeout(total=30),
        headers={"Accept": "application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.8"},
    ) as s:
        return await asyncio.gather(*(scanner._baixar_feed(s, u, sem, False, {}, meta) for u in urls))


def avaliar(r):
    """(saudável, texto) de um FeedResultado."""
    if r.desfecho != scanner.DESFECHO_OK:
        return False, f"{r.desfecho}: {r.motivo}"
    datas = [scanner.parse_entry_dt(e) for e in r.entradas]
    datas = [d if d.tzinfo else d.replace(tzinfo=timezone.utc) for d in datas if d]
    idade = (datetime.now(timezone.utc) - max(datas)).days if datas else None
    if idade is None:
        return False, f"{len(r.entradas)} entradas, NENHUMA com data"
    if idade > IDADE_MAXIMA_DIAS:
        return False, f"{len(r.entradas)} entradas, a mais recente tem {idade} dias"
    return True, f"{len(r.entradas)} entradas, mais recente há {idade} dia(s)"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--youtube", action="store_true", help="só fontes do YouTube")
    ap.add_argument("--url", nargs="*", help="sondar estas URLs em vez do catálogo")
    a = ap.parse_args()

    meta = scanner.load_sources_meta()
    urls = a.url or [u for u in scanner.load_sources() if not a.youtube or "youtube.com" in u]
    if not urls:
        print("NÃO VERIFICOU: nenhuma URL para sondar (catálogo vazio?)")
        return 2

    pos, neg = await sondar([CONTROLE_POSITIVO, CONTROLE_NEGATIVO], meta)
    ok_pos, txt_pos = avaliar(pos)
    ok_neg, txt_neg = avaliar(neg)
    print(f"calibração: positivo={'OK' if ok_pos else 'FALHOU'} ({txt_pos}) | negativo={'reprovou (certo)' if not ok_neg else 'PASSOU (instrumento cego)'} ({txt_neg})")
    if not ok_pos or ok_neg:
        print("NÃO VERIFICOU: calibração falhou; o veredito sobre o catálogo não vale.")
        return 2

    resultados = await sondar(urls, meta)
    fora = 0
    for u, r in zip(urls, resultados):
        saudavel, texto = avaliar(r)
        fora += not saudavel
        nome = meta.get(u, {}).get("name", "")
        print(f"{'OK  ' if saudavel else 'FORA'} | {nome[:30]:30} | titulo='{r.titulo[:30]}' | {texto} | {u}")
    print(f"\n{len(urls) - fora} saudáveis / {fora} fora do critério / {len(urls)} sondadas")
    return 1 if fora else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
