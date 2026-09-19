"""Sjekker at alle datakilder svarer fra der koden kjører (f.eks. GitHub sine servere)."""
from felles import kucoin, fear_greed, nyheter, onchain

tester = {
    "KuCoin spot priser": lambda: f"{len(kucoin.priser())} par",
    "KuCoin candles": lambda: f"{len(kucoin.candles('BTC-USDT', '4hour', 10))} candles",
    "KuCoin futures": lambda: f"{len(kucoin.aktive_kontrakter())} kontrakter",
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
