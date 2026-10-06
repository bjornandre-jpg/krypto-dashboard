"""Kan avkastningen økes? Tester de knappene vi faktisk har.

Hver variant kjøres på nøyaktig samme kurser og gebyrer som grunnvarianten,
slik at forskjellen bare skyldes knappen vi vrir på. Tallene er ikke et løfte
om framtiden - de sier hva innstillingen ville gjort de siste fire årene.
"""
import sys

sys.path.insert(0, ".")
from backtest.bitvavo_backtest import kjor
from backtest.mot_hodl import CFG, START, VEKTER, hodl, nokkeltall
from backtest.bitvavo_backtest import last_data
from system1.kjor import MYNTER, SMA_RASK, SMA_TREG

VARIANTER = [
    # (navn, endringer i cfg, terskel, bekreftelser, rask, treg)
    ("Dagens innstilling",        {}, 0.30, 2, SMA_RASK, SMA_TREG),
    ("Handle oftere: 1 bekreftelse", {}, 0.30, 1, SMA_RASK, SMA_TREG),
    ("Handle oftere: terskel 0,20", {}, 0.20, 2, SMA_RASK, SMA_TREG),
    ("Handle sjeldnere: terskel 0,40", {}, 0.40, 2, SMA_RASK, SMA_TREG),
    ("Mer i markedet: 85 % maks",  {"max_total": 0.85}, 0.30, 2, SMA_RASK, SMA_TREG),
    ("Fullt investert: 100 %",     {"max_total": 1.00}, 0.30, 2, SMA_RASK, SMA_TREG),
    ("Større poster: 20 % per mynt", {"max_per_mynt": 0.20, "max_total": 1.00}, 0.30, 2, SMA_RASK, SMA_TREG),
    ("Uten stop-loss",             {"stop_loss": 0.99}, 0.30, 2, SMA_RASK, SMA_TREG),
    ("Tregere trend: 20/60",       {}, 0.30, 2, 20, 60),
    ("Raskere trend: 5/20",        {}, 0.30, 2, 5, 20),
]


def main():
    data, _, _ = last_data(MYNTER, "1d")
    mkt = [m for m in MYNTER if m in data]
    btc = nokkeltall(hodl(data, ["BTC-EUR"]))

    print(f"{'variant':34s} {'total':>9s} {'per år':>8s} {'verste fall':>12s} "
          f"{'handler':>8s} {'per år/risiko':>13s}")
    rader = []
    for navn, endring, terskel, bekr, rask, treg in VARIANTER:
        r = kjor(mkt, "1d", 86400, rask, treg, VEKTER, {**CFG, **endring},
                 terskel=terskel, bekreftelser=bekr, gebyr=0.0025, start=START)
        n = nokkeltall(r["kurve"])
        forhold = n["annualisert"] / abs(n["maks_nedgang"]) if n["maks_nedgang"] else 0
        rader.append((navn, n, r["handler"], forhold))
        print(f"{navn:34s} {n['avkastning'] * 100:+8.1f} % {n['annualisert'] * 100:+7.1f} % "
              f"{n['maks_nedgang'] * 100:11.1f} % {r['handler']:8d} {forhold:13.2f}")

    f_btc = btc["annualisert"] / abs(btc["maks_nedgang"])
    print(f"\n{'Bare eie bitcoin':34s} {btc['avkastning'] * 100:+8.1f} % "
          f"{btc['annualisert'] * 100:+7.1f} % {btc['maks_nedgang'] * 100:11.1f} % "
          f"{1:8d} {f_btc:13.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
