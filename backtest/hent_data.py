"""Henter og cacher historikk for backtesten (4t candles, Fear&Greed, funding)."""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from felles import kucoin, fear_greed

CACHE = os.environ.get("BT_CACHE", "/tmp/bt_cache")
os.makedirs(CACHE, exist_ok=True)


def hent_mynt(sym, ctype="4hour", antall=6570):
    f = os.path.join(CACHE, f"{sym}_{ctype}.json")
    if not os.path.exists(f):
        c = kucoin.candles(sym, ctype, antall)
        json.dump(c, open(f, "w"))
    f2 = os.path.join(CACHE, f"{sym}_funding.json")
    if not os.path.exists(f2):
        til = int(time.time() * 1000)
        fh = kucoin.funding_historikk(sym, til - 3 * 366 * 86400 * 1000, til)
        json.dump(fh, open(f2, "w"))
    return sym


if __name__ == "__main__":
    from krypto50.univers import last
    f = os.path.join(CACHE, "fng.json")
    if not os.path.exists(f):
        json.dump(fear_greed.historikk(), open(f, "w"))
    mynter = last()
    with ThreadPoolExecutor(4) as ex:
        for s in ex.map(hent_mynt, mynter):
            print(s, flush=True)
