"""Kan vi tjene penger på nedturene i stedet for bare å stå utenfor?

Dagens system er long-only: det kan være inne eller ute. «Ute» er ikke
fortjeneste, bare fravær av tap. Spørsmålet her er om det samme trendsignalet
er godt nok til å tjene penger på vei ned.

Testes på bitcoin i euro 2014-2026, som dekker fallene i 2014-15, 2018 og
2022. Samme periodeinndeling som regime_lang.py:
  Utvikling  2014-2019
  Fasit      2020-2021   (ikke brukt til å velge noe)
  Tilsmusset 2022-2026   (allerede gjennomgått, teller ikke som bevis)

SHORT KOSTER PENGER Å HOLDE. På en perpetual betaler den som er short
funding til den som er long når markedet er i oppgang, og får betalt når det
er i nedgang. Over tid har funding vært positiv i krypto, altså en kostnad
for shorten. Det modelleres som en fast årlig kostnad, og testes med flere
nivåer siden den faktiske satsen svinger mye.
"""
import datetime
import sys

import numpy as np

sys.path.insert(0, ".")
from backtest.regime_lang import (GEBYR, PERIODER, SYKLUSER, epoke, filter_trend,
                                  hold, last, utsnitt)

SHORT_KOST = [0.0, 0.10, 0.20]      # årlig kostnad ved å ligge short


def kjor(p, vekt, gebyr=GEBYR, short_kost=0.0):
    """vekt kan være negativ. Short belastes short_kost per år mens den holdes."""
    v = np.empty(len(p))
    v[0] = 1.0
    dag = short_kost / 365.25
    for i in range(len(p) - 1):
        oms = abs(vekt[i] - (vekt[i - 1] if i else 0.0))
        avk = vekt[i] * (p[i + 1] / p[i] - 1)
        kost = dag * max(0.0, -vekt[i])
        v[i + 1] = max(v[i] * (1 + avk - kost) * (1 - gebyr * oms), 1e-12)
    return v


def tall(v, ts):
    aar = (ts[-1] - ts[0]) / (365.25 * 86400)
    topp = np.maximum.accumulate(v)
    pa = (v[-1] / v[0]) ** (1 / aar) - 1
    ned = float((v / topp - 1).min())
    return v[-1] / v[0] - 1, pa, ned, (pa / abs(ned) if ned else 0.0)


def vis(navn, v, ts):
    t, pa, ned, f = tall(v, ts)
    print(f"  {navn:44s} {t * 100:+9.0f} % {pa * 100:+8.1f} %/år {ned * 100:7.1f} % {f:6.2f}")
    return f


def main():
    ts, p = last("BTC-EUR")
    print(f"Bitcoin i euro {datetime.datetime.fromtimestamp(ts[0], datetime.UTC):%Y-%m-%d}"
          f" til {datetime.datetime.fromtimestamp(ts[-1], datetime.UTC):%Y-%m-%d}\n")

    trend = hold(filter_trend(p, 150), 5)          # 1 i opptrend, 0 i nedtrend
    varianter = {
        "Bare eie bitcoin": np.ones(len(p)),
        "Long/ut (dagens tankegang)": trend,
        "Long/halv short": trend - 0.5 * (1 - trend),
        "Long/full short (alltid i markedet)": trend - (1 - trend),
        "Bare short i nedtrend, ellers kontanter": -(1 - trend),
    }

    for navn, fra, til in PERIODER:
        mask = utsnitt(ts, fra, til)
        if mask.sum() < 400:
            continue
        print(f"{navn}")
        print(f"{'':46s} {'total':>10s} {'per år':>12s} {'verste':>9s} forhold")
        for vn, v in varianter.items():
            kost = 0.10 if "short" in vn.lower() else 0.0
            vis(vn, kjor(p[mask], v[mask], short_kost=kost), ts[mask])
        print()

    print("HVOR FØLSOM ER SHORTEN FOR HOLDEKOSTNADEN? (hele perioden)")
    print(f"{'':46s} {'per år':>12s} {'verste':>9s} forhold")
    for k in SHORT_KOST:
        v = varianter["Long/full short (alltid i markedet)"]
        vis(f"long/full short, {k * 100:.0f} % årlig shortkostnad",
            kjor(p, v, short_kost=k), ts)

    print("\nSYKLUS FOR SYKLUS (10 % shortkostnad)")
    print(f"{'':30s} {'eie':>11s} {'long/ut':>11s} {'long/short':>12s}")
    for navn, fra, til in SYKLUSER:
        mask = utsnitt(ts, fra, til)
        if mask.sum() < 30:
            continue
        pp = p[mask]
        a = kjor(pp, np.ones(len(pp)))[-1] - 1
        b = kjor(pp, trend[mask])[-1] - 1
        c = kjor(pp, varianter["Long/full short (alltid i markedet)"][mask],
                 short_kost=0.10)[-1] - 1
        print(f"  {navn:28s} {a * 100:+10.0f} % {b * 100:+10.0f} % {c * 100:+11.0f} %")

    print("\nHVOR OFTE TAR TRENDSIGNALET FEIL VEI?")
    retning = np.sign(np.diff(p))
    sig = np.where(trend[:-1] > 0, 1, -1)
    print(f"  treff neste dag: {(sig == retning).mean() * 100:.1f} % "
          f"(myntkast = 50 %)")
    for h in (5, 20, 60):
        fram = np.sign(p[h:] - p[:-h])
        print(f"  treff {h:2d} dager fram: {(np.where(trend[:-h] > 0, 1, -1) == fram).mean() * 100:.1f} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
