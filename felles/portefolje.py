"""Papirportefølje, risikostyring og handelslogikk (delt av begge systemene).

Rekkefølge per mynt (som dokumentert i prosjektplanen, seksjon 8):
 1. stop-loss / take-profit mot kostbasis
 2. drift-rebalansering tilbake til målvekt
 3. bekreftet signal (hysterese): KJØP -> signalstyrke-skalert målposisjon,
    SELG -> selg alt
Kjøp sjekkes mot maks per mynt, maks total eksponering, maks handler/dag,
maks dagstap og kill-switch. Salg (risikoreduksjon) blokkeres aldri av
handelsgrensen. Kun long, kun spot, INGEN ekte penger.
"""
import csv
import json
import os
from datetime import datetime, timezone

STANDARD = {
    "gebyr": 0.001,            # KuCoin spot taker
    "min_handel": 5.0,         # USDT
    "stop_loss": 0.15,        # vidt nok til at vanlig krypto-støy ikke kaster ut posisjonen
    "take_profit": None,      # AV: et trendsystem lever av de få store vinnerne (backtest 2026-09-25)
    "rebal_mult": 1.05,
    "max_handler_dag": 30,
    "max_dagstap": 0.05,       # stopper nye kjøp resten av døgnet (UTC)
    "terskel": 0.30,
}


def utc_iso(ts=None):
    d = datetime.fromtimestamp(ts, timezone.utc) if ts else datetime.now(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


class Portefolje:
    def __init__(self, cfg, startkapital=1000.0, mappe=None):
        self.cfg = {**STANDARD, **cfg}
        self.mappe = mappe
        self.handler = []          # nye handler denne kjøringen
        fil = os.path.join(mappe, "portefolje.json") if mappe else None
        if fil and os.path.exists(fil):
            with open(fil, encoding="utf-8") as f:
                self.s = json.load(f)
        else:
            self.s = {"kontanter": startkapital, "startkapital": startkapital,
                      "posisjoner": {}, "dag": {}, "opprettet": utc_iso()}

    # ---------- tilstand ----------
    @property
    def kontanter(self):
        return self.s["kontanter"]

    def pos(self, sym):
        return self.s["posisjoner"].get(sym)

    def verdi(self, sym, pris):
        p = self.pos(sym)
        return p["mengde"] * pris if p else 0.0

    def posisjonsverdi(self, priser):
        return sum(p["mengde"] * priser.get(s, p["snittpris"]) for s, p in self.s["posisjoner"].items())

    def egenkapital(self, priser):
        return self.kontanter + self.posisjonsverdi(priser)

    def start_dag(self, dato, egenkapital):
        if self.s["dag"].get("dato") != dato:
            self.s["dag"] = {"dato": dato, "start_egenkapital": egenkapital, "handler": 0}

    # ---------- handler ----------
    def _logg(self, ts, sym, side, mengde, pris, belop, gebyr, grunn):
        self.handler.append({"tid": utc_iso(ts), "mynt": sym, "side": side,
                             "mengde": round(mengde, 10), "pris": pris,
                             "belop_usdt": round(belop, 4), "gebyr_usdt": round(gebyr, 4),
                             "grunn": grunn})
        self.s["dag"]["handler"] = self.s["dag"].get("handler", 0) + 1

    def kjop(self, sym, usd, pris, grunn, ts=None, maalvekt=None):
        usd = min(usd, self.kontanter)
        if usd < self.cfg["min_handel"]:
            return 0.0
        gebyr = usd * self.cfg["gebyr"]
        mengde = (usd - gebyr) / pris
        p = self.s["posisjoner"].setdefault(sym, {"mengde": 0.0, "snittpris": pris, "maalvekt": 0.0})
        ny = p["mengde"] + mengde
        p["snittpris"] = (p["mengde"] * p["snittpris"] + mengde * pris) / ny
        p["mengde"] = ny
        if maalvekt is not None:
            p["maalvekt"] = maalvekt
        self.s["kontanter"] -= usd
        self._logg(ts, sym, "KJØP", mengde, pris, usd, gebyr, grunn)
        return usd

    def selg(self, sym, mengde, pris, grunn, ts=None, maalvekt=None):
        p = self.pos(sym)
        if not p:
            return 0.0
        mengde = min(mengde, p["mengde"])
        if mengde * pris < self.cfg["min_handel"] and mengde < p["mengde"]:
            return 0.0
        brutto = mengde * pris
        gebyr = brutto * self.cfg["gebyr"]
        p["mengde"] -= mengde
        self.s["kontanter"] += brutto - gebyr
        if p["mengde"] * pris < 0.01:
            del self.s["posisjoner"][sym]
        elif maalvekt is not None:
            p["maalvekt"] = maalvekt
        self._logg(ts, sym, "SELG", mengde, pris, brutto, gebyr, grunn)
        return brutto

    # ---------- risiko ----------
    def kjop_tillatt(self, sym, usd, priser, egenkapital):
        """Returnerer beløpet som faktisk kan kjøpes (0 hvis blokkert) + grunn."""
        c = self.cfg
        if c.get("kill_switch"):
            return 0.0, "kill-switch"
        if self.s["dag"].get("handler", 0) >= c["max_handler_dag"]:
            return 0.0, "maks handler/dag"
        start = self.s["dag"].get("start_egenkapital") or egenkapital
        if egenkapital < start * (1 - c["max_dagstap"]):
            return 0.0, "maks dagstap"
        pris = priser[sym]
        rom_mynt = c["max_per_mynt"] * egenkapital - self.verdi(sym, pris)
        rom_total = c["max_total"] * egenkapital - self.posisjonsverdi(priser)
        usd = min(usd, rom_mynt, rom_total, self.kontanter)
        if usd < c["min_handel"]:
            return 0.0, "eksponeringsgrense"
        return usd, ""


def vurder_mynt(pf, sym, priser, egenkapital, beslutn, score, bekreftet, signal_aktivt, ts=None):
    """Kjører hele beslutningskjeden for én mynt. Returnerer handlingstekst eller ''."""
    c = pf.cfg
    pris = priser[sym]
    p = pf.pos(sym)
    verdi = pf.verdi(sym, pris)

    # 1. stop-loss / take-profit
    if p:
        endring = pris / p["snittpris"] - 1
        if endring <= -c["stop_loss"]:
            pf.selg(sym, p["mengde"], pris, f"stop-loss {endring:+.1%}", ts)
            return "stop-loss"
        if c["take_profit"] and endring >= c["take_profit"]:
            pf.selg(sym, p["mengde"], pris, f"take-profit {endring:+.1%}", ts)
            return "take-profit"
        # 2. drift-rebalansering
        maal = p.get("maalvekt") or c["max_per_mynt"]
        if verdi > maal * c["rebal_mult"] * egenkapital:
            overskudd = verdi - maal * egenkapital
            if pf.selg(sym, overskudd / pris, pris, "rebalansering", ts):
                return "rebalansering"

    # 3. signal med hysterese
    if not (signal_aktivt and bekreftet):
        return ""
    if beslutn == "KJØP":
        maalvekt = c["max_per_mynt"] * min(1.0, abs(score))
        diff = maalvekt * egenkapital - verdi
        if diff >= c["min_handel"]:
            usd, _ = pf.kjop_tillatt(sym, diff, priser, egenkapital)
            if usd and pf.kjop(sym, usd, pris, f"signal {score:+.2f}", ts, maalvekt):
                return "kjøp"
        elif diff <= -c["min_handel"] and p:
            if pf.selg(sym, -diff / pris, pris, f"signal svekket {score:+.2f}", ts, maalvekt):
                return "trim"
        elif p:
            p["maalvekt"] = maalvekt
    elif beslutn == "SELG" and p:
        pf.selg(sym, p["mengde"], pris, f"signal {score:+.2f}", ts)
        return "salg"
    return ""


def lagre(pf, egenkapital, ekstra_csv=None):
    """Skriver portefølje, og appender handler/egenkapital til CSV-historikk."""
    m = pf.mappe
    os.makedirs(m, exist_ok=True)
    with open(os.path.join(m, "portefolje.json"), "w", encoding="utf-8") as f:
        json.dump(pf.s, f, ensure_ascii=False, indent=1)
    if pf.handler:
        _append_csv(os.path.join(m, "handler.csv"), pf.handler)
    _append_csv(os.path.join(m, "egenkapital.csv"),
                [{"tid": utc_iso(), "egenkapital": round(egenkapital, 4),
                  "kontanter": round(pf.kontanter, 4)}])
    for navn, rader in (ekstra_csv or {}).items():
        _append_csv(os.path.join(m, navn), rader)


def _append_csv(fil, rader):
    ny = not os.path.exists(fil)
    with open(fil, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rader[0].keys()))
        if ny:
            w.writeheader()
        w.writerows(rader)
