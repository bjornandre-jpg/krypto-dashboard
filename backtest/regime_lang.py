"""Virker et regimefilter i det hele tatt? Testet over tolv år og tre krakk.

Fase 1 ga et negativt svar, men på et grunnlag som ikke kunne gi noe annet:
utviklingsperioden 2022-2024 var nesten rent oksemarked, der bitcoin steg
99,6 % i året. Et defensivt filter kan ikke hjelpe i et slikt marked - det
kan bare koste. Å teste en brannslukker i et hus som ikke brenner sier
ingenting om brannslukkeren.

Her brukes bitcoin fra 2014 og ethereum fra 2017, som dekker fallene i
2014-15, 2018 og 2022 i tillegg til oppgangene.

ÆRLIGHET OM PERIODENE
  Utvikling  2014-09 til 2019-12 - her velges parameterne
  Fasit      2020-01 til 2021-12 - ikke sett på under utvikling
  Tilsmusset 2022-01 og framover - denne har jeg allerede gravd i, så den
             rapporteres, men teller ikke som bevis

Filteret har bare to av de fire målene fra felles/regime.py: bredde krever
flere mynter, og BTC-styrke viste seg skadelig (-40 % alene) og er droppet.
"""
import datetime
import json
import os
import sys

import numpy as np

sys.path.insert(0, ".")
from felles.regime import _glidende

CACHE = os.environ.get("BV_CACHE", "/tmp/bv")
GEBYR = 0.0025
PERIODER = [("Utvikling 2014-2019", "2014-01-01", "2019-12-31"),
            ("Fasit 2020-2021", "2020-01-01", "2021-12-31"),
            ("Tilsmusset 2022-2026", "2022-01-01", "2026-12-31")]
SYKLUSER = [("Fall 2014-15", "2014-09-17", "2015-08-25"),
            ("Opp 2015-17", "2015-08-26", "2017-12-16"),
            ("Fall 2018", "2017-12-17", "2018-12-15"),
            ("Opp 2019-21", "2018-12-16", "2021-11-09"),
            ("Fall 2022", "2021-11-10", "2022-11-21"),
            ("Opp 2023-26", "2022-11-22", "2026-10-06")]


def epoke(s):
    return int(datetime.datetime.fromisoformat(s + "T00:00:00+00:00").timestamp())


def last(tic="BTC-EUR"):
    r = json.load(open(os.path.join(CACHE, f"lang_{tic}.json"), encoding="utf-8"))
    return np.array([x[0] for x in r]), np.array([float(x[1]) for x in r])


def filter_trend(p, vindu):
    return (p > _glidende(p, vindu)).astype(float)


def filter_vol(p, kort=30, lang=180):
    r = np.diff(np.log(p), prepend=np.log(p[0]))
    return (_glidende(r ** 2, kort) <= _glidende(r ** 2, lang)).astype(float)


def hold(sig, min_dager):
    """Et nytt signal må holde i min_dager før det får virke."""
    ut = np.empty(len(sig))
    naa, teller = sig[0], 0
    for i, s in enumerate(sig):
        if s == naa:
            teller = 0
        else:
            teller += 1
            if teller >= min_dager:
                naa, teller = s, 0
        ut[i] = naa
    return ut


def kjor(p, vekt, gebyr=GEBYR):
    """vekt[i] bestemmes av data til og med dag i, og gjelder dag i+1."""
    v = np.empty(len(p))
    v[0] = 1.0
    for i in range(len(p) - 1):
        oms = abs(vekt[i] - (vekt[i - 1] if i else 0.0))
        v[i + 1] = v[i] * (1 + vekt[i] * (p[i + 1] / p[i] - 1)) * (1 - gebyr * oms)
    return v


def tall(v, ts):
    aar = (ts[-1] - ts[0]) / (365.25 * 86400)
    topp = np.maximum.accumulate(v)
    pa = (v[-1] / v[0]) ** (1 / aar) - 1
    ned = float((v / topp - 1).min())
    return v[-1] / v[0] - 1, pa, ned, (pa / abs(ned) if ned else 0.0)


def vis(navn, v, ts, n_skift=None):
    t, pa, ned, f = tall(v, ts)
    s = f"{n_skift:4d}" if n_skift is not None else "   -"
    print(f"  {navn:40s} {t * 100:+9.0f} % {pa * 100:+7.1f} %/år "
          f"{ned * 100:7.1f} % {f:6.2f} {s}")
    return f


def utsnitt(ts, fra, til):
    return (ts >= epoke(fra)) & (ts <= epoke(til))


def main():
    ts, p = last("BTC-EUR")
    print(f"Bitcoin i euro, {datetime.datetime.fromtimestamp(ts[0], datetime.UTC):%Y-%m-%d} "
          f"til {datetime.datetime.fromtimestamp(ts[-1], datetime.UTC):%Y-%m-%d}, "
          f"{len(p)} dager\n")

    print(f"{'':42s} {'total':>10s} {'per år':>11s} {'verste':>9s} {'forhold':>6s} skift")
    for navn, fra, til in PERIODER:
        mask = utsnitt(ts, fra, til)
        if mask.sum() < 400:
            continue
        print(f"\n{navn}")
        pp, tt = p[mask], ts[mask]
        vis("Bare eie bitcoin", kjor(pp, np.ones(len(pp))), tt)
        for vindu in (50, 100, 150, 200, 250):
            # signalet regnes på HELE serien og kuttes etterpå, ellers ville
            # hver periode startet med et blindt glidende snitt
            sig = hold(filter_trend(p, vindu), 5)[mask]
            vis(f"trend {vindu}d", kjor(pp, sig), tt, int((np.diff(sig) != 0).sum()))
        sig = hold(filter_trend(p, 150) * filter_vol(p), 5)[mask]
        vis("trend 150d + rolig volatilitet", kjor(pp, sig), tt,
            int((np.diff(sig) != 0).sum()))
        # halv eksponering i stedet for helt ut
        sig = (0.5 + 0.5 * hold(filter_trend(p, 150), 5))[mask]
        vis("trend 150d, 50 % ute i stedet for alt", kjor(pp, sig), tt,
            int((np.diff(sig) != 0).sum()))

    print("\n\nSYKLUS FOR SYKLUS (trend 150d mot å bare eie)")
    print(f"{'':30s} {'eie':>12s} {'filter':>12s}")
    sig_full = hold(filter_trend(p, 150), 5)
    for navn, fra, til in SYKLUSER:
        mask = utsnitt(ts, fra, til)
        if mask.sum() < 30:
            continue
        pp = p[mask]
        a = kjor(pp, np.ones(len(pp)))[-1] - 1
        b = kjor(pp, sig_full[mask])[-1] - 1
        print(f"  {navn:28s} {a * 100:+11.0f} % {b * 100:+11.0f} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
