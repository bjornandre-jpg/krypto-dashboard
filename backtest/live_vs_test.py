"""Sammenligner live-logikken med den logikken backtestene faktisk måler.

Krypto13 live: hver time bygges dagens candle av timene siden midnatt, TA
regnes på serien med den ufullstendige dagen sist, og et signal regnes som
bekreftet når forrige TIMESKJØRING ga samme beslutning (= 2 timer).

Krypto13 i backtesten: TA på kun lukkede dagscandles, og bekreftelse krever to
påfølgende DAGER.

Begge kjøres her på nøyaktig samme timesdata og samme handelskode, så
forskjellen kommer utelukkende fra hvor ofte det tas beslutning.

TA regnes skrittvis: alt som avhenger av lukkede dager beregnes én gang per
dag, og hver time legges bare dagens løpende kurs på som ett siste steg. Det
gir nøyaktig samme tall som å regne hele serien på nytt, men er raskt nok til
å kjøre 35 000 timer.
"""
import bisect
import json
import os
from collections import deque
from datetime import datetime, timezone

from felles.portefolje import Portefolje, vurder_mynt
from felles.signal import beslutning, fear_greed_score, funding_score, klipp

CACHE_1H = os.environ.get("BV1H_CACHE", "/tmp/bv1h")
CACHE = os.environ.get("BV_CACHE", "/tmp/bv")


def _les(sti):
    with open(sti, encoding="utf-8") as f:
        return json.load(f)


def _oppslag(ts_liste, verdier, t):
    i = bisect.bisect_right(ts_liste, t) - 1
    return verdier[i] if i >= 0 else None


class TA:
    """Trinnvis utgave av felles.signal.ta_serie.

    lukk_dag(c) tar inn en lukket dagskurs og flytter tilstanden fram.
    score(c) gir TA-verdien slik den ville sett ut med c som dagens kurs,
    uten å endre tilstanden.
    """

    def __init__(self, rask=10, treg=40, n_rsi=14, f=12, s=26, sig=9):
        self.rask, self.treg, self.n = rask, treg, n_rsi
        self.kf, self.ks, self.ksig = 2 / (f + 1), 2 / (s + 1), 2 / (sig + 1)
        self.buf_r, self.buf_t = deque(), deque()
        self.sum_r = self.sum_t = 0.0
        self.forrige = None
        self.g = self.l = None
        self.ema_f = self.ema_s = self.sig = None
        self.antall = 0

    def _sma(self, buf, sum_, n, c):
        if len(buf) < n - 1:
            return None
        s = sum_ + c - (buf[0] if len(buf) >= n else 0.0)
        return s / n

    def score(self, c):
        if self.antall < self.treg or self.forrige is None:
            return None
        s_r = self._sma(self.buf_r, self.sum_r, self.rask, c)
        s_t = self._sma(self.buf_t, self.sum_t, self.treg, c)
        if s_r is None or s_t is None:
            return None
        a = 1 / self.n
        d = c - self.forrige
        g = max(d, 0.0) * a + (self.g or 0.0) * (1 - a)
        l = max(-d, 0.0) * a + (self.l or 0.0) * (1 - a)
        r = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
        ef = c * self.kf + self.ema_f * (1 - self.kf)
        es = c * self.ks + self.ema_s * (1 - self.ks)
        linje = ef - es
        hist = linje - (linje * self.ksig + self.sig * (1 - self.ksig))
        trend = klipp((c / s_t - 1) / 0.10)
        kryss = klipp((s_r / s_t - 1) / 0.05)
        m = klipp(hist / (0.01 * c))
        if r >= 70:
            rs = -klipp((r - 70) / 15, 0, 1)
        elif r <= 30:
            rs = klipp((30 - r) / 15, 0, 1)
        else:
            rs = (r - 50) / 40
        return 0.35 * trend + 0.25 * kryss + 0.25 * m + 0.15 * rs

    def lukk_dag(self, c):
        if self.forrige is not None:
            a = 1 / self.n
            d = c - self.forrige
            self.g = max(d, 0.0) * a + (self.g or 0.0) * (1 - a)
            self.l = max(-d, 0.0) * a + (self.l or 0.0) * (1 - a)
        self.ema_f = c if self.ema_f is None else c * self.kf + self.ema_f * (1 - self.kf)
        self.ema_s = c if self.ema_s is None else c * self.ks + self.ema_s * (1 - self.ks)
        linje = self.ema_f - self.ema_s
        self.sig = linje if self.sig is None else linje * self.ksig + self.sig * (1 - self.ksig)
        for buf, n, navn in ((self.buf_r, self.rask, "r"), (self.buf_t, self.treg, "t")):
            buf.append(c)
            if navn == "r":
                self.sum_r += c
                if len(buf) > n:
                    self.sum_r -= buf.popleft()
            else:
                self.sum_t += c
                if len(buf) > n:
                    self.sum_t -= buf.popleft()
        self.forrige = c
        self.antall += 1


def kjor(markeder, modus, vekter, cfg, rask=10, treg=40, terskel=0.30,
         gebyr=0.0025, start=1000.0):
    """modus: "live" (beslutning hver time, 2 timers bekreftelse) eller
    "test" (beslutning per lukket dag, 2 dagers bekreftelse)."""
    data = {}
    for m in markeder:
        c = _les(os.path.join(CACHE_1H, f"{m}_1h.json"))
        if not c:
            continue
        f_sti = os.path.join(CACHE, f"{m.split('-')[0]}_funding.json")
        fh = _les(f_sti) if os.path.exists(f_sti) else []
        data[m] = {"c": c, "pris": {x[0]: x[4] for x in c},
                   "fund_ts": [x[0] // 1000 for x in fh], "fund": [x[1] for x in fh],
                   "ta": TA(rask, treg), "dag": None, "beslutning_dag": None}
    fng = _les(os.path.join(CACHE, "fng.json"))
    fts, fvs = [x[0] for x in fng], [x[1] for x in fng]

    alle_ts = sorted({x[0] for d in data.values() for x in d["c"]})
    pf = Portefolje({"gebyr": gebyr, "terskel": terskel, **cfg}, start)
    hist = {m: [] for m in data}
    siste, kurve = {}, []
    topp, ned, n_handler, oms, geb = start, 0.0, 0, 0.0, 0.0

    for ts in alle_ts:
        dag = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        for m, d in data.items():
            if ts in d["pris"]:
                siste[m] = d["pris"][ts]
                if d["dag"] is None:
                    d["dag"] = dag
                elif dag != d["dag"]:               # dagen før er ferdig
                    d["ta"].lukk_dag(d["forrige_kurs"])
                    d["dag"] = dag
                d["forrige_kurs"] = d["pris"][ts]
        eq = pf.egenkapital(siste)
        pf.start_dag(ts // 86400, eq)
        for m, d in data.items():
            if m not in siste:
                continue
            ny_signal = True
            if modus in ("test", "hybrid"):
                # signalet vurderes bare én gang per døgn, på lukket dagscandle
                ny_signal = d["beslutning_dag"] != dag
                if ny_signal:
                    d["beslutning_dag"] = dag
                elif modus == "test":
                    continue                     # ingen sjekk mellom dagene
                ta = d["ta"].score(d["ta"].forrige) if d["ta"].forrige is not None else None
            else:
                ta = d["ta"].score(siste[m])
            if ta is None:
                # ingen TA ennå, men stop-loss skal likevel kunne utløses i hybrid
                if modus == "hybrid" and pf.pos(m):
                    vurder_mynt(pf, m, siste, eq, "AVVENT", 0.0, False, False, ts)
                continue
            sc = (vekter["ta"] * ta
                  + vekter["fg"] * fear_greed_score(_oppslag(fts, fvs, ts))
                  + vekter["funding"] * funding_score(_oppslag(d["fund_ts"], d["fund"], ts)))
            b = beslutning(sc, terskel)
            h = hist[m]
            if ny_signal:
                h.append(b)
                del h[:-3]
            bekreftet = ny_signal and len(h) >= 2 and h[-1] == h[-2]
            vurder_mynt(pf, m, siste, eq, h[-1] if h else b, sc, bekreftet, ny_signal, ts)
        for x in pf.handler:
            oms += x["belop"]
            geb += x["gebyr"]
        n_handler += len(pf.handler)
        pf.handler = []
        eq = pf.egenkapital(siste)
        topp = max(topp, eq)
        ned = min(ned, eq / topp - 1)
        kurve.append((ts, eq))

    aar = (alle_ts[-1] - alle_ts[0]) / (365.25 * 86400)
    avk = kurve[-1][1] / start - 1
    return {"avkastning": avk, "annualisert": (1 + avk) ** (1 / aar) - 1,
            "maks_nedgang": ned, "handler": n_handler, "aar": aar,
            "oms_uke": oms / (aar * 52), "gebyr_aar_pst": geb / aar / start * 100,
            "kurve": kurve}
