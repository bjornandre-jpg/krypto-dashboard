"""Tester bokføring av innskudd og uttak mot oppdiktede data.

Den dyre delen her er ikke å legge til pengene - det er å huske at
startkapitalen må flyttes like mye, ellers framstår et innskudd som gevinst.
"""
import shutil
import sys
import tempfile

sys.path.insert(0, ".")
from felles import kontantbevegelser as kb
from felles.portefolje import Portefolje

FEIL = []


AAPNET = "2026-10-02T00:00:00Z"
AAPNET_MS = 1790899200000          # samme tidspunkt i millisekunder


def pf_med(kontanter, startkapital, mappe, bevegelser=None, aapnet=AAPNET):
    p = Portefolje({"max_per_mynt": 0.1, "max_total": 0.6}, 0.0, mappe)
    p.s["kontanter"] = kontanter
    p.s["startkapital"] = startkapital
    p.s["posisjoner"] = {}
    p.s["opprettet"] = aapnet
    p.s["apningsbalanse"] = {"tid": aapnet}
    if bevegelser:
        p.s["kontantbevegelser"] = bevegelser
    return p


def b(tid, belop, symbol="EUR", gebyr=0.0, status="completed"):
    return {"timestamp": tid, "symbol": symbol, "amount": str(belop),
            "fee": str(gebyr), "status": status}


def sjekk(v, m):
    if not v:
        FEIL.append(m)


def kjor(navn, fn):
    mappe = tempfile.mkdtemp()
    f0 = len(FEIL)
    try:
        fn(mappe)
    except Exception as e:  # noqa: BLE001
        FEIL.append(f"{navn}: {type(e).__name__} {e}")
    finally:
        shutil.rmtree(mappe, ignore_errors=True)
    print(("  ok    " if len(FEIL) == f0 else "  FEIL  ") + navn)
    for f in FEIL[f0:]:
        print(f"          {f}")


def main():
    print("Innskudd og uttak:")

    def innskudd(m):
        pf = pf_med(72.79, 103.91, m)
        nye = kb.juster(pf, kb._ferdige([b(AAPNET_MS+1000, 10)]), [])
        sjekk(len(nye) == 1, f"bokførte {len(nye)} bevegelser")
        sjekk(abs(pf.kontanter - 82.79) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(abs(pf.s["startkapital"] - 113.91) < 1e-9,
              f"startkapital {pf.s['startkapital']} - innskudd teller som gevinst!")
    kjor("innskudd øker både kontanter og startkapital", innskudd)

    def uttak(m):
        pf = pf_med(100.0, 100.0, m)
        kb.juster(pf, [], kb._ferdige([b(AAPNET_MS+1000, 20, gebyr=0.5)]))
        sjekk(abs(pf.kontanter - 79.5) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(abs(pf.s["startkapital"] - 79.5) < 1e-9,
              f"startkapital {pf.s['startkapital']}")
    kjor("uttak trekker fra begge, med gebyr", uttak)

    def gebyr(m):
        pf = pf_med(0.0, 0.0, m)
        kb.juster(pf, kb._ferdige([b(AAPNET_MS+1000, 100, gebyr=2)]), [])
        sjekk(abs(pf.kontanter - 98.0) < 1e-9, f"kontanter {pf.kontanter}")
    kjor("innskuddsgebyr trekkes fra", gebyr)

    def to_ganger(m):
        pf = pf_med(0.0, 0.0, m)
        inn = kb._ferdige([b(AAPNET_MS+1000, 10)])
        kb.juster(pf, inn, [])
        nye = kb.juster(pf, inn, [])          # samme innskudd en gang til
        sjekk(not nye, "bokførte samme innskudd to ganger")
        sjekk(abs(pf.kontanter - 10.0) < 1e-9, f"kontanter {pf.kontanter}")
    kjor("samme innskudd bokføres bare én gang", to_ganger)

    def ventende(m):
        pf = pf_med(0.0, 0.0, m)
        nye = kb.juster(pf, kb._ferdige([b(AAPNET_MS+1000, 10, status="awaiting_processing")]), [])
        sjekk(not nye, "bokførte et innskudd som ikke er gjennomført")
        sjekk(pf.kontanter == 0.0, f"kontanter {pf.kontanter}")
    kjor("innskudd som ikke er gjennomført røres ikke", ventende)

    def krypto(m):
        pf = pf_med(0.0, 0.0, m)
        inn = kb._ferdige([b(AAPNET_MS+1000, 0.5, symbol="BTC")])
        nye = kb.juster(pf, inn, [])
        sjekk(not nye, "bokførte et kryptoinnskudd automatisk")
        sjekk(len(kb.ubokfort_krypto(pf, inn, [])) == 1,
              "meldte ikke fra om kryptoinnskuddet")
    kjor("kryptoinnskudd bokføres ikke automatisk, men meldes", krypto)

    def flere(m):
        pf = pf_med(50.0, 50.0, m)
        kb.juster(pf, kb._ferdige([b(AAPNET_MS+1000, 10), b(AAPNET_MS+2000, 20)]), kb._ferdige([b(AAPNET_MS+3000, 5)]))
        sjekk(abs(pf.kontanter - 75.0) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(abs(pf.s["startkapital"] - 75.0) < 1e-9,
              f"startkapital {pf.s['startkapital']}")
        sjekk(len(pf.s["kontantbevegelser"]) == 3,
              f"{len(pf.s['kontantbevegelser'])} bevegelser lagret")
    kjor("flere bevegelser i samme runde", flere)

    def for_apningen(m):
        """Feilen 2026-10-24: innskudd fra før boka ble åpnet lå allerede i
        åpningsbalansen, og ble bokført en gang til."""
        pf = pf_med(72.79, 103.91, m)
        nye = kb.juster(pf, kb._ferdige([b(AAPNET_MS - 86400000, 97.95),
                                         b(AAPNET_MS - 99999, 4.95),
                                         b(AAPNET_MS + 1000, 10)]), [])
        sjekk(len(nye) == 1, f"bokførte {len(nye)} bevegelser, skulle bokført 1")
        sjekk(abs(pf.kontanter - 82.79) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(abs(pf.s["startkapital"] - 113.91) < 1e-9,
              f"startkapital {pf.s['startkapital']}")
    kjor("innskudd fra før åpningen bokføres ikke", for_apningen)

    def rydding(m):
        """Og hvis de alt er bokført galt, skal de kunne angres."""
        galt = [{"tid": AAPNET_MS - 86400000, "symbol": "EUR", "belop": 97.95,
                 "gebyr": 0.0, "nokkel": "a", "type": "innskudd", "netto": 97.95},
                {"tid": AAPNET_MS - 99999, "symbol": "EUR", "belop": 4.95,
                 "gebyr": 0.0, "nokkel": "b", "type": "innskudd", "netto": 4.95},
                {"tid": AAPNET_MS + 1000, "symbol": "EUR", "belop": 10.0,
                 "gebyr": 0.0, "nokkel": "c", "type": "innskudd", "netto": 10.0}]
        pf = pf_med(185.69, 216.81, m, bevegelser=galt)
        fjernet = kb.rydd(pf)
        sjekk(len(fjernet) == 2, f"angret {len(fjernet)}, skulle angret 2")
        sjekk(abs(pf.kontanter - 82.79) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(abs(pf.s["startkapital"] - 113.91) < 1e-9,
              f"startkapital {pf.s['startkapital']}")
        sjekk(len(pf.s["kontantbevegelser"]) == 1,
              "innskuddet etter åpningen ble også fjernet")
        sjekk(not kb.rydd(pf), "rydding to ganger endret noe mer")
    kjor("ryddingen gjenoppretter nøyaktig dagens situasjon", rydding)

    print(f"\n{'ALLE TESTER OK' if not FEIL else str(len(FEIL)) + ' FEIL'}")
    return 1 if FEIL else 0


if __name__ == "__main__":
    sys.exit(main())
