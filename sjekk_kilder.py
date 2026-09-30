"""Sjekker at alle datakilder svarer fra der koden kjører (f.eks. GitHub sine servere)."""
from felles import bitvavo, kucoin, fear_greed, nyheter, onchain

tester = {
    "Bitvavo priser": lambda: f"{len(bitvavo.priser())} EUR-par",
    "Bitvavo candles": lambda: f"{len(bitvavo.candles('BTC-EUR', '4h', 10))} candles",
    "Bitvavo spread": lambda: f"BTC {bitvavo.spreads()['BTC-EUR']:.3f} %",
    "KuCoin futures (funding)": lambda: f"{len(kucoin.aktive_kontrakter())} kontrakter",
    "Fear & Greed": lambda: f"verdi {fear_greed.naa()}",
    "Nyheter": lambda: "titler: %s" % (nyheter.score()[1],),
    "On-chain": lambda: f"score {onchain.score()}",
}
feil = 0
for navn, f in tester.items():
    try:
        print(f"OK    {navn}: {f()}")
    except Exception as e:  # noqa: BLE001
        feil += 1
        print(f"FEIL  {navn}: {e}")
raise SystemExit(1 if feil else 0)
