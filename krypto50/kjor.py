"""Krypto50: 50 mynter, 4-timers candles, TA 80 / Fear&Greed 10 / funding 10.
Hysterese telles per LUKKEDE candle (to bekreftelser = 8 timer), ikke per kjøring.
Stop-loss/take-profit/rebalansering sjekkes hver time. INGEN ekte penger."""
import json
import os
import sys
from datetime import datetime, timezone

from felles import kucoin, fear_greed, dashboard
from felles.signal import ta_serie, fear_greed_score, funding_score, vektet, beslutning
from felles.portefolje import Portefolje, vurder_mynt, lagre, utc_iso
from krypto50.univers import last

MAPPE = os.path.join("state", "krypto50")
VEKTER = {"ta": 0.80, "fg": 0.10, "funding": 0.10}
BEKREFTELSER = 2
CFG = {"max_per_mynt": 0.04, "max_total": 0.80,
       "kill_switch": os.path.exists(os.path.join(MAPPE, "STOPP"))}


def main():
    mynter = last()
    pf = Portefolje(CFG, 1000.0, MAPPE)
    priser = kucoin.priser()
    kontrakter = kucoin.aktive_kontrakter()
    try:
        fg = fear_greed.naa()
    except RuntimeError:
        fg = None
    eq = pf.egenkapital(priser)
    pf.start_dag(datetime.now(timezone.utc).strftime("%Y-%m-%d"), eq)
    cfil = os.path.join(MAPPE, "candle_beslutninger.json")
    hist = json.load(open(cfil, encoding="utf-8")) if os.path.exists(cfil) else {}

    signaler, logg = [], []
    for s in mynter:
        if s not in priser:
            print(f"ADVARSEL: mangler pris for {s}")
            continue
        try:
            c = kucoin.candles(s, "4hour", 320)       # kun lukkede candles
        except RuntimeError as e:
            print(f"ADVARSEL: {s} candles: {e}")
            c = []
        h = hist.setdefault(s, [])
        ny_candle, sc, b, fr = False, None, h[-1][1] if h else "AVVENT", None
        if c:
            ta = ta_serie([x[4] for x in c])[-1]
            fr = kucoin.funding_naa(s, kontrakter)
            if ta is not None:
                sc = vektet({"ta": ta, "fg": fear_greed_score(fg), "funding": funding_score(fr)}, VEKTER)
                siste_ts = c[-1][0]
                if not h or siste_ts > h[-1][0]:
                    b = beslutning(sc, pf.cfg["terskel"])
                    # regnes som påfølgende bare hvis forrige candle er nøyaktig 4t før
                    if h and siste_ts - h[-1][0] != 14400:
                        h.clear()
                    h.append([siste_ts, b, round(sc, 4)])
                    del h[:-5]
                    ny_candle = True
                else:
                    sc = h[-1][2]
        bekreftet = (ny_candle and len(h) >= BEKREFTELSER
                     and len({x[1] for x in h[-BEKREFTELSER:]}) == 1)
        handling = vurder_mynt(pf, s, priser, eq, b, sc or 0.0, bekreftet, ny_candle)
        signaler.append({"asset": s.replace("-", "/"), "decision": b, "score": sc,
                         "confirmed": len(h) >= BEKREFTELSER and len({x[1] for x in h[-BEKREFTELSER:]}) == 1,
                         "funding_rate": fr, "price": priser[s]})
        if ny_candle or handling:
            logg.append({"tid": utc_iso(), "mynt": s, "candle": utc_iso(h[-1][0]) if h else "",
                         "score": sc, "beslutning": b, "bekreftet": bekreftet, "fg": fg,
                         "funding": fr, "pris": priser[s], "handling": handling})

    json.dump(hist, open(cfil, "w", encoding="utf-8"))
    eq = pf.egenkapital(priser)
    lagre(pf, eq, {"signaler.csv": logg} if logg else None)
    dashboard.skriv(pf, priser, signaler, fg, {"system": "Krypto50 - 50 mynter, 4t"})
    print(f"Krypto50: egenkapital {eq:.2f} USDT, {len(pf.handler)} handler, "
          f"{len(pf.s['posisjoner'])} posisjoner, {len(logg)} nye candle-beslutninger")


if __name__ == "__main__":
    sys.exit(main())
