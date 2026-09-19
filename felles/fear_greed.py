"""Crypto Fear & Greed-indeks (alternative.me), gratis."""
from .http import get_json


def naa():
    d = get_json("https://api.alternative.me/fng/", {"limit": 1})["data"][0]
    return int(d["value"])


def historikk():
    """[(ts_sek, verdi)] stigende, hele historikken."""
    d = get_json("https://api.alternative.me/fng/", {"limit": 0})["data"]
    return sorted((int(x["timestamp"]), int(x["value"])) for x in d)
