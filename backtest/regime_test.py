"""Fase 1: måler regimeindikatorene på UTVIKLINGSPERIODEN 2022-2024.

Fasitperioden fra 2025-01-01 røres ikke her. Den kjøres én gang, til slutt,
når parametervalgene er låst og skrevet til state/valg_<dato>.json.
Skriptet nekter derfor å lese data etter sluttdatoen.

Spørsmålet i denne fasen er ikke «hvor mye tjener vi», men:
  - sier de fire målene det samme, eller noe hver?
  - hvor ofte skifter regimet, og hva koster skiftene?
  - er effekten der også når man flytter parameterne ett hakk?
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, ".")
from felles import regime
from system1.kjor import MYNTER

CACHE = os.environ.get("BV_CACHE", "/tmp/bv")
UTVIKLING_SLUTT = "2024-12-31"
GEBYR = 0.0025


def last(slutt=UTVIKLING_SLUTT):
    import datetime
    grense = int(datetime.datetime.fromisoformat(slutt + "T23:59:59+00:00").timestamp())
    serier = {}
    for m in MYNTER:
        f = os.path.join(CACHE, f"{m}_1d.json")
        if os.path.exists(f):
            serier[m] = {c[0]: c[4] for c in json.load(open(f, encoding="utf-8"))}
    felles = sorted(t for t in set.intersection(*[set(s) for s in serier.values()])
                    if t <= grense)
    navn = sorted(serier)
    return felles, navn, np.array([[serier[m][t] for m in navn] for t in felles])


def kjor(P, vekter, gebyr=GEBYR):
    v = [1.0]
    for i in range(len(vekter)):
        avk = P[i + 1] / P[i] - 1
        oms = np.abs(vekter[i] - (vekter[i - 1] if i else np.zeros_like(vekter[i]))).sum()
        v.append(v[-1] * (1 + float(vekter[i] @ avk)) * (1 - gebyr * oms))
    return np.array(v)


def tall(v, dager):
    topp = np.maximum.accumulate(v)
    return (v[-1] - 1, v[-1] ** (365.25 / dager) - 1, float((v / topp - 1).min()))


def vis(navn, v, dager, n_skifter=None):
    t, pa, ned = tall(v, dager)
    s = f"{n_skifter:4d}" if n_skifter is not None else "   -"
    print(f"  {navn:46s} {t * 100:+8.1f} % {pa * 100:+7.1f} %/år {ned * 100:8.1f} %  {s}")
    return pa / abs(ned) if ned else 0


def main():
    ts, navn, P = last()
    dager = (ts[-1] - ts[0]) / 86400
    ibtc = navn.index("BTC-EUR")
    N = len(P) - 1
    n_m = len(navn)
    import datetime
    print(f"UTVIKLINGSPERIODE {datetime.datetime.fromtimestamp(ts[0], datetime.UTC):%Y-%m-%d}"
          f" til {datetime.datetime.fromtimestamp(ts[-1], datetime.UTC):%Y-%m-%d}"
          f"  ({dager / 365.25:.1f} år, {len(navn)} mynter)")
    print("Fasitperioden 2025-2026 er IKKE lest av dette skriptet.\n")

    eksp, poeng, m = regime.eksponering(P, ibtc=ibtc)

    print("DE FIRE MÅLENE (andel dager de peker opp, og hvor enige de er)")
    for k, v in m.items():
        print(f"  {k:10s} peker opp {v.mean() * 100:5.1f} % av dagene")
    M = np.array([m[k] for k in m])
    C = np.corrcoef(M)
    par = C[np.triu_indices_from(C, 1)]
    print(f"  innbyrdes samvariasjon: snitt {par.mean():.2f}, "
          f"laveste {par.min():.2f}, høyeste {par.max():.2f}")
    print("  (lav samvariasjon er bra - da måler de faktisk hver sin ting)")
    for p in range(5):
        print(f"  {(poeng == p).mean() * 100:5.1f} % av dagene har {p} av 4 mål oppe")

    lik = np.full((N, n_m), 1 / n_m)
    btc = np.zeros((N, n_m)); btc[:, ibtc] = 1.0
    print(f"\n{'':48s} {'total':>9s} {'per år':>10s} {'verste':>10s}  skift")
    vis("Bare eie bitcoin", kjor(P, btc), dager)
    vis("Like mye av alle 13, alltid inne", kjor(P, lik), dager)

    print("\n  Hvert mål brukt alene (alt inn / alt ut):")
    for k, v in m.items():
        w = lik * v[:N, None]
        vis(f"bare {k}", kjor(P, w), dager, regime.skifter(v[:N]))

    print("\n  Alle fire, eksponeringstrapp 0/0/35/70/100 %:")
    vis(f"trapp, minst {regime.MIN_DAGER} dager per regime",
        kjor(P, lik * eksp[:N, None]), dager, regime.skifter(eksp[:N]))
    for md in (1, 3, 10, 20):
        e2, _, _ = regime.eksponering(P, min_dager=md, ibtc=ibtc)
        vis(f"trapp, minst {md} dager per regime", kjor(P, lik * e2[:N, None]),
            dager, regime.skifter(e2[:N]))

    print("\n  Naboverdier på trendvinduet (skal IKKE kollapse):")
    for tv in (60, 80, 100, 120, 150):
        e2, _, _ = regime.eksponering(P, trend_vindu=tv, ibtc=ibtc)
        vis(f"trendvindu {tv} dager", kjor(P, lik * e2[:N, None]), dager,
            regime.skifter(e2[:N]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
