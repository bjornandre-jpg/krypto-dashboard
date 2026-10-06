"""Markedsregime: er kryptomarkedet som helhet i opp- eller nedgang?

Bakgrunn: myntene i universet samvarierer 0,65, og én felles faktor
forklarer 68 % av all bevegelse (se backtest/marked.py). Tretten separate
beslutninger er derfor i stor grad tretten kopier av samme beslutning. Denne
modulen tar den ene beslutningen eksplisitt, og lar den styre hvor mye
kapital som skal være i markedet i det hele tatt.

Fire uavhengige mål, ikke én finjustert terskel. Et enkelt glidende snitt
med riktig vindu kan se strålende ut på historien og være ren tilpasning;
fire mål som må være enige er vanskeligere å overtilpasse, og man ser med én
gang når de er uenige.

  1. TREND     - indeksen over sitt eget glidende snitt
  2. BREDDE    - andelen mynter over sitt eget 50-dagers snitt
  3. VOLATILITET - rolig marked er stigende marked, uroen kommer i fall
  4. BTC-STYRKE - flykter pengene fra altcoins til bitcoin?

Indeksen er LIKEVEKTET. Et snitt av råpriser ville vært ren bitcoin, siden
den koster titusener og CAKE koster to euro.

Alt regnes bakoverskuende: verdien for dag i bruker bare dager til og med i.
Ingen av funksjonene får se framover.
"""
import numpy as np

TREND_VINDU = 100        # dager; naboverdier testes i fase 2
BREDDE_VINDU = 50
BREDDE_GRENSE = 0.50     # over halvparten av myntene i egen opptrend
VOL_KORT, VOL_LANG = 30, 180
BTC_VINDU = 50
MIN_DAGER = 5            # et regime må holde så lenge før eksponeringen endres
TRAPP = [0.0, 0.0, 0.35, 0.70, 1.00]   # indeks = antall mål som peker opp


def _glidende(x, vindu):
    """Glidende snitt som bruker det som finnes i starten, aldri framtiden."""
    ut = np.empty(len(x))
    s = np.cumsum(np.insert(x, 0, 0.0))
    for i in range(len(x)):
        a = max(0, i - vindu + 1)
        ut[i] = (s[i + 1] - s[a]) / (i + 1 - a)
    return ut


def indeks(P):
    """Likevektet indeks: hver mynt normalisert til 1 på første dag."""
    return (P / P[0]).mean(axis=1)


def maal(P, trend_vindu=TREND_VINDU, bredde_vindu=BREDDE_VINDU,
         vol_kort=VOL_KORT, vol_lang=VOL_LANG, btc_vindu=BTC_VINDU, ibtc=0):
    """De fire målene som 0/1 per dag. P er [dager, mynter] med lukkekurser."""
    idx = indeks(P)

    trend = (idx > _glidende(idx, trend_vindu)).astype(int)

    over = np.column_stack([P[:, j] > _glidende(P[:, j], bredde_vindu)
                            for j in range(P.shape[1])])
    bredde = (over.mean(axis=1) > BREDDE_GRENSE).astype(int)

    r = np.diff(np.log(idx), prepend=np.log(idx[0]))
    v2 = _glidende(r ** 2, vol_kort)
    v2_lang = _glidende(r ** 2, vol_lang)
    rolig = (v2 <= v2_lang).astype(int)       # roligere enn normalt = oppgang

    # Stiger bitcoin mot resten, flykter pengene ut av altcoins. Da vil vi ned
    # i eksponering selv om indeksen holder seg oppe.
    forhold = P[:, ibtc] / idx
    btc_ro = (forhold <= _glidende(forhold, btc_vindu)).astype(int)

    return {"trend": trend, "bredde": bredde, "rolig": rolig, "btc_ro": btc_ro}


def eksponering(P, min_dager=MIN_DAGER, trapp=None, **kw):
    """Andel av kapitalen som skal være i markedet, per dag.

    Et nytt regime må holde `min_dager` på rad før eksponeringen endres.
    Uten den bremsen vipper filteret fram og tilbake og spiser seg selv opp
    i gebyr og spread.
    """
    trapp = trapp or TRAPP
    m = maal(P, **kw)
    poeng = sum(m.values())
    ut = np.empty(len(poeng))
    naa = poeng[0]
    teller = 0
    for i, p in enumerate(poeng):
        if p == naa:
            teller = 0
        else:
            teller += 1
            if teller >= min_dager:
                naa, teller = p, 0
        ut[i] = trapp[naa]
    return ut, poeng, m


def skifter(eksp):
    """Antall ganger eksponeringen endres. Hvert skifte koster penger."""
    return int((np.diff(eksp) != 0).sum())
