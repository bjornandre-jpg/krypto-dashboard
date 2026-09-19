"""KuCoin offentlige endepunkter (spot + futures). Ingen nøkler, kun lesing."""
import time
from .http import get_json

SPOT = "https://api.kucoin.com"
FUT = "https://api-futures.kucoin.com"
PERIODE_SEK = {"1hour": 3600, "4hour": 14400, "1day": 86400}


def alle_tickere():
    d = get_json(SPOT + "/api/v1/market/allTickers")["data"]["ticker"]
    return {t["symbol"]: t for t in d}


def priser(tickere=None):
    tickere = tickere or alle_tickere()
    ut = {}
    for s, t in tickere.items():
        try:
            if t.get("last"):
                ut[s] = float(t["last"])
        except (TypeError, ValueError):
            pass
    return ut


def candles(symbol, ctype, antall, kun_lukkede=True):
    """[(ts, open, high, low, close, volum)] stigende. Maks 1500 per kall - blar bakover."""
    per = PERIODE_SEK[ctype]
    slutt = int(time.time())
    rader = {}
    while len(rader) < antall:
        start = slutt - per * 1500
        data = get_json(SPOT + "/api/v1/market/candles",
                        {"type": ctype, "symbol": symbol, "startAt": start, "endAt": slutt})["data"]
        if not data:
            break
        for r in data:
            ts = int(r[0])
            rader[ts] = (ts, float(r[1]), float(r[3]), float(r[4]), float(r[2]), float(r[5]))
        eldste = min(int(r[0]) for r in data)
        if len(data) < 1400 or eldste >= slutt:
            break
        slutt = eldste - 1
        time.sleep(0.15)
    ut = sorted(rader.values())
    if kun_lukkede:
        naa = time.time()
        ut = [c for c in ut if c[0] + per <= naa]
    return ut[-antall:]


def futures_symbol(spot_symbol):
    base = spot_symbol.split("-")[0]
    return ("XBT" if base == "BTC" else base) + "USDTM"


def aktive_kontrakter():
    d = get_json(FUT + "/api/v1/contracts/active")["data"]
    return {c["symbol"]: c for c in d}


def funding_naa(spot_symbol, kontrakter):
    """Nåværende funding rate, None hvis mynten ikke har USDT-perp."""
    c = kontrakter.get(futures_symbol(spot_symbol))
    if not c or c.get("fundingFeeRate") is None:
        return None
    return float(c["fundingFeeRate"])


def funding_historikk(spot_symbol, fra_ms, til_ms):
    """[(ts_ms, rate)] stigende. Maks 100 punkter per kall -> blar i vinduer."""
    sym = futures_symbol(spot_symbol)
    ut = {}
    vindu = 100 * 8 * 3600 * 1000
    t = fra_ms
    while t < til_ms:
        slutt = min(t + vindu, til_ms)
        try:
            d = get_json(FUT + "/api/v1/contract/funding-rates",
                         {"symbol": sym, "from": t, "to": slutt}).get("data") or []
        except RuntimeError:
            d = []
        for p in d:
            ut[int(p["timepoint"])] = float(p["fundingRate"])
        t = slutt
        time.sleep(0.1)
    return sorted(ut.items())
