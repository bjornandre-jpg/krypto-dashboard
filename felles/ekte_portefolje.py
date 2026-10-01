"""Portefølje som handler med ekte penger på Bitvavo.

Arver all beslutningslogikk fra papirporteføljen, og bytter bare ut de to
metodene som flytter verdier: kjop() og selg() legger nå faktiske ordrer.
Slik kjører ekte penger gjennom nøyaktig samme regler som papirhandelen,
og en endring i strategien treffer begge.

To prinsipper styrer koden:

1. BØRSEN EIER TALLENE. Etter hver ordre leser vi saldoen på nytt og setter
   kontanter og antall enheter til det Bitvavo faktisk viser. Vi regner oss
   ikke fram til hva vi burde ha - da ville små avvik i gebyr, avrunding og
   delfyll hopet seg opp usett.
2. VÅR BOK EIER KOSTPRISEN. Kostpris, målvekt og åpningsdato finnes ikke på
   børsen, og er vårt ansvar å holde orden på. De regnes ut fra hva ordren
   faktisk ble fylt til, ikke fra prisen vi håpet på.

Tørrkjøring er standard: uten BITVAVO_EKTE=ja regnes ordrene ut og skrives
ut, men sendes ikke, og boka står urørt.
"""
import time

from . import bitvavo_handel as bh
from .portefolje import Portefolje, utc_iso


class EktePortefolje(Portefolje):
    def __init__(self, cfg, mappe, operator_id, presisjon=None, startkapital=0.0):
        super().__init__(cfg, startkapital, mappe)
        self.operator_id = operator_id
        self.presisjon = presisjon or {}
        self.planlagt = []          # ordrer vi ville sendt (tørrkjøring)

    # ---------- hjelpere ----------
    def _pres(self, sym):
        return self.presisjon.get(sym, {"mengde": 8, "notional": 2})

    def _vent_pa_fyll(self, sym, order_id, forsok=12):
        o = {}
        for _ in range(forsok):
            o = bh.ordre_status(sym, order_id)
            if o.get("status") in ("filled", "canceled", "rejected", "expired"):
                return o
            time.sleep(1)
        print(f"  ADVARSEL: {sym} ordre {order_id} er ikke ferdig etter {forsok} s")
        return o

    def _synk_saldo(self, symboler):
        """Setter kontanter og antall enheter til det børsen faktisk viser."""
        s = bh.saldo()
        self.s["kontanter"] = (s.get("EUR", {}).get("tilgjengelig", 0.0)
                               + s.get("EUR", {}).get("i_ordre", 0.0))
        for sym in symboler:
            p = self.pos(sym)
            if not p:
                continue
            f = s.get(sym.split("-")[0], {})
            p["mengde"] = f.get("tilgjengelig", 0.0) + f.get("i_ordre", 0.0)
            if p["mengde"] <= 0:
                del self.s["posisjoner"][sym]

    @staticmethod
    def _fyll_tall(sym, o):
        """(mottatt mengde, kostnad i euro, gebyr i euro) fra et ordresvar."""
        base = sym.split("-")[0]
        fylt = float(o.get("filledAmount") or 0)
        kvote = float(o.get("filledAmountQuote") or 0)
        gebyr = float(o.get("feePaid") or 0)
        # Bitvavo kan trekke gebyret i base- eller kvotevaluta. Står det i base,
        # fikk vi mindre krypto; står det i euro, betalte vi mer euro.
        if (o.get("feeCurrency") or "EUR").upper() == base:
            pris = kvote / fylt if fylt else 0.0
            return fylt - gebyr, kvote, gebyr * pris
        return fylt, kvote + gebyr, gebyr

    # ---------- handel ----------
    def kjop(self, sym, usd, pris, grunn, ts=None, maalvekt=None):
        usd = min(usd, self.kontanter, bh.MAKS_ORDRE)
        if usd < self.cfg["min_handel"] or usd < bh.MIN_ORDRE:
            return 0.0
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

        o = self._vent_pa_fyll(sym, data["orderId"])
        mengde, kost, gebyr = self._fyll_tall(sym, o)
        if mengde <= 0:
            print(f"  {sym}: kjøpsordren ble ikke fylt ({o.get('status')})")
            return 0.0
        snitt = kost / mengde
        p = self.s["posisjoner"].setdefault(sym, {"mengde": 0.0, "snittpris": snitt,
                                                  "maalvekt": 0.0})
        if p["mengde"] <= 0:
            p["apnet"] = utc_iso(ts)
        ny = p["mengde"] + mengde
        p["snittpris"] = (p["mengde"] * p["snittpris"] + kost) / ny
        p["mengde"] = ny
        if maalvekt is not None:
            p["maalvekt"] = maalvekt
        self._logg(ts, sym, "KJØP", mengde, snitt, kost, gebyr, grunn)
        self._synk_saldo([sym])
        print(f"  KJØPT {sym}: {mengde:.8f} for {kost:.2f} EUR "
              f"(kurs {snitt:.6f}, gebyr {gebyr:.4f}) - {grunn}")
        return kost

    def selg(self, sym, mengde, pris, grunn, ts=None, maalvekt=None):
        p = self.pos(sym)
        if not p:
            return 0.0
        mengde = min(mengde, p["mengde"])
        helt_ut = mengde >= p["mengde"] * 0.999
        # rund NED, aldri opp: en ordre på mer enn vi eier blir avvist
        des = self._pres(sym).get("mengde", 8)
        mengde = int(mengde * 10 ** des) / 10 ** des
        if mengde <= 0:
            return 0.0
        if mengde * pris < max(self.cfg["min_handel"], bh.MIN_ORDRE) and not helt_ut:
            return 0.0
        if mengde * pris < bh.MIN_ORDRE:
            print(f"  {sym}: rest verdt {mengde * pris:.2f} EUR er under "
                  f"minsteordren, lar den ligge")
            return 0.0

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

        o = self._vent_pa_fyll(sym, data["orderId"])
        solgt = float(o.get("filledAmount") or 0)
        brutto = float(o.get("filledAmountQuote") or 0)
        gebyr = float(o.get("feePaid") or 0)
        if (o.get("feeCurrency") or "EUR").upper() != "EUR":
            gebyr = gebyr * (brutto / solgt if solgt else 0.0)
        if solgt <= 0:
            print(f"  {sym}: salgsordren ble ikke fylt ({o.get('status')})")
            return 0.0
        kost = p["snittpris"] * solgt
        gevinst = (brutto - gebyr) - kost
        from .portefolje import _dager_siden
        dager = _dager_siden(p.get("apnet"), ts)
        p["mengde"] -= solgt
        if maalvekt is not None:
            p["maalvekt"] = maalvekt
        self._logg(ts, sym, "SELG", solgt, brutto / solgt, brutto, gebyr, grunn,
                   {"kostpris": round(p["snittpris"], 10),
                    "avkastning_pst": round(gevinst / kost * 100, 3) if kost else "",
                    "gevinst": round(gevinst, 4),
                    "dager": "" if dager is None else round(dager, 2)})
        self._synk_saldo([sym])
        print(f"  SOLGT {sym}: {solgt:.8f} for {brutto:.2f} EUR "
              f"(gebyr {gebyr:.4f}, resultat {gevinst:+.2f} EUR) - {grunn}")
        return brutto


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
