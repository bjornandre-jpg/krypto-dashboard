"""Bygger myntuniverset fra Bitvavo: de mest omsatte EUR-parene, med minst
365 dagers historikk, uten girede tokens, stablecoins, wrapped/staking-
duplikater og gull-tokens, og uten par med for vid kjøps-/salgsforskjell.

Spread-filteret kom til 2026-09-27: en måling viste at enkelte små Bitvavo-par
har over 1 % spread, og den kostnaden betales ved hver eneste handel, i tillegg
til gebyret.

Kjør: python -m krypto50.univers        (50 mynter -> krypto50/univers.json)
      python -m krypto50.univers 100    (100 mynter -> krypto100/univers.json)
"""
import json
import os
import re
import time

from felles import bitvavo
from felles.portefolje import utc_iso

ANTALL = 50
MIN_DAGER = 365
MAKS_SPREAD = 0.30          # prosent; par med videre spread koster for mye per handel
STABLE = {"USDT", "USDC", "DAI", "TUSD", "FDUSD", "USDD", "PYUSD", "USDE", "USD1", "BUSD",
          "USDP", "USDJ", "UST", "USTC", "FRAX", "GUSD", "USDS", "RLUSD", "USD0", "EURC",
          "EURT", "EUR", "AEUR", "USDQ", "USDR", "LUSD", "CRVUSD", "SUSD", "USDX", "USDG",
          "XUSD", "USDB", "BFUSD", "USDF", "SUSDE", "DEUSD", "USDA", "USDY", "USDTB"}
WRAPPED = {"WBTC", "WETH", "STETH", "WSTETH", "CBETH", "RETH", "WBETH", "BETH", "JITOSOL",
           "MSOL", "BNSOL", "WEETH", "EZETH", "CBBTC", "BTCB", "WBNB", "WSOL", "STSOL",
           "SOLVBTC", "LBTC", "TBTC", "FBTC", "WTRX", "BBTC", "RSETH", "METH",
           "SAVAX", "OSETH", "SFRXETH", "EETH", "WAVAX", "WMATIC"}
GULL = {"PAXG", "XAUT", "KAU", "XAUM", "DGX"}
GIRET = re.compile(r"(\d+[LS]|UP|DOWN|BULL|BEAR)$")

FIL = os.path.join(os.path.dirname(__file__), "univers.json")


def godkjent_base(base):
    return not (base in STABLE or base in WRAPPED or base in GULL or GIRET.search(base))


def bygg(antall=ANTALL, fil=FIL):
    mk = bitvavo.markeder()
    t = bitvavo.tickere()
    oms = bitvavo.omsetning_24t(t)
    sp = bitvavo.spreads()
    kandidater = sorted(
        (m for m in mk if godkjent_base(m.split("-")[0]) and oms.get(m)),
        key=lambda m: oms[m], reverse=True)
    grense = time.time() - MIN_DAGER * 86400
    valgt, forkastet_hist, forkastet_spread = [], [], []
    for m in kandidater:
        if len(valgt) >= antall:
            break
        s = sp.get(m)
        if s is None or s > MAKS_SPREAD:
            forkastet_spread.append(f"{m.split('-')[0]} ({s:.2f} %)" if s is not None else m.split("-")[0])
            continue
        try:
            c = bitvavo.candles(m, "1d", MIN_DAGER + 30, kun_lukkede=False)
        except RuntimeError:
            c = []
        if c and c[0][0] <= grense:
            valgt.append({"symbol": m, "omsetning_eur_24t": round(oms[m]), "spread_pst": round(s, 3)})
        else:
            forkastet_hist.append(m.split("-")[0])
        time.sleep(0.08)
    data = {"bygget": utc_iso(), "bors": "Bitvavo", "valuta": "EUR",
            "min_dager_historikk": MIN_DAGER, "maks_spread_pst": MAKS_SPREAD,
            "mynter": valgt, "forkastet_for_lite_historikk": forkastet_hist,
            "forkastet_for_vid_spread": forkastet_spread}
    with open(fil, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def last(fil=FIL):
    with open(fil, encoding="utf-8") as f:
        return [m["symbol"] for m in json.load(f)["mynter"]]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "100":
        from krypto100 import UNIVERS_FIL
        d = bygg(100, UNIVERS_FIL)
    else:
        d = bygg()
    print(f"{len(d['mynter'])} mynter valgt · {len(d['forkastet_for_lite_historikk'])} for kort historikk "
          f"· {len(d['forkastet_for_vid_spread'])} for vid spread")
    print(", ".join(m["symbol"].split("-")[0] for m in d["mynter"]))
