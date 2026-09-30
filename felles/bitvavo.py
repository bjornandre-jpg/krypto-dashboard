"""Bitvavo sitt offentlige API (kun lesing, ingen nøkler).

Bitvavo er EUR-basert: alle par er <MYNT>-EUR, så både kurser og
porteføljeverdi regnes i euro. Candles hentes 1440 om gangen og
blas bakover med end-parameteren.
"""
import time

from .http import get_json

BASE = "https://api.bitvavo.com/v2"
PERIODE_SEK = {"1h": 3600, "4h": 14400, "1d": 86400}


def markeder(kun_eur=True):
    """{'BTC-EUR': {...}} for alle markeder som handles."""
    d = get_json(BASE + "/markets")
    return {m["market"]: m for m in d
            if m.get("status") == "trading" and (not kun_eur or m.get("quote") == "EUR")}


def tickere():
    """{'BTC-EUR': {last, volume, ...}} med 24-timers tall."""
    return {t["market"]: t for t in get_json(BASE + "/ticker/24h")}


def bok():
    """Beste kjøps- og salgskurs per marked, brukt til å måle spread."""
    return get_json(BASE + "/ticker/book")


def spreads(b=None):
    """{'BTC-EUR': spread i prosent}."""
    ut = {}
    for x in (b if b is not None else bok()):
        try:
            bid, ask = float(x["bid"]), float(x["ask"])
            if bid > 0 and ask > 0:
                ut[x["market"]] = (ask - bid) / ((ask + bid) / 2) * 100
        except (TypeError, ValueError, KeyError):
            pass
    return ut


def priser(t=None):
    ut = {}
    for m, x in (t or tickere()).items():
        try:
            if x.get("last"):
                ut[m] = float(x["last"])
        except (TypeError, ValueError):
            pass
    return ut


def omsetning_24t(t=None):
    """Omsetning i EUR siste døgn, brukt til å rangere universet."""
    ut = {}
    for m, x in (t or tickere()).items():
        try:
            ut[m] = float(x.get("volume") or 0) * float(x.get("last") or 0)
        except (TypeError, ValueError):
            pass
    return ut


def candles(market, interval, antall, kun_lukkede=True):
    """[(ts_sek, open, high, low, close, volum)] stigende i tid.

    Bitvavo gir nyeste først, maks 1440 per kall; vi blar bakover med end.
    """
    per = PERIODE_SEK[interval]
    rader = {}
    end = int(time.time() * 1000)
    while len(rader) < antall:
        d = get_json(f"{BASE}/{market}/candles",
                     {"interval": interval, "limit": 1440, "end": end})
        if not d:
            break
        for r in d:
            ts = int(r[0]) // 1000
            rader[ts] = (ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
        eldste = min(int(r[0]) for r in d)
        if eldste >= end or len(d) < 1400:   # ikke mer historikk
            break
        end = eldste - 1
        time.sleep(0.12)
    ut = sorted(rader.values())
    if kun_lukkede:
        naa = time.time()
        ut = [c for c in ut if c[0] + per <= naa]
    return ut[-antall:]
