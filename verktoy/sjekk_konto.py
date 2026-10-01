"""Lesetest mot Bitvavo-kontoen. Legger INGEN ordrer.

Svarer på to spørsmål:
  1. Virker API-nøkkelen?
  2. Slipper Bitvavo autentiserte kall gjennom fra GitHub sine servere?

Kjøres manuelt fra Actions -> "Sjekk Bitvavo-konto".
"""
import sys

sys.path.insert(0, ".")
from felles import bitvavo_handel as bh


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

    print("\nKonklusjon: autentiserte kall til Bitvavo virker herfra.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
