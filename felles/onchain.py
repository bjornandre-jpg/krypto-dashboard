"""Enkel BTC-nettverksstatistikk (blockchain.info, gratis): trend i hashrate
og antall transaksjoner, siste 7 dager mot siste 30. Kun brukt for BTC."""
from .http import get_json
from .signal import klipp


def _trend(chart):
    v = [p["y"] for p in get_json(f"https://api.blockchain.info/charts/{chart}",
                                   {"timespan": "60days", "format": "json"})["values"]]
    if len(v) < 30:
        return 0.0
    return sum(v[-7:]) / 7 / (sum(v[-30:]) / 30) - 1


def score():
    try:
        return 0.5 * klipp(_trend("hash-rate") / 0.10) + 0.5 * klipp(_trend("n-transactions") / 0.20)
    except Exception:  # noqa: BLE001
        return None
