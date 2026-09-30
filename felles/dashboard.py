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
                    "current_price": pr, "verdi": p["mengde"] * pr,
                    "pnl_pct": (pr / p["snittpris"] - 1) * 100})
    pv = sum(x["verdi"] for x in pos)
    eq = pf.kontanter + pv
    handler = _berik(_siste_csv(os.path.join(m, "handler.csv"), 15), pf, priser)
    kurve = _siste_csv(os.path.join(m, "egenkapital.csv"), 10 ** 6)
    if len(kurve) > 300:                      # jevn nedsampling, siste punkt alltid med
        steg = len(kurve) / 300
        kurve = [kurve[int(i * steg)] for i in range(300)] + [kurve[-1]]
    data = {"updated_at": utc_iso(), "signals_updated_at": utc_iso(), "valuta": "EUR", "kontanter": pf.kontanter,
            "startkapital": pf.s.get("startkapital", 1000.0), "egenkapital": eq,
            "posisjonsverdi": pv, "total_exposure_pct": pv / eq * 100 if eq else 0,
            "fear_greed_value": fg, "positions": pos, "signals": signaler,
            "recent_trades": list(reversed(handler)),
            "equity_curve": [[r["tid"], float(r["egenkapital"])] for r in kurve],
            **(ekstra or {})}
    with open(os.path.join(m, "dashboard.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _berik(handler, pf, priser):
    """Fyller ut avkastning og dager per handel.

    Salg har realisert resultat fra loggen. Kjøp får urealisert resultat mot
    dagens kurs, men bare så lenge posisjonen fortsatt er åpen - er den solgt,
    står resultatet på salgsraden i stedet.
    """
    from .portefolje import _dager_siden
    for h in handler:
        sym = h.get("mynt", "")
        h["dager_vist"] = h.get("dager") or ""
        if h.get("side") == "KJØP":
            p = pf.pos(sym)
            pris = priser.get(sym)
            kjopspris = float(h.get("pris") or 0)
            if p and pris and kjopspris > 0:
                h["urealisert_pst"] = round((pris / kjopspris - 1) * 100, 3)
                h["urealisert"] = round(float(h.get("belop") or 0) * (pris / kjopspris - 1), 4)
            d = _dager_siden(h.get("tid"))
            h["dager_vist"] = "" if d is None else round(d, 2)
    return handler


def _siste_csv(fil, n):
    if not os.path.exists(fil):
        return []
    with open(fil, encoding="utf-8") as f:
        return list(csv.DictReader(f))[-n:]
