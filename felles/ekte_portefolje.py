"""Portefølje som handler med ekte penger på Bitvavo.

Arver all beslutningslogikk fra papirporteføljen, og bytter bare ut de to
metodene som flytter verdier: kjop() og selg() legger nå faktiske ordrer.
Slik kjører ekte penger gjennom nøyaktig samme regler som papirhandelen,
og en endring i strategien treffer begge.

Tre prinsipper styrer koden, alle tre lært av feil 2026-10-02:

1. SALDOENDRINGEN ER FASIT. Hva vi faktisk fikk og hva det faktisk kostet
   leses som forskjellen på saldoen før og etter ordren - ikke fra feltene i
   ordresvaret. Bitvavo kan oppgi gebyret i base- eller kvotevaluta, kan
   returnere et ordresvar før tallene er fylt ut, og svarer 404 på en ordre
   som nettopp er ferdig. Saldoen lyver ikke.
2. BOKA SKRIVES ETTER HVER ENESTE ORDRE. Første natt kjøpte systemet SOL,
   krasjet på neste mynt, og mistet hele boka fordi den ble skrevet til slutt.
   Posisjonen var ekte, bokføringen fantes ikke, og avstemmingen stoppet alt
   neste time. Nå er hver handel på disk før neste ordre sendes.
3. BØRSEN EIER ANTALLET, BOKA EIER KOSTPRISEN. Kostpris, målvekt og
   åpningsdato finnes ikke på børsen og er vårt ansvar.

Tørrkjøring er standard: uten BITVAVO_EKTE=ja regnes ordrene ut og skrives
ut, men sendes ikke, og boka står urørt.
"""
import json
import os
import time

from . import bitvavo_handel as bh
from .portefolje import Portefolje, _append_csv, _dager_siden, utc_iso

VENT_PA_OPPGJOR = 15        # sekunder vi venter på at saldoen endrer seg


class EktePortefolje(Portefolje):
    def __init__(self, cfg, mappe, operator_id, presisjon=None, startkapital=0.0):
        super().__init__(cfg, startkapital, mappe)
        self.operator_id = operator_id
        self.presisjon = presisjon or {}
        self.planlagt = []          # ordrer vi ville sendt (tørrkjøring)

    # ---------- hjelpere ----------
    def _pres(self, sym):
        return self.presisjon.get(sym, {"mengde": 8, "notional": 2})

    @staticmethod
    def _flat(saldo):
        return {k: v["tilgjengelig"] + v["i_ordre"] for k, v in saldo.items()}

    def _vent_pa_endring(self, base, for_):
        """Leser saldoen til den har endret seg, eller til tiden er ute.

        Returnerer den nye saldoen uansett - er den uendret, oppdager den som
        kalte det ved at differansen er null, og vi bokfører ingenting.
        """
        for forsok in range(VENT_PA_OPPGJOR + 1):
            etter = self._flat(bh.saldo())
            if (abs(etter.get(base, 0.0) - for_.get(base, 0.0)) > 0
                    or abs(etter.get("EUR", 0.0) - for_.get("EUR", 0.0)) > 0):
                return etter
            if forsok < VENT_PA_OPPGJOR:
                time.sleep(1)
        return etter

    @staticmethod
    def _gebyr_eur(o, pris):
        """Gebyret fra ordresvaret, omregnet til euro. Kun til loggen."""
        try:
            g = float(o.get("feePaid") or 0)
        except (TypeError, ValueError):
            return 0.0
        return g * pris if (o.get("feeCurrency") or "EUR").upper() != "EUR" else g

    def _lagre_bok(self, rad=None):
        """Skriver boka til disk med én gang, og loggfører handelen."""
        if not self.mappe:
            return
        os.makedirs(self.mappe, exist_ok=True)
        with open(os.path.join(self.mappe, "portefolje.json"), "w", encoding="utf-8") as f:
            json.dump(self.s, f, ensure_ascii=False, indent=1)
        if rad:
            _append_csv(os.path.join(self.mappe, "handler.csv"), [rad])

    def _sett_saldo(self, etter, sym):
        self.s["kontanter"] = etter.get("EUR", 0.0)
        p = self.pos(sym)
        if p:
            p["mengde"] = etter.get(sym.split("-")[0], 0.0)
            if p["mengde"] <= 0:
                del self.s["posisjoner"][sym]

    # ---------- handel ----------
    def kjop(self, sym, usd, pris, grunn, ts=None, maalvekt=None):
        usd = min(usd, self.kontanter, bh.MAKS_ORDRE)
        if usd < max(self.cfg["min_handel"], bh.MIN_ORDRE):
            return 0.0
        base = sym.split("-")[0]
        for_ = self._flat(bh.saldo())

        status, data = bh.markedsordre(sym, "buy", belop_eur=usd,
                                       presisjon=self._pres(sym), grunn=grunn,
                                       operator_id=self.operator_id)
        if status == "avvist":
            print(f"  AVVIST kjøp {sym} {usd:.2f} EUR: {data}")
            return 0.0
        if status == "tørrkjøring":
            self.planlagt.append({"side": "KJØP", "mynt": sym, "belop": round(usd, 2),
                                  "pris": pris, "grunn": grunn})
            print(f"  [tørrkjøring] ville kjøpt {sym} for {usd:.2f} EUR ({grunn})")
            return 0.0

        etter = self._vent_pa_endring(base, for_)
        mengde = etter.get(base, 0.0) - for_.get(base, 0.0)
        kost = for_.get("EUR", 0.0) - etter.get("EUR", 0.0)
        if mengde <= 0 or kost <= 0:
            print(f"  ADVARSEL {sym}: ordre {data.get('orderId')} ga ingen "
                  f"saldoendring (mengde {mengde:+.8f}, euro {-kost:+.2f}). "
                  f"Ingenting bokført.")
            return 0.0

        snitt = kost / mengde
        p = self.s["posisjoner"].setdefault(sym, {"mengde": 0.0, "snittpris": snitt,
                                                  "maalvekt": 0.0})
        if p["mengde"] <= 0:
            p["apnet"] = utc_iso(ts)
        p["snittpris"] = (p["mengde"] * p["snittpris"] + kost) / (p["mengde"] + mengde)
        p["mengde"] += mengde
        if maalvekt is not None:
            p["maalvekt"] = maalvekt
        self._sett_saldo(etter, sym)
        self._logg(ts, sym, "KJØP", mengde, snitt, kost,
                   self._gebyr_eur(data, pris), grunn)
        self._lagre_bok(self.handler[-1])
        print(f"  KJØPT {sym}: {mengde:.8f} for {kost:.2f} EUR "
              f"(kurs {snitt:.6f}) - {grunn}")
        return kost

    def selg(self, sym, mengde, pris, grunn, ts=None, maalvekt=None):
        p = self.pos(sym)
        if not p:
            return 0.0
        base = sym.split("-")[0]
        mengde = min(mengde, p["mengde"])
        helt_ut = mengde >= p["mengde"] * 0.999
        des = self._pres(sym).get("mengde", 8)
        mengde = int(mengde * 10 ** des) / 10 ** des      # rund NED, aldri opp
        if mengde <= 0:
            return 0.0
        if mengde * pris < max(self.cfg["min_handel"], bh.MIN_ORDRE) and not helt_ut:
            return 0.0
        if mengde * pris < bh.MIN_ORDRE:
            print(f"  {sym}: rest verdt {mengde * pris:.2f} EUR er under "
                  f"minsteordren, lar den ligge")
            return 0.0

        for_ = self._flat(bh.saldo())
        status, data = bh.markedsordre(sym, "sell", mengde=mengde,
                                       presisjon=self._pres(sym), grunn=grunn,
                                       operator_id=self.operator_id)
        if status == "avvist":
            print(f"  AVVIST salg {sym} {mengde:.8f}: {data}")
            return 0.0
        if status == "tørrkjøring":
            self.planlagt.append({"side": "SELG", "mynt": sym, "mengde": mengde,
                                  "belop": round(mengde * pris, 2), "pris": pris,
                                  "grunn": grunn})
            print(f"  [tørrkjøring] ville solgt {mengde:.8f} {sym} "
                  f"(~{mengde * pris:.2f} EUR) ({grunn})")
            return 0.0

        etter = self._vent_pa_endring(base, for_)
        solgt = for_.get(base, 0.0) - etter.get(base, 0.0)
        netto = etter.get("EUR", 0.0) - for_.get("EUR", 0.0)
        if solgt <= 0 or netto <= 0:
            print(f"  ADVARSEL {sym}: salgsordre {data.get('orderId')} ga ingen "
                  f"saldoendring. Ingenting bokført.")
            return 0.0

        gebyr = self._gebyr_eur(data, pris)
        kost = p["snittpris"] * solgt
        gevinst = netto - kost                      # netto er allerede etter gebyr
        dager = _dager_siden(p.get("apnet"), ts)
        p["mengde"] -= solgt
        if maalvekt is not None:
            p["maalvekt"] = maalvekt
        self._sett_saldo(etter, sym)
        self._logg(ts, sym, "SELG", solgt, netto / solgt, netto + gebyr, gebyr, grunn,
                   {"kostpris": round(kost / solgt, 10),
                    "avkastning_pst": round(gevinst / kost * 100, 3) if kost else "",
                    "gevinst": round(gevinst, 4),
                    "dager": "" if dager is None else round(dager, 2)})
        self._lagre_bok(self.handler[-1])
        print(f"  SOLGT {sym}: {solgt:.8f} for {netto:.2f} EUR netto "
              f"(resultat {gevinst:+.2f} EUR) - {grunn}")
        return netto


def apningsbalanse(pf, priser, saldo=None):
    """Første gang: skriv boka ut fra det som faktisk står på kontoen.

    Dette er det eneste tidspunktet vi lar børsen bestemme innholdet i boka.
    Senere er et avvik mellom de to et varsel, ikke noe vi retter opp.
    """
    s = saldo if saldo is not None else bh.saldo()
    pf.s["kontanter"] = (s.get("EUR", {}).get("tilgjengelig", 0.0)
                         + s.get("EUR", {}).get("i_ordre", 0.0))
    pf.s["posisjoner"] = {}
    for sym, f in s.items():
        if sym == "EUR":
            continue
        marked = f"{sym}-EUR"
        mengde = f.get("tilgjengelig", 0.0) + f.get("i_ordre", 0.0)
        pris = priser.get(marked)
        if not pris or mengde * pris < 1.0:        # støv tar vi ikke inn i boka
            continue
        pf.s["posisjoner"][marked] = {"mengde": mengde, "snittpris": pris,
                                      "maalvekt": 0.0, "apnet": utc_iso()}
    pf.s["startkapital"] = pf.egenkapital(priser)
    pf.s["opprettet"] = utc_iso()
    pf.s["apningsbalanse"] = {"tid": utc_iso(), "egenkapital": pf.s["startkapital"]}
    return pf.s["startkapital"]
