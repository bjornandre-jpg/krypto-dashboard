"""Tester ekte-penger-porteføljen mot en falsk børs. Rører ingenting ekte.

Dette er koden som flytter penger. Den skal testes med tall vi styrer selv,
særlig på de stedene der en feil koster noe: avrunding av salgsmengde,
gebyr i feil valuta, og at tørrkjøring virkelig lar boka være i fred.
"""
import shutil
import sys
import tempfile

sys.path.insert(0, ".")
from felles import ekte_portefolje as ep

FEIL = []


class FalskBors:
    """Erstatter felles.bitvavo_handel. Fyller alt umiddelbart til `kurs`."""
    MIN_ORDRE, MAKS_ORDRE = 5.0, 50.0

    def __init__(self, kurs=100.0, eur=100.0, beholdning=None, gebyr=0.004,
                 gebyr_i_base=False, ekte=True):
        self.kurs, self.gebyr, self.gebyr_i_base, self._ekte = kurs, gebyr, gebyr_i_base, ekte
        self.konto = {"EUR": eur, **(beholdning or {})}
        self.sendte, self.ordrer, self._n = [], {}, 0

    def ekte_handel(self):
        return self._ekte

    def markedsordre(self, market, side, belop_eur=None, mengde=None,
                     presisjon=None, grunn="", operator_id=None):
        if operator_id is None or not isinstance(operator_id, int):
            FEIL.append(f"ordre uten gyldig operatorId: {operator_id!r}")
        if not self._ekte:
            return "tørrkjøring", {"ville_sendt": {"market": market, "side": side}}
        base = market.split("-")[0]
        self._n += 1
        oid = f"o{self._n}"
        if side == "buy":
            if belop_eur > self.MAKS_ORDRE:
                FEIL.append(f"ordre over grensen slapp gjennom: {belop_eur}")
            if belop_eur > self.konto["EUR"] + 1e-9:
                FEIL.append(f"kjøpte for {belop_eur} med bare {self.konto['EUR']} EUR")
            gebyr = belop_eur * self.gebyr
            kvote = belop_eur - gebyr
            fylt = kvote / self.kurs
            self.konto["EUR"] -= belop_eur
            if self.gebyr_i_base:
                # børsen tar gebyret i krypto i stedet: vi får mindre, men
                # bruker hele beløpet i euro
                fylt = belop_eur / self.kurs
                kvote = belop_eur
                gebyr = fylt * self.gebyr
                self.konto["EUR"] = self.konto["EUR"] + belop_eur - belop_eur
                self.konto[base] = self.konto.get(base, 0.0) + fylt - gebyr
                self.ordrer[oid] = {"status": "filled", "filledAmount": str(fylt),
                                    "filledAmountQuote": str(kvote),
                                    "feePaid": str(gebyr), "feeCurrency": base}
                return "sendt", {"orderId": oid}
            self.konto[base] = self.konto.get(base, 0.0) + fylt
            self.ordrer[oid] = {"status": "filled", "filledAmount": str(fylt),
                                "filledAmountQuote": str(kvote),
                                "feePaid": str(gebyr), "feeCurrency": "EUR"}
            return "sendt", {"orderId": oid}

        if mengde > self.konto.get(base, 0.0) + 1e-12:
            FEIL.append(f"solgte {mengde} {base} med bare {self.konto.get(base, 0.0)}")
            return "avvist", {"errorCode": 216, "error": "insufficient balance"}
        brutto = mengde * self.kurs
        gebyr = brutto * self.gebyr
        self.konto[base] -= mengde
        self.konto["EUR"] += brutto - gebyr
        self.ordrer[oid] = {"status": "filled", "filledAmount": str(mengde),
                            "filledAmountQuote": str(brutto),
                            "feePaid": str(gebyr), "feeCurrency": "EUR"}
        return "sendt", {"orderId": oid}

    def ordre_status(self, market, order_id):
        return self.ordrer[order_id]

    def saldo(self):
        return {k: {"tilgjengelig": v, "i_ordre": 0.0}
                for k, v in self.konto.items() if v}


def ny_pf(bors, mappe, posisjoner=None, kontanter=None):
    ep.bh = bors
    pf = ep.EktePortefolje({"max_per_mynt": 0.5, "max_total": 1.0}, mappe, 13,
                           {"X-EUR": {"mengde": 4, "notional": 2}})
    pf.s["kontanter"] = bors.konto["EUR"] if kontanter is None else kontanter
    pf.s["posisjoner"] = posisjoner or {}
    return pf


def kjor(navn, fn):
    mappe = tempfile.mkdtemp()
    f0 = len(FEIL)
    try:
        fn(mappe)
    except Exception as e:  # noqa: BLE001
        FEIL.append(f"{navn}: unntak {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(mappe, ignore_errors=True)
    print(("  ok    " if len(FEIL) == f0 else "  FEIL  ") + navn)
    for f in FEIL[f0:]:
        print(f"          {f}")


def sjekk(vilkar, melding):
    if not vilkar:
        FEIL.append(melding)


def main():
    print("Ekte-penger-portefølje:")

    def torrkjoring(m):
        b = FalskBors(ekte=False)
        pf = ny_pf(b, m)
        sjekk(pf.kjop("X-EUR", 20.0, 100.0, "signal") == 0.0, "tørrkjøring returnerte beløp")
        sjekk(not b.sendte and not b.ordrer, "tørrkjøring sendte ordre")
        sjekk(pf.s["posisjoner"] == {}, "tørrkjøring endret boka")
        sjekk(pf.kontanter == 100.0, "tørrkjøring endret kontanter")
        sjekk(len(pf.planlagt) == 1 and pf.planlagt[0]["side"] == "KJØP",
              "tørrkjøring loggførte ikke planlagt ordre")
    kjor("tørrkjøring rører verken børs eller bok", torrkjoring)

    def kjop_med_gebyr_i_euro(m):
        b = FalskBors(kurs=100.0, eur=100.0, gebyr=0.004)
        pf = ny_pf(b, m)
        brukt = pf.kjop("X-EUR", 20.0, 100.0, "signal", maalvekt=0.2)
        p = pf.pos("X-EUR")
        # 20 EUR, 0,4 % gebyr -> 19,92 kjøpte 0,1992 enheter, kostpris 20/0,1992
        sjekk(abs(p["mengde"] - 0.1992) < 1e-9, f"mengde {p['mengde']}")
        sjekk(abs(p["snittpris"] - 20.0 / 0.1992) < 1e-6, f"snittpris {p['snittpris']}")
        sjekk(abs(brukt - 20.0) < 1e-9, f"brukt {brukt}")
        sjekk(abs(pf.kontanter - 80.0) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(p["maalvekt"] == 0.2, "målvekt ikke satt")
        sjekk(p.get("apnet"), "åpningstidspunkt mangler")
        sjekk(pf.handler[0]["side"] == "KJØP", "handel ikke loggført")
    kjor("kjøp: kostpris inkluderer gebyret", kjop_med_gebyr_i_euro)

    def kjop_med_gebyr_i_krypto(m):
        b = FalskBors(kurs=100.0, eur=100.0, gebyr=0.004, gebyr_i_base=True)
        pf = ny_pf(b, m)
        pf.kjop("X-EUR", 20.0, 100.0, "signal")
        p = pf.pos("X-EUR")
        # 20 EUR -> 0,2 enheter, gebyr 0,0008 enheter trukket i krypto
        sjekk(abs(p["mengde"] - 0.1992) < 1e-9, f"mengde {p['mengde']}")
        sjekk(abs(p["snittpris"] - 20.0 / 0.1992) < 1e-6, f"snittpris {p['snittpris']}")
    kjor("kjøp: gebyr trukket i krypto gir samme kostpris", kjop_med_gebyr_i_krypto)

    def tak_pa_ordre(m):
        b = FalskBors(kurs=100.0, eur=1000.0)
        pf = ny_pf(b, m)
        pf.kjop("X-EUR", 400.0, 100.0, "signal")
        sjekk(abs(pf.handler[0]["belop"] - 50.0) < 0.01,
              f"ordre ikke kuttet til 50 EUR: {pf.handler[0]['belop']}")
    kjor("ordre over 50 EUR kuttes ned", tak_pa_ordre)

    def for_lite(m):
        b = FalskBors(kurs=100.0, eur=100.0)
        pf = ny_pf(b, m)
        sjekk(pf.kjop("X-EUR", 4.0, 100.0, "signal") == 0.0, "kjøpte under minstebeløpet")
        sjekk(not b.ordrer, "sendte ordre under minstebeløpet")
    kjor("kjøp under 5 EUR sendes ikke", for_lite)

    def salg_rundes_ned(m):
        b = FalskBors(kurs=100.0, eur=0.0, beholdning={"X": 0.19999999})
        pf = ny_pf(b, m, {"X-EUR": {"mengde": 0.19999999, "snittpris": 90.0,
                                    "maalvekt": 0.2, "apnet": "2026-09-01T00:00:00Z"}},
                   kontanter=0.0)
        pf.selg("X-EUR", 0.19999999, 100.0, "signal")
        # 4 desimaler: 0,1999 selges, resten blir liggende
        sjekk(abs(float(pf.handler[0]["mengde"]) - 0.1999) < 1e-9,
              f"solgte {pf.handler[0]['mengde']}, ventet 0.1999")
        sjekk(not FEIL or "solgte" not in FEIL[-1], "solgte mer enn vi eide")
        sjekk(pf.handler[0]["avkastning_pst"] > 0, "resultat ikke regnet ut")
    kjor("salg rundes ned til børsens desimaler", salg_rundes_ned)

    def rest_under_minsteordre(m):
        b = FalskBors(kurs=100.0, eur=0.0, beholdning={"X": 0.03})
        pf = ny_pf(b, m, {"X-EUR": {"mengde": 0.03, "snittpris": 90.0, "maalvekt": 0.2}},
                   kontanter=0.0)
        sjekk(pf.selg("X-EUR", 0.03, 100.0, "signal") == 0.0,
              "forsøkte å selge 3 EUR, under minsteordren")
        sjekk(not b.ordrer, "sendte salgsordre under minstebeløpet")
    kjor("rest under 5 EUR forsøkes ikke solgt", rest_under_minsteordre)

    def apning(m):
        b = FalskBors(kurs=100.0, eur=103.91, beholdning={"X": 0.5, "STOV": 0.0001})
        pf = ny_pf(b, m, kontanter=0.0)
        eq = ep.apningsbalanse(pf, {"X-EUR": 100.0, "STOV-EUR": 1.0}, b.saldo())
        sjekk(abs(pf.kontanter - 103.91) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(list(pf.s["posisjoner"]) == ["X-EUR"],
              f"posisjoner {list(pf.s['posisjoner'])} (støv skal utelates)")
        sjekk(abs(eq - 153.91) < 1e-9, f"egenkapital {eq}")
    kjor("åpningsbalanse tar kontoen som den er, uten støv", apning)

    print(f"\n{'ALLE TESTER OK' if not FEIL else str(len(FEIL)) + ' FEIL'}")
    return 1 if FEIL else 0


if __name__ == "__main__":
    sys.exit(main())
