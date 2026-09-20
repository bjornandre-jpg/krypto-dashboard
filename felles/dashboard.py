"""Lager dashboard.json som nettsiden leser."""
import csv
import json
import os
from .portefolje import utc_iso


def skriv(pf, priser, signaler, fg, ekstra=None):
    m = pf.mappe
    pos = []
    for s, p in sorted(pf.s["posisjoner"].items()):
        pr = priser.get(s, p["snittpris"])
        pos.append({"asset": s.replace("-", "/"), "amount": p["mengde"], "entry_price": p["snittpris"],
                    "current_price": pr, "value_usd": p["mengde"] * pr,
                    "pnl_pct": (pr / p["snittpris"] - 1) * 100})
    pv = sum(x["value_usd"] for x in pos)
    eq = pf.kontanter + pv
    handler = _siste_csv(os.path.join(m, "handler.csv"), 15)
    kurve = _siste_csv(os.path.join(m, "egenkapital.csv"), 10 ** 6)
    if len(kurve) > 300:                      # jevn nedsampling, siste punkt alltid med
        steg = len(kurve) / 300
        kurve = [kurve[int(i * steg)] for i in range(300)] + [kurve[-1]]
    data = {"updated_at": utc_iso(), "signals_updated_at": utc_iso(), "cash_usd": pf.kontanter,
            "start_capital": pf.s.get("startkapital", 1000.0), "equity_usd": eq,
            "positions_value_usd": pv, "total_exposure_pct": pv / eq * 100 if eq else 0,
            "fear_greed_value": fg, "positions": pos, "signals": signaler,
            "recent_trades": list(reversed(handler)),
            "equity_curve": [[r["tid"], float(r["egenkapital"])] for r in kurve],
            **(ekstra or {})}
    with open(os.path.join(m, "dashboard.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _siste_csv(fil, n):
    if not os.path.exists(fil):
        return []
    with open(fil, encoding="utf-8") as f:
        return list(csv.DictReader(f))[-n:]
