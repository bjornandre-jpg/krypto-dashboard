"""Bygger ekte-boka opp igjen fra Bitvavo, og fjerner STOPP-fila.

Brukes når boka og børsen har kommet i utakt - typisk fordi en kjøring
krasjet etter at en ordre var lagt, men før den ble bokført.

Kostprisen hentes fra din egen handelshistorikk, ikke fra dagens kurs, slik
at avkastningen fortsatt måles fra det du faktisk betalte. Klarer vi ikke å
dekke hele beholdningen med kjente handler, sies det tydelig fra, og dagens
kurs brukes for resten.

Kjøres manuelt. Legger INGEN ordrer.
"""
import json
import os
import sys

sys.path.insert(0, ".")
from felles import avstemming, bitvavo, bitvavo_handel as bh
from felles.portefolje import utc_iso

MAPPE = os.path.join("state", "ekte")


def _ledger(market):
    """Går gjennom egne handler i tidsrekkefølge og returnerer (mengde, kost, åpnet)."""
    try:
        h = bh.handler(market)
    except bh.BitvavoFeil as e:
        print(f"      klarte ikke hente handler for {market}: {e}")
        return 0.0, 0.0, None
    mengde = kost = 0.0
    apnet = None
    for t in h:
        try:
            a = float(t["amount"])
            p = float(t["price"])
        except (KeyError, TypeError, ValueError):
            continue
        gebyr = 0.0
        try:
            gebyr = float(t.get("fee") or 0)
        except (TypeError, ValueError):
            pass
        i_base = (t.get("feeCurrency") or "EUR").upper() != "EUR"
        tid = t.get("timestamp")
        if t.get("side") == "buy":
            if mengde <= 1e-12:
                apnet = tid
            netto = a - gebyr if i_base else a
            kost += a * p + (0.0 if i_base else gebyr)
            mengde += netto
        else:
            if mengde > 1e-12:
                kost -= kost * min(a, mengde) / mengde      # forholdsmessig
            mengde -= a
            if mengde <= 1e-12:
                mengde, kost, apnet = 0.0, 0.0, None
    return max(mengde, 0.0), max(kost, 0.0), apnet


def main():
    priser = bitvavo.priser()
    saldo = bh.saldo()
    eur = saldo.get("EUR", {}).get("tilgjengelig", 0.0) + saldo.get("EUR", {}).get("i_ordre", 0.0)
    print(f"Faktisk på Bitvavo: {eur:.2f} EUR")

    posisjoner = {}
    for sym, f in sorted(saldo.items()):
        if sym == "EUR":
            continue
        marked = f"{sym}-EUR"
        mengde = f.get("tilgjengelig", 0.0) + f.get("i_ordre", 0.0)
        pris = priser.get(marked)
        if not pris:
            print(f"      {marked}: ingen pris, hoppes over ({mengde})")
            continue
        if mengde * pris < 1.0:
            print(f"      {marked}: {mengde * pris:.2f} EUR regnes som støv")
            continue

        bokfort, kost, apnet = _ledger(marked)
        if bokfort > 0 and abs(bokfort - mengde) / mengde < 0.02:
            snitt = kost / bokfort
            kilde = "egen handelshistorikk"
        else:
            snitt = pris
            kilde = (f"DAGENS KURS - historikken dekket {bokfort:.8f} av "
                     f"{mengde:.8f}")
        posisjoner[marked] = {"mengde": mengde, "snittpris": snitt, "maalvekt": 0.0,
                              "apnet": utc_iso((apnet or 0) / 1000) if apnet else utc_iso()}
        print(f"      {marked}: {mengde:.8f} · kostpris {snitt:.6f} EUR "
              f"({kilde}) · verdi {mengde * pris:.2f} EUR")

    gammel = {}
    fil = os.path.join(MAPPE, "portefolje.json")
    if os.path.exists(fil):
        gammel = json.load(open(fil, encoding="utf-8"))

    bok = {"kontanter": eur, "posisjoner": posisjoner,
           "startkapital": gammel.get("startkapital") or (
               eur + sum(p["mengde"] * priser[m] for m, p in posisjoner.items())),
           "dag": gammel.get("dag", {}),
           "opprettet": gammel.get("opprettet", utc_iso()),
           "apningsbalanse": gammel.get("apningsbalanse"),
           "gjenopprettet": utc_iso()}
    os.makedirs(MAPPE, exist_ok=True)
    with open(fil, "w", encoding="utf-8") as f:
        json.dump(bok, f, ensure_ascii=False, indent=1)

    eq = eur + sum(p["mengde"] * priser[m] for m, p in posisjoner.items())
    print(f"\nBoka skrevet: {eq:.2f} EUR i alt, {len(posisjoner)} posisjoner, "
          f"startkapital {bok['startkapital']:.2f} EUR")

    stopp = os.path.join(MAPPE, avstemming.STOPPFIL)
    if os.path.exists(stopp):
        os.remove(stopp)
        print("STOPP-fila fjernet. Neste kjøring handler igjen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
