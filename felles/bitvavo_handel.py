"""Autentisert tilgang til Bitvavo: saldo og ordrelegging.

Nøklene leses fra miljøvariablene BITVAVO_API_KEY og BITVAVO_API_SECRET, som
settes fra GitHub Secrets. De logges aldri.

SIKKERHET
- Modulen rører aldri uttaksendepunktene. API-nøkkelen har uansett ikke
  uttaksrett, men koden skal heller ikke kunne be om det.
- TØRRKJØRING er på som standard: ordrer regnes ut og logges, men sendes ikke.
  Ekte handel krever at miljøvariabelen BITVAVO_EKTE settes til "ja".
- Hver ordre må under MAKS_ORDRE euro. Det er en bremse mot at en feil i
  signalkoden tømmer kontoen i én handel.

Signeringen følger Bitvavos eget bibliotek:
  streng = tidsstempel_ms + METODE + "/v2" + sti + kompakt_json_body
  signatur = HMAC-SHA256(hemmelighet, streng).hexdigest()
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.bitvavo.com/v2"
VINDU = 10_000          # ms Bitvavo godtar at klokka vår avviker
MIN_ORDRE = 5.0         # euro, Bitvavos minimum på de fleste markeder
MAKS_ORDRE = 50.0       # euro, vår egen bremse


class BitvavoFeil(RuntimeError):
    pass


def _nokler():
    k, s = os.environ.get("BITVAVO_API_KEY"), os.environ.get("BITVAVO_API_SECRET")
    if not k or not s:
        raise BitvavoFeil("BITVAVO_API_KEY/BITVAVO_API_SECRET mangler i miljøet")
    return k, s


def ekte_handel():
    """Sant bare når det er bedt om eksplisitt. Alt annet er tørrkjøring."""
    return os.environ.get("BITVAVO_EKTE", "").strip().lower() == "ja"


def _kall(metode, sti, params=None, body=None, timeout=25):
    nokkel, hemmelighet = _nokler()
    if params:
        sti = sti + "?" + urllib.parse.urlencode(params)
    kropp = json.dumps(body, separators=(",", ":")) if body else ""
    ts = int(time.time() * 1000)
    streng = f"{ts}{metode}/v2{sti}{kropp}"
    sig = hmac.new(hemmelighet.encode(), streng.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        BASE + sti, method=metode,
        data=kropp.encode() if kropp else None,
        headers={"bitvavo-access-key": nokkel, "bitvavo-access-signature": sig,
                 "bitvavo-access-timestamp": str(ts), "bitvavo-access-window": str(VINDU),
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        tekst = e.read().decode(errors="replace")[:300]
        raise BitvavoFeil(f"{metode} {sti} ga HTTP {e.code}: {tekst}") from None
    except Exception as e:  # noqa: BLE001
        raise BitvavoFeil(f"{metode} {sti} feilet: {type(e).__name__} {e}") from None


# ---------- lesing ----------
def saldo():
    """{'EUR': {'available': 123.45, 'inOrder': 0.0}, 'BTC': {...}} - bare det som ikke er null."""
    ut = {}
    for r in _kall("GET", "/balance"):
        try:
            t, i = float(r.get("available") or 0), float(r.get("inOrder") or 0)
        except (TypeError, ValueError):
            continue
        if t or i:
            ut[r["symbol"]] = {"tilgjengelig": t, "i_ordre": i}
    return ut


def konto():
    """Gebyrsats og handelsvolum, nyttig for å bekrefte hvilket trinn vi ligger på."""
    return _kall("GET", "/account")


def ordre_status(market, order_id):
    return _kall("GET", "/order", {"market": market, "orderId": order_id})


def aapne_ordrer(market=None):
    return _kall("GET", "/ordersOpen", {"market": market} if market else None)


# ---------- handel ----------
def _avrund(x, desimaler):
    return f"{x:.{desimaler}f}".rstrip("0").rstrip(".") or "0"


def markedsordre(market, side, belop_eur=None, mengde=None, presisjon=None, grunn=""):
    """Legger en markedsordre. KJØP oppgis i euro, SALG i antall enheter.

    Returnerer (status, data) der status er "sendt", "tørrkjøring" eller "avvist".
    Ordren sendes bare hvis BITVAVO_EKTE=ja.
    """
    if side not in ("buy", "sell"):
        raise BitvavoFeil(f"ugyldig side: {side}")
    body = {"market": market, "side": side, "orderType": "market"}
    if side == "buy":
        if belop_eur is None:
            raise BitvavoFeil("kjøp krever belop_eur")
        if belop_eur < MIN_ORDRE:
            return "avvist", {"grunn": f"{belop_eur:.2f} EUR er under minstebeløpet {MIN_ORDRE} EUR"}
        if belop_eur > MAKS_ORDRE:
            return "avvist", {"grunn": f"{belop_eur:.2f} EUR er over grensen {MAKS_ORDRE} EUR"}
        body["amountQuote"] = _avrund(belop_eur, (presisjon or {}).get("notional", 2))
    else:
        if mengde is None:
            raise BitvavoFeil("salg krever mengde")
        body["amount"] = _avrund(mengde, (presisjon or {}).get("mengde", 8))

    if not ekte_handel():
        return "tørrkjøring", {"ville_sendt": body, "grunn": grunn}
    svar = _kall("POST", "/order", body=body)
    if svar.get("errorCode"):
        return "avvist", svar
    return "sendt", svar


def markedsinfo():
    """{'BTC-EUR': {'min_eur': 5.0, 'mengde_desimaler': 8, 'notional_desimaler': 2}}"""
    from . import bitvavo
    ut = {}
    for m in bitvavo.markeder().values():
        try:
            ut[m["market"]] = {
                "min_eur": float(m.get("minOrderInQuoteAsset") or MIN_ORDRE),
                "mengde_desimaler": int(m.get("quantityDecimals") or 8),
                "notional_desimaler": int(m.get("notionalDecimals") or 2),
            }
        except (TypeError, ValueError):
            pass
    return ut
