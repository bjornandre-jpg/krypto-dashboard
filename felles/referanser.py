"""Referansekurver for dashbordet: S&P 500, Nordnet Global Indeks 125 og
Virtune Crypto Top 10 Index ETP SEK. Utvikling i % fra felles start
(sluttkurs 2026-09-21, dagen alle tre kryptosystemene ble nullstilt),
målt i hver referanses egen valuta. Skriver state/referanser.json."""
import json
import os
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from .http import get_json

START_DATO = "2026-09-27"
REF = {
    "sp500": {"navn": "S&P 500", "valuta": "USD", "kilde": "yahoo", "id": "^GSPC", "intradag": True},
    "btc": {"navn": "Bitcoin", "valuta": "EUR", "kilde": "bitvavo", "id": "BTC-EUR", "intradag": True},
    "nordnet125": {"navn": "Nordnet Global Indeks 125", "valuta": "NOK", "kilde": "yahoo", "id": "0P0001RMV1.IR", "intradag": False},
    "virtune10": {"navn": "Virtune Crypto Top 10", "valuta": "SEK", "kilde": "nasdaq", "id": "TX4856348", "intradag": True},
}
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _yahoo(tid, intradag):
    start = int(datetime.fromisoformat(START_DATO).replace(tzinfo=timezone.utc).timestamp()) - 5 * 86400
    base = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(tid)
    d = get_json(base, {"period1": start, "period2": int(time.time()), "interval": "1d"}, headers=UA)["chart"]["result"][0]
    dag = {}
    for ts, c in zip(d.get("timestamp") or [], d["indicators"]["quote"][0]["close"]):
        if c is not None:
            dag[datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")] = (ts, c)
    punkter = []
    if intradag:   # timesbarer for jevnere kurve
        h = get_json(base, {"period1": start, "period2": int(time.time()), "interval": "1h"}, headers=UA)["chart"]["result"][0]
        punkter = [(ts, c) for ts, c in zip(h.get("timestamp") or [], h["indicators"]["quote"][0]["close"]) if c is not None]
        m = d.get("meta", {})
        if m.get("regularMarketPrice") and m.get("regularMarketTime"):
            punkter.append((m["regularMarketTime"], m["regularMarketPrice"]))
    return dag, punkter


def _bitvavo(market):
    """Kurshistorikk fra Bitvavo, samme kilde som systemene handler på."""
    from . import bitvavo
    dag = {datetime.fromtimestamp(c[0], timezone.utc).strftime("%Y-%m-%d"): (c[0] + 86399, c[4])
           for c in bitvavo.candles(market, "1d", 30, kun_lukkede=False)}
    time_ = [(c[0] + 14399, c[4]) for c in bitvavo.candles(market, "4h", 200, kun_lukkede=False)]
    return dag, time_


def _nasdaq(oid):
    url = f"https://api.nasdaq.com/api/nordic/instruments/{oid}/chart"
    fra = (datetime.fromisoformat(START_DATO) - timedelta(days=10)).strftime("%Y-%m-%d")
    til = max(datetime.now(timezone.utc).strftime("%Y-%m-%d"), fra)
    d = get_json(url, {"assetClass": "ETN/ETC", "fromDate": fra, "toDate": til}, headers=UA)["data"]
    dag = {p["z"]["dateTime"]: (p["x"] + 15 * 3600 + 1800, float(p["y"])) for p in d.get("CP") or []}
    i = get_json(url, {"assetClass": "ETN/ETC"}, headers=UA)["data"]
    punkter = [(p["x"], float(p["y"])) for p in i.get("CP") or []]
    return dag, punkter


def bygg(mappe="state"):
    ut = {"start_dato": START_DATO, "oppdatert": _iso(time.time()), "serier": {}}
    for k, r in REF.items():
        try:
            if r["kilde"] == "yahoo":
                dag, intradag = _yahoo(r["id"], r["intradag"])
            elif r["kilde"] == "bitvavo":
                dag, intradag = _bitvavo(r["id"])
            else:
                dag, intradag = _nasdaq(r["id"])
        except Exception as e:  # noqa: BLE001 - én død kilde skal ikke stoppe resten
            print(f"ADVARSEL referanse {k}: {e}")
            continue
        # nullpunktet er siste kjente sluttkurs til og med startdatoen; et fond som
        # bare prises én gang i døgnet får da gårsdagens kurs som utgangspunkt
        tidligere = sorted(d_ for d_ in dag if d_ <= START_DATO)
        if not tidligere:
            print(f"Referanse {k}: ingen kurs på eller før {START_DATO}")
            continue
        basis_dato = tidligere[-1]
        base_ts, base = dag[basis_dato]
        slutt_start = max(base_ts, int(datetime.fromisoformat(START_DATO + "T00:00:00+00:00").timestamp()))
        pkt = {ts: c for d_, (ts, c) in dag.items() if d_ > basis_dato}
        pkt.update({ts: c for ts, c in intradag if ts > slutt_start})
        kurve = [[_iso(slutt_start), 0.0]] + [[_iso(ts), round((c / base - 1) * 100, 3)] for ts, c in sorted(pkt.items())]
        if len(kurve) > 400:
            steg = len(kurve) / 400
            kurve = [kurve[int(i * steg)] for i in range(400)] + [kurve[-1]]
        ut["serier"][k] = {"navn": r["navn"], "valuta": r["valuta"], "startkurs": base,
                           "basis_dato": basis_dato, "kurve": kurve}
    with open(os.path.join(mappe, "referanser.json"), "w", encoding="utf-8") as f:
        json.dump(ut, f, ensure_ascii=False)
    return ut


if __name__ == "__main__":
    u = bygg()
    for k, s in u["serier"].items():
        print(f"{s['navn']}: start {s['startkurs']:.2f} {s['valuta']}, nå {s['kurve'][-1][1]:+.2f} % ({len(s['kurve'])} punkter)")
