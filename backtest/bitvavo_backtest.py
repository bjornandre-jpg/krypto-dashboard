"""Porteføljebacktest på Bitvavo sine egne EUR-kurser.

Samme signal- og handelskode som live (felles.signal + felles.portefolje),
men alt regnes i euro, slik det faktisk vil bli på Bitvavo.
Ingen lookahead: beslutning fra candle i utføres til åpningskursen på i+1.
"""
import bisect
import json
import os
import random
from collections import defaultdict

from felles.portefolje import Portefolje, vurder_mynt
from felles.signal import beslutning, fear_greed_score, funding_score, ta_serie

CACHE = os.environ.get("BV_CACHE", "/tmp/bv")


def _les(sti):
    with open(sti, encoding="utf-8") as f:
        return json.load(f)


def last_data(markeder, interval):
    d = {}
    for m in markeder:
        c = _les(os.path.join(CACHE, f"{m}_{interval}.json"))
        if not c:
            continue
        fh = []
        f_sti = os.path.join(CACHE, f"{m.split('-')[0]}_funding.json")
        if os.path.exists(f_sti):
            fh = _les(f_sti)
        d[m] = {"c": c, "fund_ts": [x[0] // 1000 for x in fh], "fund": [x[1] for x in fh],
                "open": {x[0]: x[1] for x in c}, "low": {x[0]: x[3] for x in c}}
    fng = _les(os.path.join(CACHE, "fng.json"))
    return d, [x[0] for x in fng], [x[1] for x in fng]


def _oppslag(ts_liste, verdier, t):
    i = bisect.bisect_right(ts_liste, t) - 1
    return verdier[i] if i >= 0 else None


def kjor(markeder, interval, per, rask, treg, vekter, cfg, terskel=0.30, bekreftelser=2,
         gebyr=0.0025, start=1000.0, stokk=False, seed=1, sl_intra=False):
    """sl_intra=True sjekker stop-loss mot candlens LAVESTE kurs i stedet for
    sluttkursen. Det tilsvarer å sjekke stop-loss løpende inne i candlen, slik
    live gjør hver time, og er den ytterste varianten av hyppig sjekk."""
    data, fts, fvs = last_data(markeder, interval)
    rng = random.Random(seed)
    score = {}
    for m, d in data.items():
        closes = [c[4] for c in d["c"]]
        ta = ta_serie(closes, rask, treg)
        sc = {}
        for c, t in zip(d["c"], ta):
            if t is None:
                continue
            slutt = c[0] + per
            sc[c[0]] = (vekter["ta"] * t
                        + vekter["fg"] * fear_greed_score(_oppslag(fts, fvs, slutt))
                        + vekter["funding"] * funding_score(_oppslag(d["fund_ts"], d["fund"], slutt)))
        if stokk:
            v = list(sc.values())
            rng.shuffle(v)
            sc = dict(zip(sc.keys(), v))
        score[m] = sc

    alle_ts = sorted({c[0] for d in data.values() for c in d["c"]})
    pf = Portefolje({"gebyr": gebyr, "terskel": terskel, **cfg}, start)
    hist = {m: [] for m in data}
    siste, kurve = {}, []
    topp, ned, n_handler, oms = start, 0.0, 0, defaultdict(float)
    import datetime

    for t in alle_ts:
        for m, d in data.items():
            if t in d["open"]:
                siste[m] = d["open"][t]
        eq = pf.egenkapital(siste)
        pf.start_dag(t // 86400, eq)
        if sl_intra and cfg.get("stop_loss"):
            for mm in list(pf.s["posisjoner"]):
                lav = data.get(mm, {}).get("low", {}).get(t)
                p = pf.pos(mm)
                if lav is None or not p:
                    continue
                grense = p["snittpris"] * (1 - cfg["stop_loss"])
                if lav <= grense:
                    pf.selg(mm, p["mengde"], grense, f"stop-loss {-cfg['stop_loss']:+.1%} (intra)", t)
        bts = t - per
        for m in data:
            if m not in siste:
                continue
            sc = score[m].get(bts)
            ny = sc is not None
            if ny:
                hist[m].append(beslutning(sc, terskel))
            h = hist[m]
            bekreftet = ny and len(h) >= bekreftelser and len(set(h[-bekreftelser:])) == 1
            vurder_mynt(pf, m, siste, eq, h[-1] if h else "AVVENT", sc or 0.0, bekreftet, ny, t)
        mnd = datetime.datetime.fromtimestamp(t, datetime.UTC).strftime("%Y-%m")
        for x in pf.handler:
            oms[mnd] += x["belop"]
        n_handler += len(pf.handler)
        pf.handler = []
        eq = pf.egenkapital(siste)
        topp = max(topp, eq)
        ned = min(ned, eq / topp - 1)
        kurve.append((t, eq))

    aar = (alle_ts[-1] - alle_ts[0]) / (365.25 * 86400)
    avk = kurve[-1][1] / start - 1
    m_oms = sorted(v for k, v in sorted(oms.items())[1:-1])
    return {"avkastning": avk, "annualisert": (1 + avk) ** (1 / aar) - 1, "maks_nedgang": ned,
            "handler": n_handler, "aar": aar, "sluttverdi": kurve[-1][1],
            "oms_median": m_oms[len(m_oms) // 2] if m_oms else 0, "kurve": kurve}
