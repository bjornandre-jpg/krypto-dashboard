"""Slår Krypto13-strategien å bare eie bitcoin?

Det er det egentlige spørsmålet. En strategi som gir +40 % mens bitcoin gir
+80 % har tapt penger, uansett hvor pent kurven ser ut alene.

Sammenligner tre ting på nøyaktig samme kurser og samme periode:
  1. Krypto13-strategien, med ekte gebyrer
  2. kjøp bitcoin på dag én og rør den aldri
  3. kjøp like mye av alle 13 på dag én og rør dem aldri

Rapporterer også år for år, fordi et snitt over fire år kan skjule at
strategien vant stort i ett marked og tapte jevnt i alle andre.
"""
import datetime
import json
import os
import sys

sys.path.insert(0, ".")
from backtest.bitvavo_backtest import kjor, last_data
from system1.kjor import MYNTER, SMA_RASK, SMA_TREG

# Live-vektene uten nyhetsleddet (som backtesten ikke har), skalert til 1.
VEKTER = {"ta": 0.80 / 0.95, "fg": 0.05 / 0.95, "funding": 0.10 / 0.95}
CFG = {"max_per_mynt": 0.10, "max_total": 0.60, "stop_loss": 0.15, "take_profit": None}
START = 1000.0


def hodl(data, markeder, start=START):
    """Kjøper like mye av hver mynt første dag alle finnes, og holder."""
    felles = sorted(set.intersection(*[{c[0] for c in data[m]["c"]} for m in markeder]))
    t0 = felles[0]
    andel = start / len(markeder)
    mengder = {m: andel / data[m]["open"][t0] for m in markeder}
    kurve = []
    for t in felles:
        v = sum(mengder[m] * data[m]["open"][t] for m in markeder if t in data[m]["open"])
        kurve.append((t, v))
    return kurve


def nokkeltall(kurve, start=START):
    topp, ned = start, 0.0
    for _, v in kurve:
        topp = max(topp, v)
        ned = min(ned, v / topp - 1)
    aar = (kurve[-1][0] - kurve[0][0]) / (365.25 * 86400)
    avk = kurve[-1][1] / start - 1
    return {"avkastning": avk, "annualisert": (1 + avk) ** (1 / aar) - 1,
            "maks_nedgang": ned, "sluttverdi": kurve[-1][1]}


def per_aar(kurve):
    """{år: avkastning i prosent} basert på første og siste verdi i hvert år."""
    aar = {}
    for t, v in kurve:
        a = datetime.datetime.fromtimestamp(t, datetime.UTC).year
        aar.setdefault(a, [v, v])[1] = v
    return {a: (b / f - 1) * 100 for a, (f, b) in aar.items()}


def main():
    data, _, _ = last_data(MYNTER, "1d")
    mangler = [m for m in MYNTER if m not in data]
    if mangler:
        print(f"ADVARSEL: mangler data for {mangler}")
    mkt = [m for m in MYNTER if m in data]

    print(f"{len(mkt)} mynter · daglige kurser fra Bitvavo · gebyr 0,25 % per handel\n")

    r = kjor(mkt, "1d", 86400, SMA_RASK, SMA_TREG, VEKTER, CFG, gebyr=0.0025)
    strategi = r["kurve"]
    btc = hodl(data, ["BTC-EUR"])
    alle = hodl(data, mkt)

    rader = [("Krypto13-strategien", {**nokkeltall(strategi), "handler": r["handler"]}, strategi),
             ("Bare eie bitcoin", {**nokkeltall(btc), "handler": 1}, btc),
             ("Like mye av alle 13", {**nokkeltall(alle), "handler": len(mkt)}, alle)]

    print(f"{'':22s} {'total':>9s} {'per år':>8s} {'verste fall':>12s} {'handler':>8s}")
    for navn, n, _ in rader:
        print(f"{navn:22s} {n['avkastning'] * 100:+8.1f} % {n['annualisert'] * 100:+7.1f} % "
              f"{n['maks_nedgang'] * 100:11.1f} % {n['handler']:8d}")

    print("\nÅr for år (%):")
    aarlige = {navn: per_aar(k) for navn, _, k in rader}
    alle_aar = sorted({a for d in aarlige.values() for a in d})
    print(f"{'':22s}" + "".join(f"{a:>9d}" for a in alle_aar))
    for navn in aarlige:
        print(f"{navn:22s}" + "".join(f"{aarlige[navn].get(a, 0):+8.1f} " for a in alle_aar))

    ut = {"laget": datetime.datetime.now(datetime.UTC).isoformat(),
          "mynter": mkt, "resultater": {navn: n for navn, n, _ in rader},
          "aarlig": aarlige}
    os.makedirs("state", exist_ok=True)
    with open("state/mot_hodl.json", "w", encoding="utf-8") as f:
        json.dump(ut, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
