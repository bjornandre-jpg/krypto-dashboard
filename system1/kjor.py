"""System 1: 13 mynter, daglige candles, seks signalkilder, hysterese per kjøring.
Kjøres hver time av GitHub Actions. Simulert papirhandel - INGEN ekte penger."""
import json
import os
import sys
from datetime import datetime, timezone

from felles import kucoin, fear_greed, nyheter, onchain, dashboard
from felles.signal import ta_serie, fear_greed_score, funding_score, vektet, beslutning
from felles.portefolje import Portefolje, vurder_mynt, lagre, utc_iso

MAPPE = os.path.join("state", "system1")
MYNTER = ["BTC-USDT", "ETH-USDT", "XRP-USDT", "SOL-USDT", "BNB-USDT", "DOGE-USDT", "ADA-USDT",
          "LINK-USDT", "AVAX-USDT", "DOT-USDT", "LTC-USDT", "UNI-USDT", "CAKE-USDT"]
# Giret opp 2026-09-19: kortere trendvindu (SMA 8/33) og tyngre TA-vekt, se backtest i README.
VEKT_BTC = {"nyheter": 0.05, "onchain": 0.05, "ta": 0.75, "fg": 0.05, "funding": 0.10}
VEKT_ANDRE = {"nyheter": 0.05, "ta": 0.80, "fg": 0.05, "funding": 0.10}
SMA_RASK, SMA_TREG = 8, 33
CFG = {"max_per_mynt": 0.10, "max_total": 0.60,
       "kill_switch": os.path.exists(os.path.join(MAPPE, "STOPP"))}


def main():
    pf = Portefolje(CFG, 1000.0, MAPPE)
    tickere = kucoin.alle_tickere()
    priser = kucoin.priser(tickere)
    kontrakter = kucoin.aktive_kontrakter()
    try:
        fg = fear_greed.naa()
    except RuntimeError:
        fg = None
    nyh, n_titler = nyheter.score()
    oc = onchain.score()

    eq = pf.egenkapital(priser)
    pf.start_dag(datetime.now(timezone.utc).strftime("%Y-%m-%d"), eq)
    bfil = os.path.join(MAPPE, "beslutninger.json")
    forrige = json.load(open(bfil, encoding="utf-8")) if os.path.exists(bfil) else {}

    signaler, logg, nye = [], [], {}
    for s in MYNTER:
        if s not in priser:
            print(f"ADVARSEL: mangler pris for {s}")
            continue
        try:
            closes = [c[4] for c in kucoin.candles(s, "1day", 120, kun_lukkede=False)]
            ta = ta_serie(closes, SMA_RASK, SMA_TREG)[-1]
        except RuntimeError as e:
            print(f"ADVARSEL: {s} candles: {e}")
            ta = None
        fr = kucoin.funding_naa(s, kontrakter)
        deler = {"nyheter": nyh, "onchain": oc, "ta": ta,
                 "fg": fear_greed_score(fg), "funding": funding_score(fr)}
        sc = vektet(deler, VEKT_BTC if s == "BTC-USDT" else VEKT_ANDRE)
        b = beslutning(sc, pf.cfg["terskel"])
        bekreftet = forrige.get(s) == b
        nye[s] = b
        handling = vurder_mynt(pf, s, priser, eq, b, sc, bekreftet, True)
        signaler.append({"asset": s.replace("-", "/"), "decision": b, "score": sc,
                         "confirmed": bekreftet, "funding_rate": fr, "price": priser[s],
                         "ta": ta})
        logg.append({"tid": utc_iso(), "mynt": s, "score": round(sc, 4), "beslutning": b,
                     "bekreftet": bekreftet, "ta": None if ta is None else round(ta, 4),
                     "nyheter": None if nyh is None else round(nyh, 4),
                     "onchain": None if oc is None else round(oc, 4), "fg": fg,
                     "funding": fr, "pris": priser[s], "handling": handling})

    json.dump(nye, open(bfil, "w", encoding="utf-8"))
    eq = pf.egenkapital(priser)
    lagre(pf, eq, {"signaler.csv": logg})
    dashboard.skriv(pf, priser, signaler, fg,
                    {"system": "Krypto13 - 13 mynter", "news_headlines": n_titler})
    print(f"Krypto13: egenkapital {eq:.2f} USDT, {len(pf.handler)} handler, "
          f"{len(pf.s['posisjoner'])} posisjoner, F&G {fg}, nyheter {nyh}, onchain {oc}")
    for h in pf.handler:
        print("  ", h)


if __name__ == "__main__":
    sys.exit(main())
