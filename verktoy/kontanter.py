"""Bokfører innskudd og uttak, og fjerner STOPP hvis alt da stemmer.

Brukes når avstemmingen har stoppet systemet fordi det kom penger inn eller
ut som bøkene ikke visste om. Bare bevegelser Bitvavo selv bekrefter blir
bokført - stemmer det fortsatt ikke etterpå, blir STOPP stående.

Legger INGEN ordrer.
"""
import os
import sys

sys.path.insert(0, ".")
from felles import avstemming, bitvavo, bitvavo_handel as bh, kontantbevegelser
from felles.ekte_portefolje import EktePortefolje
from felles.portefolje import lagre

MAPPE = os.path.join("state", "ekte")
CFG = {"max_per_mynt": 0.10, "max_total": 0.60}


def main():
    if not os.path.exists(os.path.join(MAPPE, "portefolje.json")):
        print("Ingen bok å justere.")
        return 1
    pf = EktePortefolje(CFG, MAPPE, bh.OPERATOR["krypto13"])
    priser = bitvavo.priser()

    print(f"Før:  kontanter {pf.kontanter:.2f} EUR · "
          f"startkapital {pf.s.get('startkapital', 0):.2f} EUR")
    feil = kontantbevegelser.rydd(pf)
    if feil:
        print(f"Angret {len(feil)} bevegelse(r) som skjedde før boka ble åpnet "
              f"og dermed alt lå i åpningsbalansen:")
        for b in feil:
            print(f"  {b['type']:9s} {b['netto']:+9.2f} EUR")
        print(f"      kontanter {pf.kontanter:.2f} EUR · "
              f"startkapital {pf.s.get('startkapital', 0):.2f} EUR")
    inn, ut = kontantbevegelser.hent()
    print(f"Bitvavo melder {len(inn)} innskudd og {len(ut)} uttak totalt.")
    nye = kontantbevegelser.juster(pf, inn, ut)
    print(kontantbevegelser.tekst(nye))
    for b in kontantbevegelser.ubokfort_krypto(pf, inn, ut):
        print(f"  MERK kryptobevegelse som ikke bokføres automatisk: "
              f"{b['symbol']} {b['belop']}")
    print(f"Etter: kontanter {pf.kontanter:.2f} EUR · "
          f"startkapital {pf.s.get('startkapital', 0):.2f} EUR")

    rapport = avstemming.avstem(pf, priser)
    print("\n" + avstemming.tekstrapport(rapport))
    avstemming.skriv(MAPPE, rapport)
    lagre(pf, pf.egenkapital(priser), skriv_handler=False)

    stopp = os.path.join(MAPPE, avstemming.STOPPFIL)
    if rapport["ok"]:
        if os.path.exists(stopp):
            os.remove(stopp)
            print("\nSTOPP-fila fjernet. Neste kjøring handler igjen.")
        else:
            print("\nAlt stemmer.")
        return 0
    print("\nDet stemmer fortsatt ikke. STOPP blir stående - dette må "
          "forstås før systemet får handle.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
