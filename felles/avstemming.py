"""Avstemming: stemmer våre egne bøker med det Bitvavo faktisk viser?

Dette er sikkerhetsnettet under ekte handel. Et handelssystem som tror det
eier 0,004 BTC mens børsen viser 0,002 vil regne feil på alt etterpå:
posisjonsstørrelser, stop-loss, avkastning. Derfor leser systemet faktisk
saldo ved hver kjøring, sammenligner med egne tall, og nekter å handle
videre hvis det ikke stemmer.

Reglen er streng med vilje: ved avvik stopper vi og varsler. Vi retter
ALDRI bøkene automatisk etter børsen - hvis tallene spriker, har noe skjedd
vi ikke forstår, og da skal et menneske se på det før neste ordre.

Avvik som ikke betyr noe:
- støv (små rester etter salg) under `stovgrense` euro
- forskjeller under toleransen, som dekker avrunding og gebyr i siste ordre

Bruk:
    rapport = avstemming.avstem(pf, priser)
    if not rapport["ok"]:
        avstemming.stopp(pf.mappe, rapport)   # skriver STOPP-fil
        return 1                              # ingen handel denne kjøringen
"""
import json
import os

from .portefolje import utc_iso

TOLERANSE_EUR = 1.00       # absolutt slakk per linje
TOLERANSE_PST = 0.005      # eller 0,5 % av linjens verdi, det største av de to
STOVGRENSE = 1.00          # beholdning verdt under dette regnes som støv
STOPPFIL = "STOPP"
RAPPORTFIL = "avstemming.json"


def _grense(verdi_eur):
    return max(TOLERANSE_EUR, abs(verdi_eur) * TOLERANSE_PST)


def avstem(pf, priser, faktisk=None, stovgrense=STOVGRENSE):
    """Sammenligner porteføljen med faktisk saldo på Bitvavo.

    `faktisk` kan sendes inn (for tester); ellers hentes den fra børsen.
    Returnerer en rapport. `rapport["ok"]` er False hvis noe må undersøkes.
    """
    if faktisk is None:
        from . import bitvavo_handel
        faktisk = bitvavo_handel.saldo()

    linjer, avvik = [], []

    def legg_til(navn, bokfort, faktisk_mengde, pris, merknad=""):
        diff = faktisk_mengde - bokfort
        diff_eur = diff * pris
        grense = _grense(max(abs(bokfort), abs(faktisk_mengde)) * pris)
        stov = abs(faktisk_mengde * pris) < stovgrense and bokfort == 0
        ok = abs(diff_eur) <= grense or stov
        rad = {"navn": navn, "bokfort": bokfort, "faktisk": faktisk_mengde,
               "differanse": diff, "differanse_eur": round(diff_eur, 4),
               "grense_eur": round(grense, 4), "ok": ok,
               "merknad": "støv" if stov else merknad}
        linjer.append(rad)
        if not ok:
            avvik.append(rad)

    # 1. kontanter
    legg_til("EUR", pf.kontanter,
             faktisk.get("EUR", {}).get("tilgjengelig", 0.0)
             + faktisk.get("EUR", {}).get("i_ordre", 0.0), 1.0)

    # 2. hver posisjon vi mener å ha
    sett = set()
    for marked, p in sorted(pf.s["posisjoner"].items()):
        base = marked.split("-")[0]
        sett.add(base)
        f = faktisk.get(base, {})
        legg_til(marked, p["mengde"],
                 f.get("tilgjengelig", 0.0) + f.get("i_ordre", 0.0),
                 priser.get(marked, p["snittpris"]))

    # 3. beholdning børsen har som vi ikke har bokført
    for sym, f in sorted(faktisk.items()):
        if sym == "EUR" or sym in sett:
            continue
        mengde = f.get("tilgjengelig", 0.0) + f.get("i_ordre", 0.0)
        pris = priser.get(f"{sym}-EUR", 0.0)
        legg_til(f"{sym}-EUR", 0.0, mengde, pris,
                 "ikke bokført hos oss" if pris else "ukjent pris, ikke bokført")

    bokfort_eq = pf.egenkapital(priser)
    faktisk_eq = sum(
        (f.get("tilgjengelig", 0.0) + f.get("i_ordre", 0.0))
        * (1.0 if sym == "EUR" else priser.get(f"{sym}-EUR", 0.0))
        for sym, f in faktisk.items())

    return {"tid": utc_iso(), "ok": not avvik,
            "bokfort_egenkapital": round(bokfort_eq, 4),
            "faktisk_egenkapital": round(faktisk_eq, 4),
            "differanse_eur": round(faktisk_eq - bokfort_eq, 4),
            "linjer": linjer, "avvik": avvik}


def skriv(mappe, rapport):
    """Lagrer siste rapport, slik at dashbordet og vi selv kan se den."""
    if not mappe:
        return
    os.makedirs(mappe, exist_ok=True)
    with open(os.path.join(mappe, RAPPORTFIL), "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=1)


def stopp(mappe, rapport):
    """Skriver STOPP-fila, som slår av all handel til et menneske fjerner den.

    Samme fil som kill-switchen systemene allerede leser ved oppstart.
    """
    skriv(mappe, rapport)
    if not mappe:
        return
    tekst = [f"Avstemming feilet {rapport['tid']}",
             f"Bokført egenkapital {rapport['bokfort_egenkapital']:.2f} EUR, "
             f"faktisk {rapport['faktisk_egenkapital']:.2f} EUR "
             f"({rapport['differanse_eur']:+.2f})", "", "Avvik:"]
    for a in rapport["avvik"]:
        tekst.append(f"  {a['navn']}: bokført {a['bokfort']:.8f}, "
                     f"faktisk {a['faktisk']:.8f} "
                     f"({a['differanse_eur']:+.2f} EUR, grense "
                     f"{a['grense_eur']:.2f}) {a['merknad']}")
    tekst += ["", "Ingen handel før dette er forstått og fila slettet."]
    with open(os.path.join(mappe, STOPPFIL), "w", encoding="utf-8") as f:
        f.write("\n".join(tekst) + "\n")


def stoppet(mappe):
    return bool(mappe) and os.path.exists(os.path.join(mappe, STOPPFIL))


def krev(pf, priser, faktisk=None):
    """Avstemmer, og returnerer (ok, rapport). Stopper systemet ved avvik.

    Dette er inngangen handelssystemene skal bruke: er svaret False, skal
    kjøringen avsluttes uten en eneste ordre.
    """
    rapport = avstem(pf, priser, faktisk)
    if rapport["ok"]:
        skriv(pf.mappe, rapport)
    else:
        stopp(pf.mappe, rapport)
    return rapport["ok"], rapport


def tekstrapport(rapport):
    linjer = [f"Avstemming {rapport['tid']}: "
              f"{'OK' if rapport['ok'] else 'AVVIK - HANDEL STOPPET'}",
              f"  bokført {rapport['bokfort_egenkapital']:.2f} EUR · "
              f"faktisk {rapport['faktisk_egenkapital']:.2f} EUR · "
              f"differanse {rapport['differanse_eur']:+.2f} EUR"]
    for r in rapport["linjer"]:
        merke = "ok " if r["ok"] else "AVVIK"
        linjer.append(f"  {merke} {r['navn']:10s} bokført {r['bokfort']:.8f}  "
                      f"faktisk {r['faktisk']:.8f}  "
                      f"{r['differanse_eur']:+.2f} EUR"
                      + (f"  ({r['merknad']})" if r["merknad"] else ""))
    return "\n".join(linjer)
