"""Lesetest mot Bitvavo-kontoen. Legger INGEN ordrer.

Svarer på tre spørsmål:
  1. Virker API-nøkkelen?
  2. Slipper Bitvavo autentiserte kall gjennom fra GitHub sine servere?
  3. Stemmer børsens tall med bøkene til et ekte-penger-system, hvis det finnes?

Kjøres manuelt fra Actions -> "Sjekk Bitvavo-konto".
"""
import os
import sys

sys.path.insert(0, ".")
from felles import avstemming, bitvavo, bitvavo_handel as bh
from felles.portefolje import Portefolje

EKTE_MAPPE = os.path.join("state", "ekte")


def main():
    print(f"Ekte handel er {'PÅ' if bh.ekte_handel() else 'AV (tørrkjøring)'}")
    try:
        s = bh.saldo()
    except bh.BitvavoFeil as e:
        print(f"FEIL ved saldo: {e}")
        return 1
    print(f"OK  saldo hentet: {len(s)} valuta(er) med beholdning")
    for sym, v in sorted(s.items()):
        print(f"      {sym:6s} tilgjengelig {v['tilgjengelig']:.8f}  i ordre {v['i_ordre']:.8f}")
    if not s:
        print("      (tom konto - det er greit, testen gjelder tilgangen)")

    try:
        k = bh.konto()
        gebyr = k.get("fees", {})
        print(f"OK  gebyrtrinn: maker {gebyr.get('maker')}  taker {gebyr.get('taker')}  "
              f"30-dagers volum {gebyr.get('volume')}")
    except bh.BitvavoFeil as e:
        print(f"ADVARSEL konto: {e}")

    try:
        aapne = bh.aapne_ordrer()
        print(f"OK  åpne ordrer: {len(aapne)}")
    except bh.BitvavoFeil as e:
        print(f"ADVARSEL åpne ordrer: {e}")

    print("\nAvstemming mot ekte-penger-bøkene:")
    if not os.path.exists(os.path.join(EKTE_MAPPE, "portefolje.json")):
        print("      ingen bok åpnet ennå - ingenting å avstemme mot.")
        verdi = 0.0
        if s:
            priser = bitvavo.priser()
            verdi = sum(v["tilgjengelig"] + v["i_ordre"]
                        if sym == "EUR" else
                        (v["tilgjengelig"] + v["i_ordre"]) * priser.get(f"{sym}-EUR", 0.0)
                        for sym, v in s.items())
            print(f"      kontoen er verdt {verdi:.2f} EUR i dag.")
    else:
        pf = Portefolje({"max_per_mynt": 0.1, "max_total": 0.6}, 0.0, EKTE_MAPPE)
        r = avstemming.avstem(pf, bitvavo.priser(), s)
        avstemming.skriv(EKTE_MAPPE, r)      # leser bare, stopper ingenting
        print(avstemming.tekstrapport(r))
        if not r["ok"]:
            print("      NB: dette er en lesetest. Et handelssystem ville stoppet her.")

    print("\nKonklusjon: autentiserte kall til Bitvavo virker herfra.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
