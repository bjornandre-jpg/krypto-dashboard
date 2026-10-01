"""Krypto13: 13 mynter, daglige candles, seks signalkilder, hysterese per kjøring.

Kurser og handel: Bitvavo (EUR). Funding hentes fortsatt fra KuCoin futures,
fordi Bitvavo ikke har perpetuals og funding er et markedsbredt signal.
Kjøres hver time av GitHub Actions. Simulert papirhandel - INGEN ekte penger."""
import json
import os
import sys
from datetime import datetime, timezone

from felles import bitvavo, kucoin, fear_greed, nyheter, onchain, dashboard
from felles.signal import ta_serie, fear_greed_score, funding_score, vektet, beslutning
from felles.portefolje import STANDARD, Portefolje, vurder_mynt, lagre, utc_iso

STANDARD_TERSKEL = STANDARD["terskel"]

MAPPE = os.path.join("state", "system1")
MYNTER = ["BTC-EUR", "ETH-EUR", "XRP-EUR", "SOL-EUR", "BNB-EUR", "DOGE-EUR", "ADA-EUR",
          "LINK-EUR", "AVAX-EUR", "DOT-EUR", "LTC-EUR", "UNI-EUR", "CAKE-EUR"]
# Giret opp 2026-09-19 (kortere trendvindu, tyngre TA-vekt), justert 2026-09-25 til SMA 10/40. Se README.
VEKT_BTC = {"nyheter": 0.05, "onchain": 0.05, "ta": 0.75, "fg": 0.05, "funding": 0.10}
VEKT_ANDRE = {"nyheter": 0.05, "ta": 0.80, "fg": 0.05, "funding": 0.10}
SMA_RASK, SMA_TREG = 10, 40
CFG = {"max_per_mynt": 0.10, "max_total": 0.60,
       "kill_switch": os.path.exists(os.path.join(MAPPE, "STOPP"))}


def markedsbilde():
    """Henter alt som er felles for alle mynter: priser og de brede signalene.

    Skilt ut fra main() slik at ekte-penger-systemet bruker nøyaktig samme
    kode som papirsystemet. To kopier av signallogikken ville før eller siden
    sklidd fra hverandre, og da måler vi ikke lenger det vi tror vi måler.
    """
    priser = bitvavo.priser()
    kontrakter = kucoin.aktive_kontrakter()   # kun for funding-signalet
    try:
        fg = fear_greed.naa()
    except RuntimeError:
        fg = None
    nyh, n_titler = nyheter.score()
    return {"priser": priser, "kontrakter": kontrakter, "fg": fg,
            "nyheter": nyh, "titler": n_titler, "onchain": onchain.score()}


def mynt_signal(s, mb):
    """Score, beslutning og tidsstempel på siste lukkede dagscandle for én mynt."""
    try:
        c = bitvavo.candles(s, "1d", 120)        # KUN lukkede dagscandles
        ta = ta_serie([x[4] for x in c], SMA_RASK, SMA_TREG)[-1] if c else None
    except RuntimeError as e:
        print(f"ADVARSEL: {s} candles: {e}")
        c, ta = [], None
    fr = kucoin.funding_naa(s.split("-")[0] + "-USDT", mb["kontrakter"])
    deler = {"nyheter": mb["nyheter"], "onchain": mb["onchain"], "ta": ta,
             "fg": fear_greed_score(mb["fg"]), "funding": funding_score(fr)}
    sc = vektet(deler, VEKT_BTC if s == "BTC-EUR" else VEKT_ANDRE)
    return {"score": sc, "beslutning": beslutning(sc, STANDARD_TERSKEL),
            "ta": ta, "funding": fr, "ts": c[-1][0] if c else None}


def ny_dag_og_bekreftelse(lagret, sig):
    """Én beslutning per LUKKET dagscandle, bekreftelse krever to påfølgende.

    Mellom dagene gjør systemet ingenting: målt over fire år ga timesvis
    vurdering -25 prosentpoeng og dobbelt så høye gebyrer, og timesvis
    stop-loss kastet ut posisjoner på intradag-støy som var hentet inn igjen
    ved dagsslutt (se backtest/live_vs_test.py).
    """
    if not isinstance(lagret, dict):              # gammelt format {mynt: "KJØP"}
        lagret = {}
    ny_dag = sig["ts"] is not None and lagret.get("ts") != sig["ts"]
    return ny_dag, ny_dag and lagret.get("beslutning") == sig["beslutning"]


def main():
    pf = Portefolje(CFG, 1000.0, MAPPE)
    mb = markedsbilde()
    priser, fg, nyh, oc, n_titler = (mb["priser"], mb["fg"], mb["nyheter"],
                                     mb["onchain"], mb["titler"])

    eq = pf.egenkapital(priser)
    pf.start_dag(datetime.now(timezone.utc).strftime("%Y-%m-%d"), eq)
    bfil = os.path.join(MAPPE, "beslutninger.json")
    forrige = json.load(open(bfil, encoding="utf-8")) if os.path.exists(bfil) else {}

    signaler, logg, nye = [], [], {}
    n_dager = 0
    for s in MYNTER:
        if s not in priser:
            print(f"ADVARSEL: mangler pris for {s}")
            continue
        sig = mynt_signal(s, mb)
        sc, b, ta, fr, ts = (sig["score"], sig["beslutning"], sig["ta"],
                             sig["funding"], sig["ts"])
        ny_dag, bekreftet = ny_dag_og_bekreftelse(forrige.get(s), sig)
        handling = ""
        if ny_dag:
            n_dager += 1
            handling = vurder_mynt(pf, s, priser, eq, b, sc, bekreftet, True)
            nye[s] = {"ts": ts, "beslutning": b}
        else:
            nye[s] = forrige.get(s) or {"ts": ts, "beslutning": b}

        signaler.append({"asset": s.replace("-", "/"), "decision": b, "score": sc,
                         "confirmed": bekreftet, "funding_rate": fr, "price": priser[s],
                         "ta": ta})
        if ny_dag or handling:
            logg.append({"tid": utc_iso(), "mynt": s, "score": round(sc, 4), "beslutning": b,
                         "bekreftet": bekreftet, "ta": None if ta is None else round(ta, 4),
                         "nyheter": None if nyh is None else round(nyh, 4),
                         "onchain": None if oc is None else round(oc, 4), "fg": fg,
                         "funding": fr, "pris": priser[s], "handling": handling})

    json.dump(nye, open(bfil, "w", encoding="utf-8"))
    eq = pf.egenkapital(priser)
    lagre(pf, eq, {"signaler.csv": logg} if logg else None)
    dashboard.skriv(pf, priser, signaler, fg,
                    {"system": "Krypto13 - 13 mynter", "valuta": "EUR", "news_headlines": n_titler})
    print(f"Krypto13: egenkapital {eq:.2f} EUR, {len(pf.handler)} handler, "
          f"{len(pf.s['posisjoner'])} posisjoner, {n_dager} nye dagsbeslutninger, "
          f"F&G {fg}, nyheter {nyh}, onchain {oc}")
    for h in pf.handler:
        print("  ", h)


if __name__ == "__main__":
    sys.exit(main())
