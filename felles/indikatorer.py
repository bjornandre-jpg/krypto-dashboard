"""Tekniske indikatorer som serier (samme kode brukes live og i backtest)."""


def sma(xs, n):
    ut, s = [None] * len(xs), 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            ut[i] = s / n
    return ut


def ema(xs, n):
    k, ut, e = 2 / (n + 1), [], None
    for x in xs:
        e = x if e is None else x * k + e * (1 - k)
        ut.append(e)
    return ut


def rsi(xs, n=14):
    ut = [None] * len(xs)
    if len(xs) < n + 1:
        return ut
    a = 1 / n
    g = l = None
    for i in range(1, len(xs)):
        d = xs[i] - xs[i - 1]
        up, dn = max(d, 0.0), max(-d, 0.0)
        g = up if g is None else up * a + g * (1 - a)
        l = dn if l is None else dn * a + l * (1 - a)
        if i >= n:
            ut[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return ut


def macd(xs, f=12, s=26, sig=9):
    ef, es = ema(xs, f), ema(xs, s)
    linje = [a - b for a, b in zip(ef, es)]
    signal = ema(linje, sig)
    return linje, signal, [a - b for a, b in zip(linje, signal)]
