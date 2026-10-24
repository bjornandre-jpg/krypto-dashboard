"""Innskudd og uttak: penger inn og ut som IKKE er avkastning.

Bakgrunnen er feilen 2026-10-16. Det kom 10 euro inn på kontoen, avstemmingen
så at bøkene og børsen ikke stemte, skrev STOPP-fila og lot systemet stå i
åtte dager. Den gjorde akkurat det den skulle - den kan ikke vite forskjell
på et innskudd og en feil - men systemet manglet en måte å få vite det på.

Løsningen er ikke å senke terskelen i avstemmingen. Det ville gjort
sikkerhetsnettet verdiløst. Løsningen er å spørre Bitvavo: børsen vet selv
hvilke innskudd og uttak som har skjedd, og bare bevegelser den bekrefter
blir bokført. Et uforklart avvik stopper fortsatt alt.

To tall må justeres, ikke ett:
  kontanter    - pengene finnes nå på kontoen
  startkapital - ellers teller innskuddet som gevinst, og avkastningen lyver

Kryptoinnskudd håndteres ikke automatisk: da må kostprisen bestemmes, og det
er ikke noe en maskin skal gjette på. De stopper systemet, som før.
"""
from . import bitvavo_handel as bh
from .portefolje import utc_iso


def apning_ms(pf):
    """Når boka ble åpnet, i millisekunder.

    Åpningsbalansen tok kontoen som den sto, og den inneholdt allerede
    pengene som var satt inn fram til da. Innskudd FØR dette tidspunktet er
    derfor alt med i boka, og skal aldri bokføres en gang til.
    """
    from datetime import datetime, timezone
    iso = (pf.s.get("apningsbalanse") or {}).get("tid") or pf.s.get("opprettet")
    if not iso:
        return 0
    try:
        d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0
    return int(d.timestamp() * 1000)


def _nokkel(b):
    return f"{b.get('timestamp')}-{b.get('symbol')}-{b.get('amount')}"


def _ferdige(liste):
    ut = []
    for b in liste or []:
        if (b.get("status") or "").lower() not in ("completed", "settled", "success"):
            continue
        try:
            ut.append({"tid": int(b["timestamp"]), "symbol": b["symbol"],
                       "belop": float(b["amount"]), "gebyr": float(b.get("fee") or 0),
                       "nokkel": _nokkel(b)})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(ut, key=lambda x: x["tid"])


def hent():
    """(innskudd, uttak) som er gjennomført, eldste først."""
    return _ferdige(bh.innskudd()), _ferdige(bh.uttak())


def juster(pf, inn=None, ut=None):
    """Bokfører innskudd og uttak som ikke er bokført fra før.

    Returnerer liste over det som ble bokført. Endrer både kontanter og
    startkapital, slik at avkastningen fortsatt måler avkastning.
    """
    if inn is None or ut is None:
        inn, ut = hent()
    sett = {b["nokkel"] for b in pf.s.get("kontantbevegelser", [])}
    grense = apning_ms(pf)
    nye = []

    for b in inn:
        if b["nokkel"] in sett or b["symbol"] != "EUR" or b["tid"] <= grense:
            continue
        netto = b["belop"] - b["gebyr"]
        pf.s["kontanter"] += netto
        pf.s["startkapital"] = pf.s.get("startkapital", 0.0) + netto
        nye.append({**b, "type": "innskudd", "netto": round(netto, 4),
                    "bokfort": utc_iso()})

    for b in ut:
        if b["nokkel"] in sett or b["symbol"] != "EUR" or b["tid"] <= grense:
            continue
        netto = b["belop"] + b["gebyr"]
        pf.s["kontanter"] -= netto
        pf.s["startkapital"] = pf.s.get("startkapital", 0.0) - netto
        nye.append({**b, "type": "uttak", "netto": round(-netto, 4),
                    "bokfort": utc_iso()})

    if nye:
        pf.s.setdefault("kontantbevegelser", []).extend(nye)
    return nye


def rydd(pf):
    """Angrer bevegelser som er bokført selv om de skjedde før åpningen.

    Feilen 2026-10-24: første versjon bokførte hele innskuddshistorikken,
    også de innskuddene som allerede lå inne i åpningsbalansen. Boka trodde
    den hadde 102,90 euro mer enn kontoen faktisk hadde.
    """
    grense = apning_ms(pf)
    beholdt, fjernet = [], []
    for b in pf.s.get("kontantbevegelser", []):
        if b.get("tid", 0) <= grense:
            netto = float(b.get("netto", 0.0))
            pf.s["kontanter"] -= netto
            pf.s["startkapital"] = pf.s.get("startkapital", 0.0) - netto
            fjernet.append(b)
        else:
            beholdt.append(b)
    if fjernet:
        pf.s["kontantbevegelser"] = beholdt
    return fjernet


def ubokfort_krypto(pf, inn=None, ut=None):
    """Kryptoinnskudd og -uttak vi ikke har bokført. Skal stoppe systemet."""
    if inn is None or ut is None:
        inn, ut = hent()
    sett = {b["nokkel"] for b in pf.s.get("kontantbevegelser", [])}
    return [b for b in list(inn) + list(ut)
            if b["symbol"] != "EUR" and b["nokkel"] not in sett]


def tekst(nye):
    if not nye:
        return "Ingen nye innskudd eller uttak."
    rader = [f"Bokført {len(nye)} kontantbevegelse(r):"]
    for b in nye:
        rader.append(f"  {b['type']:9s} {b['netto']:+9.2f} EUR  "
                     f"(gebyr {b['gebyr']:.2f})")
    return "\n".join(rader)
