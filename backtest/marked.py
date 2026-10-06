"""Måler to påstander om kryptomarkedet, og tester hva de er verdt.

Påstand 1: "Stort sett faller alt samtidig, og alt stiger samtidig."
  -> måles som samvariasjon mellom myntene og hvor stor andel av bevegelsen
     én felles faktor forklarer.

Påstand 2: "I ny og ne gjør en eller flere tokens et byks, og det er de
            høydepunktene jeg vil være med på."
  -> testes som tverrsnittsmomentum: eie de myntene som har steget mest
     i det siste, i stedet for like mye av alle.

Begge testes mot kjøp-og-behold bitcoin, som er den eneste målestokken
som betyr noe.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, ".")
from system1.kjor import MYNTER

CACHE = os.environ.get("BV_CACHE", "/tmp/bv")
GEBYR = 0.0025


def last_kurser():
    """{marked: {ts: lukkekurs}} -> felles tidsakse og matrise [dager, mynter]."""
    serier = {}
    for m in MYNTER:
        f = os.path.join(CACHE, f"{m}_1d.json")
        if not os.path.exists(f):
            continue
        serier[m] = {c[0]: c[4] for c in json.load(open(f, encoding="utf-8"))}
    felles = sorted(set.intersection(*[set(s) for s in serier.values()]))
    navn = sorted(serier)
    P = np.array([[serier[m][t] for m in navn] for t in felles])
    return felles, navn, P


def samvariasjon(P, navn):
    R = np.diff(np.log(P), axis=0)
    C = np.corrcoef(R.T)
    par = C[np.triu_indices_from(C, 1)]
    egen = np.linalg.eigvalsh(C)[::-1]
    # hvor ofte beveger flertallet seg samme vei?
    opp = (R > 0).sum(axis=1) / R.shape[1]
    samlet = ((opp >= 0.8) | (opp <= 0.2)).mean()
    print("SAMVARIASJON")
    print(f"  snitt samvariasjon mellom to tilfeldige mynter: {par.mean():.2f} "
          f"(laveste par {par.min():.2f}, høyeste {par.max():.2f})")
    print(f"  én felles faktor forklarer {egen[0] / len(navn) * 100:.0f} % av bevegelsen")
    print(f"  andel dager der minst 80 % av myntene gikk samme vei: {samlet * 100:.0f} %")
    print(f"  snitt samvariasjon med bitcoin: "
          f"{np.delete(C[navn.index('BTC-EUR')], navn.index('BTC-EUR')).mean():.2f}")
    return R


def kjor_vekter(P, vekter, gebyr=GEBYR):
    """vekter[i] = porteføljevekter FØR dag i+1. Returnerer verdikurve."""
    verdi = [1.0]
    for i in range(len(vekter)):
        avk = P[i + 1] / P[i] - 1
        oms = np.abs(vekter[i] - (vekter[i - 1] if i else np.zeros_like(vekter[i]))).sum()
        verdi.append(verdi[-1] * (1 + float(vekter[i] @ avk)) * (1 - gebyr * oms))
    return np.array(verdi)


def nokkeltall(v, dager):
    aar = dager / 365.25
    topp = np.maximum.accumulate(v)
    return {"total": v[-1] - 1, "per_aar": v[-1] ** (1 / aar) - 1,
            "verste": float((v / topp - 1).min())}


def vis(navn, v, dager):
    n = nokkeltall(v, dager)
    print(f"  {navn:44s} {n['total'] * 100:+8.1f} % {n['per_aar'] * 100:+7.1f} %/år "
          f"{n['verste'] * 100:8.1f} %")
    return n


def main():
    ts, navn, P = last_kurser()
    dager = (ts[-1] - ts[0]) / 86400
    print(f"{len(navn)} mynter · {len(ts)} dager · {dager / 365.25:.1f} år\n")
    samvariasjon(P, navn)

    n_m = len(navn)
    ibtc = navn.index("BTC-EUR")
    N = len(P) - 1

    print("\nTEST (alle med 0,25 % gebyr per handel)")
    btc_v = np.zeros((N, n_m)); btc_v[:, ibtc] = 1.0
    vis("Bare eie bitcoin", kjor_vekter(P, btc_v), dager)
    lik = np.full((N, n_m), 1 / n_m)
    vis("Like mye av alle 13", kjor_vekter(P, lik), dager)

    # --- regimefilter: inn når markedet er over sitt eget glidende snitt ---
    # Indeksen må være likevektet. Et snitt av RÅPRISER ville vært ren bitcoin,
    # siden den koster titusener og CAKE koster to euro. Derfor normaliseres
    # hver mynt til 1 på første dag først.
    indeks = (P / P[0]).mean(axis=1)
    print("\n  Regimefilter (alt inn / alt ut etter markedets trend):")
    for vindu in (50, 100, 150, 200):
        snitt = np.array([indeks[max(0, i - vindu):i + 1].mean() for i in range(len(indeks))])
        paa = (indeks > snitt).astype(float)[:N]
        vis(f"likevekt, inne når indeks > {vindu}d snitt", kjor_vekter(P, lik * paa[:, None]), dager)

    # --- tverrsnittsmomentum: eie det som har steget mest ---
    print("\n  Tverrsnittsmomentum (eie de K sterkeste siste 30 dager):")
    tilbake, rebal = 30, 7
    for K in (1, 2, 3, 5):
        V = np.zeros((N, n_m))
        siste = np.zeros(n_m)
        for i in range(N):
            if i >= tilbake and i % rebal == 0:
                mom = P[i] / P[i - tilbake] - 1
                topp = np.argsort(mom)[-K:]
                siste = np.zeros(n_m)
                siste[topp] = 1 / K
            V[i] = siste
        vis(f"topp {K} mynt(er), ny vurdering hver {rebal}. dag", kjor_vekter(P, V), dager)

    # --- begge deler: regimefilter + momentum ---
    print("\n  Begge deler (momentum, men bare når markedet er i oppgang):")
    for vindu in (100, 150):
        snitt = np.array([indeks[max(0, i - vindu):i + 1].mean() for i in range(len(indeks))])
        paa = (indeks > snitt).astype(float)[:N]
        for K in (2, 3, 5):
            V = np.zeros((N, n_m))
            siste = np.zeros(n_m)
            for i in range(N):
                if i >= tilbake and i % rebal == 0:
                    mom = P[i] / P[i - tilbake] - 1
                    topp = np.argsort(mom)[-K:]
                    siste = np.zeros(n_m)
                    siste[topp] = 1 / K
                V[i] = siste * paa[i]
            vis(f"topp {K}, inne når indeks > {vindu}d snitt", kjor_vekter(P, V), dager)
    return 0


if __name__ == "__main__":
    sys.exit(main())
