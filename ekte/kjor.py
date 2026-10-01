"""Krypto13 med EKTE penger på Bitvavo.

Samme mynter, samme signaler, samme regler som papirsystemet i system1/ -
signalkoden importeres derfra, slik at de to ikke kan skli fra hverandre.
Forskjellen er at kjøp og salg går til børsen i stedet for til en tenkt bok.

Rekkefølgen i hver kjøring:
  1. Er STOPP-fila satt? Da gjør vi ingenting.
  2. Avstem boka mot faktisk saldo. Avvik -> STOPP, og ingen handel.
  3. Regn ut signaler på siste lukkede dagscandle.
  4. Handle de myntene som har fått en ny, bekreftet beslutning.

TØRRKJØRING ER STANDARD. Uten BITVAVO_EKTE=ja skriver kjøringen ut hvilke
ordrer den ville lagt, og rører verken børsen eller boka.

Om beløpet: Bitvavos minsteordre er 5 euro. Med en konto på rundt 100 euro
blir en full posisjon 5-10 euro, og svake signaler gir målposisjoner under
minstebeløpet. De blir da stående uten kjøp. Systemet eier altså færre og
sterkere posisjoner enn papirversjonen med 1000 euro. Det er en reell
forskjell mellom de to, og grunnen til at papirsystemet fortsetter å gå ved
siden av som fasit på hva strategien egentlig gjør.
"""
import json
import os
import sys
from datetime import datetime, timezone

from felles import avstemming, bitvavo_handel as bh, dashboard
from felles.ekte_portefolje import EktePortefolje, apningsbalanse
from felles.portefolje import vurder_mynt, lagre, utc_iso
from system1.kjor import MYNTER, markedsbilde, mynt_signal, ny_dag_og_bekreftelse

MAPPE = os.path.join("state", "ekte")
CFG = {"max_per_mynt": 0.10, "max_total": 0.60}
OPERATOR = bh.OPERATOR["krypto13"]


def main():
    ekte = bh.ekte_handel()
    print(f"Krypto13 EKTE - {'HANDLER PÅ EKTE' if ekte else 'tørrkjøring'}")

    if avstemming.stoppet(MAPPE):
        print("STOPP-fila er satt. Ingen handel før den er fjernet manuelt.")
        print(open(os.path.join(MAPPE, avstemming.STOPPFIL), encoding="utf-8").read())
        return 1

    mb = markedsbilde()
    priser = mb["priser"]
    info = bh.markedsinfo()
    presisjon = {m: {"mengde": v["mengde_desimaler"], "notional": v["notional_desimaler"]}
                 for m, v in info.items()}
    pf = EktePortefolje(CFG, MAPPE, OPERATOR, presisjon)

    forst = not os.path.exists(os.path.join(MAPPE, "portefolje.json"))
    if forst:
        eq0 = apningsbalanse(pf, priser)
        print(f"Åpningsbalanse skrevet: {eq0:.2f} EUR "
              f"({len(pf.s['posisjoner'])} posisjoner fra kontoen)")
    else:
        ok, rapport = avstemming.krev(pf, priser)
        print(avstemming.tekstrapport(rapport))
        if not ok:
            print("\nBoka stemmer ikke med børsen. STOPP skrevet, ingen ordrer sendt.")
            return 1

    eq = pf.egenkapital(priser)
    pf.start_dag(datetime.now(timezone.utc).strftime("%Y-%m-%d"), eq)
    print(f"Egenkapital {eq:.2f} EUR · kontanter {pf.kontanter:.2f} · "
          f"{len(pf.s['posisjoner'])} posisjoner")

    bfil = os.path.join(MAPPE, "beslutninger.json")
    forrige = json.load(open(bfil, encoding="utf-8")) if os.path.exists(bfil) else {}

    signaler, logg, nye = [], [], {}
    n_dager = 0
    for s in MYNTER:
        if s not in priser:
            print(f"ADVARSEL: mangler pris for {s}")
            continue
        sig = mynt_signal(s, mb)
        ny_dag, bekreftet = ny_dag_og_bekreftelse(forrige.get(s), sig)
        handling = ""
        if ny_dag:
            n_dager += 1
            handling = vurder_mynt(pf, s, priser, eq, sig["beslutning"], sig["score"],
                                   bekreftet, True)
            nye[s] = {"ts": sig["ts"], "beslutning": sig["beslutning"]}
        else:
            nye[s] = forrige.get(s) or {"ts": sig["ts"], "beslutning": sig["beslutning"]}

        signaler.append({"asset": s.replace("-", "/"), "decision": sig["beslutning"],
                         "score": sig["score"], "confirmed": bekreftet,
                         "funding_rate": sig["funding"], "price": priser[s],
                         "ta": sig["ta"]})
        if ny_dag or handling:
            logg.append({"tid": utc_iso(), "mynt": s, "score": round(sig["score"], 4),
                         "beslutning": sig["beslutning"], "bekreftet": bekreftet,
                         "ta": None if sig["ta"] is None else round(sig["ta"], 4),
                         "fg": mb["fg"], "funding": sig["funding"],
                         "pris": priser[s], "handling": handling})

    # Tørrkjøring skal ikke late som den har handlet: hysterese-tilstanden
    # lagres likevel, ellers ville den første ekte kjøringen tro at alle
    # beslutninger var nye og handlet på ubekreftede signaler.
    os.makedirs(MAPPE, exist_ok=True)
    json.dump(nye, open(bfil, "w", encoding="utf-8"))

    if pf.planlagt:
        print(f"\nPlanlagte ordrer ({len(pf.planlagt)}), ikke sendt:")
        for o in pf.planlagt:
            print(f"  {o['side']:5s} {o['mynt']:10s} ~{o['belop']:.2f} EUR  ({o['grunn']})")

    eq = pf.egenkapital(priser)
    lagre(pf, eq, {"signaler.csv": logg} if logg else None)
    dashboard.skriv(pf, priser, signaler, mb["fg"],
                    {"system": "Krypto13 EKTE - Bitvavo", "valuta": "EUR",
                     "ekte": ekte, "news_headlines": mb["titler"]})
    print(f"\nKrypto13 EKTE: egenkapital {eq:.2f} EUR, {len(pf.handler)} handler, "
          f"{len(pf.s['posisjoner'])} posisjoner, {n_dager} nye dagsbeslutninger")
    return 0


if __name__ == "__main__":
    sys.exit(main())
