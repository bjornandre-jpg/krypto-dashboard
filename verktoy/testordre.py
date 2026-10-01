"""Legger ÉN liten testordre på Bitvavo, og selger den tilbake hvis du ber om det.

Hensikten er å bekrefte at ordrelegging faktisk fylles fra GitHub sine servere,
før noe system får lov til å handle automatisk.

Sperrene:
- Ordren sendes bare når miljøvariabelen BITVAVO_EKTE er "ja". Den settes fra
  et felt du må fylle ut selv når du starter arbeidsflyten, ikke fra koden.
- Beløpet må ligge mellom 5 og 50 euro (felles/bitvavo_handel.MAKS_ORDRE).
- Skriptet handler bare det ene markedet du oppgir, og bare én gang.
"""
import os
import sys
import time

sys.path.insert(0, ".")
from felles import bitvavo, bitvavo_handel as bh


def vis_saldo(merkelapp):
    s = bh.saldo()
    eur = s.get("EUR", {}).get("tilgjengelig", 0.0)
    print(f"  {merkelapp}: EUR {eur:.2f}" + "".join(
        f" · {k} {v['tilgjengelig']:.8f}" for k, v in sorted(s.items()) if k != "EUR"))
    return s


def main():
    market = os.environ.get("MARKED", "BTC-EUR").strip().upper()
    belop = float(os.environ.get("BELOP", "5"))
    selg_tilbake = os.environ.get("SELG_TILBAKE", "").strip().lower() == "ja"

    print(f"Marked {market} · beløp {belop:.2f} EUR · "
          f"ekte handel {'PÅ' if bh.ekte_handel() else 'AV (tørrkjøring)'}")

    info = bh.markedsinfo().get(market)
    if not info:
        print(f"FEIL: {market} finnes ikke som EUR-marked på Bitvavo")
        return 1
    print(f"  minstebeløp {info['min_eur']:.2f} EUR · "
          f"{info['mengde_desimaler']} desimaler på mengde")
    sp = bitvavo.spreads().get(market)
    print(f"  spread akkurat nå: {sp:.3f} %" if sp is not None else "  spread ukjent")

    print("Saldo før:")
    for_ = vis_saldo("før")
    base = market.split("-")[0]
    mengde_for = for_.get(base, {}).get("tilgjengelig", 0.0)

    presisjon = {"mengde": info["mengde_desimaler"], "notional": info["notional_desimaler"]}
    status, data = bh.markedsordre(market, "buy", belop_eur=belop,
                                   presisjon=presisjon, grunn="testordre")
    print(f"KJØP: {status}")
    if status == "avvist":
        print(f"  {data}")
        return 1
    if status == "tørrkjøring":
        print(f"  ville sendt: {data['ville_sendt']}")
        print("\nIngen ekte ordre lagt. Sett bekreftelsesfeltet for å handle på ekte.")
        return 0

    print(f"  ordreId {data.get('orderId')} · status {data.get('status')}")
    time.sleep(3)
    o = bh.ordre_status(market, data["orderId"])
    fylt = float(o.get("filledAmount") or 0)
    betalt = float(o.get("filledAmountQuote") or 0)
    gebyr = float(o.get("feePaid") or 0)
    print(f"  fylt {fylt:.8f} {base} for {betalt:.2f} EUR · gebyr {gebyr:.4f} EUR "
          f"({gebyr / betalt * 100:.3f} %)" if betalt else "  ikke fylt ennå")
    if betalt:
        print(f"  snittkurs {betalt / fylt:.2f} EUR")

    etter = vis_saldo("etter kjøp")
    kjopt = etter.get(base, {}).get("tilgjengelig", 0.0) - mengde_for
    print(f"  endring i beholdning: {kjopt:+.8f} {base}")

    if selg_tilbake and kjopt > 0:
        print("SALG tilbake:")
        status, data = bh.markedsordre(market, "sell", mengde=kjopt,
                                       presisjon=presisjon, grunn="selger testordren tilbake")
        print(f"  {status}")
        if status == "sendt":
            time.sleep(3)
            o = bh.ordre_status(market, data["orderId"])
            fikk = float(o.get("filledAmountQuote") or 0)
            g2 = float(o.get("feePaid") or 0)
            print(f"  fikk {fikk:.2f} EUR · gebyr {g2:.4f} EUR")
            print(f"  rundtur kostet {betalt - fikk + 0:.4f} EUR av {betalt:.2f} "
                  f"({(betalt - fikk) / betalt * 100:.2f} %)" if betalt else "")
        vis_saldo("etter salg")

    print("\nFerdig. Ordrelegging mot Bitvavo virker fra GitHub.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
