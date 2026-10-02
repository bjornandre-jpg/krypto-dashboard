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

    # Gebyret er IKKE likt for alle markeder: Bitvavo deler dem i kategorier,
    # og kontonivået over viser bare kategori A. Testordren på BTC-EUR ble
    # belastet 0,40 %, ikke 0,25 %, så dette må leses per marked.
    print("\nFaktisk gebyr per marked (taker er det vi betaler på markedsordre):")
    from system1.kjor import MYNTER
    satser = {}
    for m in MYNTER:
        try:
            g = bh.gebyrer(m)
        except bh.BitvavoFeil as e:
            print(f"      {m:10s} feil: {e}")
            continue
        satser[m] = g["taker"]
        print(f"      {m:10s} taker {g['taker'] * 100:.3f} %  maker {g['maker'] * 100:.3f} %  "
              f"(tier {g['tier']})")
    if satser:
        snitt = sum(satser.values()) / len(satser)
        print(f"      snitt taker {snitt * 100:.3f} %  ->  rundtur {snitt * 200:.3f} %")

    # Oppgitt sats er én ting, belastet gebyr er en annen. Testordren
    # 2026-10-02 ble belastet 0,40 % selv om satsen over sier 0,25 %, så her
    # måler vi hva vi faktisk har betalt på egne handler.
    print("\nMålt gebyr på egne handler:")
    sum_omsetning = sum_gebyr = 0.0
    for m in MYNTER:
        try:
            h = bh.handler(m, 100)
        except bh.BitvavoFeil:
            continue
        for t in h:
            try:
                oms = float(t["amount"]) * float(t["price"])
                g = float(t.get("fee") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if (t.get("feeCurrency") or "EUR").upper() != "EUR":
                g *= float(t["price"])
            sum_omsetning += oms
            sum_gebyr += g
            print(f"      {m:10s} {t.get('side'):4s} {oms:7.2f} EUR  "
                  f"gebyr {g:.4f} = {g / oms * 100:.3f} %")
    if sum_omsetning:
        print(f"      SNITT over {sum_omsetning:.2f} EUR omsatt: "
              f"{sum_gebyr / sum_omsetning * 100:.3f} %")
    else:
        print("      ingen handler ennå")

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
