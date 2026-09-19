"""Omregning av råtall til delscore i [-1, 1] og samlet beslutning.

Rekonstruert 2026-09-19 etter at originalkoden gikk tapt med PC-en.
Vekter og terskler er de dokumenterte; selve omregningene under er nye
og brukes likt i begge systemene.
"""
from .indikatorer import sma, rsi, macd


def klipp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def ta_serie(closes, rask=50, treg=200):
    """TA-score per candle (None før det finnes nok historikk)."""
    s_r, s_t = sma(closes, rask), sma(closes, treg)
    r = rsi(closes, 14)
    _, _, hist = macd(closes)
    ut = []
    for i, p in enumerate(closes):
        if s_t[i] is None or r[i] is None:
            ut.append(None)
            continue
        trend = klipp((p / s_t[i] - 1) / 0.10)          # pris over/under langt snitt
        kryss = klipp((s_r[i] / s_t[i] - 1) / 0.05)     # golden/death cross, glattet
        m = klipp(hist[i] / (0.01 * p))                 # MACD-histogram, prisnormalisert
        ri = r[i]
        if ri >= 70:
            rs = -klipp((ri - 70) / 15, 0, 1)            # overkjøpt
        elif ri <= 30:
            rs = klipp((30 - ri) / 15, 0, 1)             # oversolgt
        else:
            rs = (ri - 50) / 40                          # moderat momentum
        ut.append(0.35 * trend + 0.25 * kryss + 0.25 * m + 0.15 * rs)
    return ut


def fear_greed_score(verdi):
    """KONTRÆR: ekstrem frykt = positivt, ekstrem grådighet = negativt."""
    return 0.0 if verdi is None else klipp((50 - verdi) / 50)


def funding_score(rate):
    """KONTRÆR, sentrert rundt normal-raten 0,01 %/8t. None -> nøytral."""
    return 0.0 if rate is None else klipp(-(rate - 0.0001) / 0.0005)


def vektet(deler, vekter):
    return sum(vekter[k] * (deler.get(k) or 0.0) for k in vekter)


def beslutning(score, terskel=0.30):
    if score >= terskel:
        return "KJØP"
    if score <= -terskel:
        return "SELG"
    return "AVVENT"
