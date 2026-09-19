"""Bygger myntuniverset for Krypto50: topp 50 etter USDT-volum på KuCoin,
med minst 365 dagers historikk, uten girede tokens, stablecoins,
wrapped/staking-duplikater og gull-tokens.

Kjør: python -m krypto50.univers   (skriver krypto50/univers.json)
"""
import json
import os
import re
import time

from felles import kucoin
from felles.portefolje import utc_iso

ANTALL = 50
MIN_DAGER = 365
STABLE = {"USDT", "USDC", "DAI", "TUSD", "FDUSD", "USDD", "PYUSD", "USDE", "USD1", "BUSD",
          "USDP", "USDJ", "UST", "USTC", "FRAX", "GUSD", "USDS", "RLUSD", "USD0", "EURC",
          "EURT", "EUR", "AEUR", "USDQ", "USDR", "LUSD", "CRVUSD", "SUSD", "USDX", "USDG",
          "XUSD", "USDB", "BFUSD", "USDF", "SUSDE", "DEUSD", "USDA", "USDY", "USDTB"}
WRAPPED = {"WBTC", "WETH", "STETH", "WSTETH", "CBETH", "RETH", "WBETH", "BETH", "JITOSOL",
           "MSOL", "BNSOL", "WEETH", "EZETH", "CBBTC", "BTCB", "WBNB", "WSOL", "STSOL",
           "SOLVBTC", "LBTC", "TBTC", "FBTC", "WTRX", "STX_OLD", "BBTC", "RSETH", "METH",
           "SAVAX", "OSETH", "SFRXETH", "EETH"}
GULL = {"PAXG", "XAUT", "KAU", "XAUM", "DGX"}
GIRET = re.compile(r"(\d+[LS]|UP|DOWN|BULL|BEAR)$")

FIL = os.path.join(os.path.dirname(__file__), "univers.json")


def godkjent_base(base):
    return not (base in STABLE or base in WRAPPED or base in GULL or GIRET.search(base))


def bygg():
    tickere = kucoin.alle_tickere()
    kandidater = sorted(
        (t for s, t in tickere.items()
         if s.endswith("-USDT") and godkjent_base(s[:-5]) and t.get("volValue")),
        key=lambda t: float(t["volValue"]), reverse=True)
    grense = time.time() - MIN_DAGER * 86400
    valgt, forkastet = [], []
    for t in kandidater:
        if len(valgt) >= ANTALL:
            break
        sym = t["symbol"]
        try:
            c = kucoin.candles(sym, "1day", MIN_DAGER + 30, kun_lukkede=False)
        except RuntimeError:
            c = []
        if c and c[0][0] <= grense:
            valgt.append({"symbol": sym, "volum_usdt_24t": round(float(t["volValue"]))})
        else:
            forkastet.append(sym)
        time.sleep(0.1)
    data = {"bygget": utc_iso(), "min_dager_historikk": MIN_DAGER,
            "mynter": valgt, "forkastet_for_lite_historikk": forkastet}
    with open(FIL, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def last():
    with open(FIL, encoding="utf-8") as f:
        return [m["symbol"] for m in json.load(f)["mynter"]]


if __name__ == "__main__":
    d = bygg()
    print(f"{len(d['mynter'])} mynter valgt, {len(d['forkastet_for_lite_historikk'])} forkastet")
    print(", ".join(m["symbol"][:-5] for m in d["mynter"]))
