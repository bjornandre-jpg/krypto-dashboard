"""Tester avstemmingen mot oppdiktede saldoer. Rører ikke børsen.

Avstemmingen er sikkerhetsnettet under ekte handel, så den skal testes
med tall vi styrer selv - ikke bare prøves ut i felt.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, ".")
from felles import avstemming
from felles.portefolje import Portefolje

PRISER = {"BTC-EUR": 100_000.0, "ETH-EUR": 3_000.0, "SOL-EUR": 150.0}
FEIL = 0


def pf_med(kontanter, posisjoner, mappe):
    p = Portefolje({"max_per_mynt": 0.1, "max_total": 0.6}, 1000.0, mappe)
    p.s["kontanter"] = kontanter
    p.s["posisjoner"] = {s: {"mengde": m, "snittpris": PRISER[s], "maalvekt": 0.1}
                         for s, m in posisjoner.items()}
    return p


def sjekk(navn, ventet_ok, kontanter, posisjoner, faktisk, ventede_avvik=()):
    global FEIL
    mappe = tempfile.mkdtemp()
    try:
        pf = pf_med(kontanter, posisjoner, mappe)
        ok, r = avstemming.krev(pf, PRISER, faktisk)
        navn_avvik = sorted(a["navn"] for a in r["avvik"])
        stoppfil = avstemming.stoppet(mappe)
        feil = []
        if ok != ventet_ok:
            feil.append(f"ok={ok}, ventet {ventet_ok}")
        if navn_avvik != sorted(ventede_avvik):
            feil.append(f"avvik {navn_avvik}, ventet {sorted(ventede_avvik)}")
        if stoppfil == ok:
            feil.append(f"STOPP-fil {stoppfil} med ok={ok}")
        if not os.path.exists(os.path.join(mappe, avstemming.RAPPORTFIL)):
            feil.append("rapport ikke skrevet")
        if feil:
            FEIL += 1
            print(f"  FEIL  {navn}: {'; '.join(feil)}")
            print(avstemming.tekstrapport(r))
        else:
            print(f"  ok    {navn}")
    finally:
        shutil.rmtree(mappe, ignore_errors=True)


def main():
    print("Avstemming:")

    sjekk("tom konto, tomme bøker", True, 0.0, {}, {})

    sjekk("alt stemmer", True, 500.0, {"BTC-EUR": 0.005},
          {"EUR": {"tilgjengelig": 500.0, "i_ordre": 0.0},
           "BTC": {"tilgjengelig": 0.005, "i_ordre": 0.0}})

    sjekk("penger låst i åpen ordre teller med", True, 500.0, {"BTC-EUR": 0.005},
          {"EUR": {"tilgjengelig": 100.0, "i_ordre": 400.0},
           "BTC": {"tilgjengelig": 0.001, "i_ordre": 0.004}})

    sjekk("gebyravrunding på 0,40 EUR godtas", True, 500.0, {"BTC-EUR": 0.005},
          {"EUR": {"tilgjengelig": 499.60, "i_ordre": 0.0},
           "BTC": {"tilgjengelig": 0.005, "i_ordre": 0.0}})

    sjekk("halv posisjon borte", False, 500.0, {"BTC-EUR": 0.005},
          {"EUR": {"tilgjengelig": 500.0, "i_ordre": 0.0},
           "BTC": {"tilgjengelig": 0.0025, "i_ordre": 0.0}}, ["BTC-EUR"])

    sjekk("kontanter forsvunnet", False, 500.0, {},
          {"EUR": {"tilgjengelig": 300.0, "i_ordre": 0.0}}, ["EUR"])

    sjekk("posisjon vi tror vi har finnes ikke", False, 0.0, {"ETH-EUR": 0.3},
          {"EUR": {"tilgjengelig": 0.0, "i_ordre": 0.0}}, ["ETH-EUR"])

    sjekk("ubokført beholdning av verdi", False, 0.0, {},
          {"SOL": {"tilgjengelig": 2.0, "i_ordre": 0.0}}, ["SOL-EUR"])

    sjekk("støv etter salg godtas", True, 0.0, {},
          {"SOL": {"tilgjengelig": 0.004, "i_ordre": 0.0}})

    sjekk("flere avvik samtidig", False, 500.0, {"BTC-EUR": 0.005, "ETH-EUR": 0.3},
          {"EUR": {"tilgjengelig": 200.0, "i_ordre": 0.0},
           "BTC": {"tilgjengelig": 0.005, "i_ordre": 0.0}},
          ["EUR", "ETH-EUR"])

    # store porteføljer: toleransen skal følge verdien, ikke være fast
    sjekk("0,3 % avvik på stor post godtas", True, 0.0, {"BTC-EUR": 0.5},
          {"BTC": {"tilgjengelig": 0.4985, "i_ordre": 0.0}})
    sjekk("1 % avvik på stor post fanges", False, 0.0, {"BTC-EUR": 0.5},
          {"BTC": {"tilgjengelig": 0.495, "i_ordre": 0.0}}, ["BTC-EUR"])

    print(f"\n{'ALLE TESTER OK' if not FEIL else str(FEIL) + ' TEST(ER) FEILET'}")
    return 1 if FEIL else 0


if __name__ == "__main__":
    sys.exit(main())
