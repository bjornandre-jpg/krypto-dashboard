"""Porteføljebacktest av Krypto50 med den rekonstruerte signalkoden.

Samme logikk som live: felles.signal + felles.portefolje.vurder_mynt.
Ingen lookahead: beslutning fra candle i utføres til åpningskursen på i+1.
Kjør etter backtest.hent_data:  python -m backtest.krypto50_backtest
"""
import bisect, json, os, sys
from felles.signal import ta_serie, fear_greed_score, funding_score, beslutning
from felles.portefolje import Portefolje, vurder_mynt

CACHE = os.environ.get("BT_CACHE", "/tmp/bt_cache")
VEKTER = {"ta": 0.80, "fg": 0.10, "funding": 0.10}


def last_data(mynter, ctype="4hour"):
    d = {}
    for s in mynter:
        c = json.load(open(os.path.join(CACHE, f"{s}_{ctype}.json")))
        fh = json.load(open(os.path.join(CACHE, f"{s}_funding.json")))
        d[s] = {"c": c, "fund_ts": [x[0] // 1000 for x in fh], "fund": [x[1] for x in fh]}
    fng = json.load(open(os.path.join(CACHE, "fng.json")))
    return d, [x[0] for x in fng], [x[1] for x in fng]


def slaa_opp(ts_liste, verdier, t):
    i = bisect.bisect_right(ts_liste, t) - 1
    return verdier[i] if i >= 0 else None


def kjor(mynter, terskel=0.30, bekreftelser=2, per=14400, rask=50, treg=200, ctype="4hour",
         forsinkelse=0, gebyr=0.001, stokk=False, cfg_ekstra=None):
    data, fts, fvs = last_data(mynter, ctype)
    import random
    rng = random.Random(1)
    # forhåndsberegn score per mynt per candle-ts (ved candle-slutt)
    score = {}
    for s, d in data.items():
        closes = [c[4] for c in d["c"]]
        ta = ta_serie(closes, rask, treg)
        sc = {}
        for c, t in zip(d["c"], ta):
            if t is None:
                continue
            slutt = c[0] + per
            fg = slaa_opp(fts, fvs, slutt)
            fu = slaa_opp(d["fund_ts"], d["fund"], slutt)
            sc[c[0]] = VEKTER["ta"] * t + VEKTER["fg"] * fear_greed_score(fg) + VEKTER["funding"] * funding_score(fu)
        if stokk:
            v = list(sc.values()); rng.shuffle(v); sc = dict(zip(sc.keys(), v))
        score[s] = sc
        d["open"] = {c[0]: c[1] for c in d["c"]}
    alle_ts = sorted({c[0] for d in data.values() for c in d["c"]})
    cfg = {"max_per_mynt": 0.04, "max_total": 0.80, "gebyr": gebyr, "terskel": terskel, **(cfg_ekstra or {})}
    pf = Portefolje(cfg, 1000.0)
    historikk = {s: [] for s in mynter}
    siste_pris = {}
    kurve, antall_handler, topp, maks_ned = [], 0, 1000.0, 0.0
    for j, t in enumerate(alle_ts):
        # priser ved åpning av candle t
        for s, d in data.items():
            if t in d["open"]:
                siste_pris[s] = d["open"][t]
        eq = pf.egenkapital(siste_pris)
        pf.start_dag(t // 86400, eq)
        beslutn_ts = t - per * (1 + forsinkelse)
        for s in mynter:
            if s not in siste_pris:
                continue
            sc = score[s].get(beslutn_ts)
            ny = sc is not None
            if ny:
                historikk[s].append(beslutning(sc, terskel))
            h = historikk[s]
            bekreftet = ny and len(h) >= bekreftelser and len(set(h[-bekreftelser:])) == 1
            vurder_mynt(pf, s, siste_pris, eq, h[-1] if h else "AVVENT", sc or 0.0, bekreftet, ny, t)
        antall_handler += len(pf.handler); pf.handler = []
        eq = pf.egenkapital(siste_pris)
        topp = max(topp, eq); maks_ned = min(maks_ned, eq / topp - 1)
        kurve.append((t, eq))
    ar = (alle_ts[-1] - alle_ts[0]) / (365.25 * 86400)
    avk = kurve[-1][1] / 1000 - 1
    return {"avkastning": avk, "annualisert": (1 + avk) ** (1 / ar) - 1, "maks_nedgang": maks_ned,
            "handler": antall_handler, "aar": ar}


if __name__ == "__main__":
    from krypto50.univers import last
    m = last()
    for navn, kw in [("4t ±0,30 x2 (valgt)", {}),
                     ("4t ±0,20 x1", {"terskel": 0.20, "bekreftelser": 1}),
                     ("4t stokket signal", {"stokk": True})]:
        r = kjor(m, **kw)
        print(f"{navn:24s} avk {r['avkastning']:+.1%}  ann {r['annualisert']:+.1%}  "
              f"maks ned {r['maks_nedgang']:.1%}  handler {r['handler']}  ({r['aar']:.1f} år)", flush=True)
