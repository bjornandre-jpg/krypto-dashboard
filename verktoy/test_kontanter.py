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


def pf_med(kontanter, startkapital, mappe, bevegelser=None):
    p = Portefolje({"max_per_mynt": 0.1, "max_total": 0.6}, 0.0, mappe)
    p.s["kontanter"] = kontanter
    p.s["startkapital"] = startkapital
    p.s["posisjoner"] = {}
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
        nye = kb.juster(pf, kb._ferdige([b(1, 10)]), [])
        sjekk(len(nye) == 1, f"bokførte {len(nye)} bevegelser")
        sjekk(abs(pf.kontanter - 82.79) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(abs(pf.s["startkapital"] - 113.91) < 1e-9,
              f"startkapital {pf.s['startkapital']} - innskudd teller som gevinst!")
    kjor("innskudd øker både kontanter og startkapital", innskudd)

    def uttak(m):
        pf = pf_med(100.0, 100.0, m)
        kb.juster(pf, [], kb._ferdige([b(1, 20, gebyr=0.5)]))
        sjekk(abs(pf.kontanter - 79.5) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(abs(pf.s["startkapital"] - 79.5) < 1e-9,
              f"startkapital {pf.s['startkapital']}")
    kjor("uttak trekker fra begge, med gebyr", uttak)

    def gebyr(m):
        pf = pf_med(0.0, 0.0, m)
        kb.juster(pf, kb._ferdige([b(1, 100, gebyr=2)]), [])
        sjekk(abs(pf.kontanter - 98.0) < 1e-9, f"kontanter {pf.kontanter}")
    kjor("innskuddsgebyr trekkes fra", gebyr)

    def to_ganger(m):
        pf = pf_med(0.0, 0.0, m)
        inn = kb._ferdige([b(1, 10)])
        kb.juster(pf, inn, [])
        nye = kb.juster(pf, inn, [])          # samme innskudd en gang til
        sjekk(not nye, "bokførte samme innskudd to ganger")
        sjekk(abs(pf.kontanter - 10.0) < 1e-9, f"kontanter {pf.kontanter}")
    kjor("samme innskudd bokføres bare én gang", to_ganger)

    def ventende(m):
        pf = pf_med(0.0, 0.0, m)
        nye = kb.juster(pf, kb._ferdige([b(1, 10, status="awaiting_processing")]), [])
        sjekk(not nye, "bokførte et innskudd som ikke er gjennomført")
        sjekk(pf.kontanter == 0.0, f"kontanter {pf.kontanter}")
    kjor("innskudd som ikke er gjennomført røres ikke", ventende)

    def krypto(m):
        pf = pf_med(0.0, 0.0, m)
        inn = kb._ferdige([b(1, 0.5, symbol="BTC")])
        nye = kb.juster(pf, inn, [])
        sjekk(not nye, "bokførte et kryptoinnskudd automatisk")
        sjekk(len(kb.ubokfort_krypto(pf, inn, [])) == 1,
              "meldte ikke fra om kryptoinnskuddet")
    kjor("kryptoinnskudd bokføres ikke automatisk, men meldes", krypto)

    def flere(m):
        pf = pf_med(50.0, 50.0, m)
        kb.juster(pf, kb._ferdige([b(1, 10), b(2, 20)]), kb._ferdige([b(3, 5)]))
        sjekk(abs(pf.kontanter - 75.0) < 1e-9, f"kontanter {pf.kontanter}")
        sjekk(abs(pf.s["startkapital"] - 75.0) < 1e-9,
              f"startkapital {pf.s['startkapital']}")
        sjekk(len(pf.s["kontantbevegelser"]) == 3,
              f"{len(pf.s['kontantbevegelser'])} bevegelser lagret")
    kjor("flere bevegelser i samme runde", flere)

    print(f"\n{'ALLE TESTER OK' if not FEIL else str(len(FEIL)) + ' FEIL'}")
    return 1 if FEIL else 0


if __name__ == "__main__":
    sys.exit(main())
