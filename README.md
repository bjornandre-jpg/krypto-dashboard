# Krypto papirhandel - Krypto13, Krypto50 og Krypto100 på Bitvavo (EUR)

**Simulert papirhandel. Ingen ekte penger, ingen API-nøkler, ingen ordre sendes til noen børs.**

Gjenoppbygd 2026-09-19 etter at PC-en som kjørte systemene ble ødelagt.
Alt kjører nå hver time på GitHub sine servere (`.github/workflows/handel.yml`),
status lagres i `state/` og committes tilbake, og dashbordet (`index.html`,
GitHub Pages) leser `state/*/dashboard.json` direkte.

| | System 1 | Krypto50 |
|---|---|---|
| Mynter | 13 faste (inkl. CAKE) | Topp 50 EUR-par på Bitvavo, ≥365 d historikk, spread ≤0,30 % |
| Candles | Daglige, SMA 8/33 (giret opp 2026-09-19) | 4-timers, SMA 50/200 (= 8/33 dager) |
| Signal | Nyheter, on-chain (BTC), TA, Fear&Greed, funding | TA 80 %, Fear&Greed 10 %, funding 10 % |
| Hysterese | 2 like beslutninger på rad (kjøringer) | 2 like på rad per LUKKET candle (8 t) |
| Grenser | 10 % per mynt, 60 % totalt | 3 % per mynt, 70 % totalt |

Felles: terskel ±0,30, stop-loss 15 %, ingen take-profit, rebalansering ved 1,05× målvekt,
maks 30 handler/døgn, maks dagstap 5 % (stopper nye kjøp), gebyr 0,1 %, kun long/spot.

**Nødstopp:** lag en tom fil `state/system1/STOPP` eller `state/krypto50/STOPP`
(via GitHub-appen/nettsiden) - da gjøres ingen nye kjøp.

**Manuell kjøring:** Actions → «Papirhandel hver time» → Run workflow.

## Struktur
- `felles/` - datakilder (KuCoin, Fear&Greed, nyheter, on-chain), indikatorer, signal, portefølje/risiko
- `system1/kjor.py`, `krypto50/kjor.py` - timeskjøringene
- `krypto50/univers.py` - bygger `univers.json` (egen manuell workflow)
- `backtest/` - porteføljebacktest av Krypto50 med samme kode som live
- `state/<system>/` - portefolje.json, handler.csv, egenkapital.csv, signaler.csv, dashboard.json

## Rekonstruksjon
Signalomregningene i `felles/signal.py` er ny kode (originalen gikk tapt). Validert
2026-09-19 med backtest over 3 år / 50 mynter: +88 % (-24 % maks nedgang) mot
dokumentert +78 % (-18 %) for originalen; stokket signal +13 %.
System 1 ble gjenopprettet fra siste Gist-status (2026-09-16 04:32 UTC);
handelshistorikk før det gikk tapt.

## System 1 giret opp (2026-09-19)
Backtest, 13 mynter, daglige candles, ~3 år (nyheter/on-chain uten historikk, satt nøytrale):

| Variant | Avkastning | Maks nedgang | Handler |
|---|---|---|---|
| Før: SMA 50/200, TA 65 % | -24,9 % | -28,3 % | 790 |
| Etter: SMA 8/33, TA 80 % | +35,8 % til +60,7 %* | -29 til -37 % | ~2 500-2 800 |
| Nabovinduer 6/25, 10/40, 12/50 | +41 til +57 % | -29 til -33 % | |
| Stokket signal (kontroll) | +6,2 % | -40,1 % | |
| Kjøp&hold likevektet | +109,4 % | (ikke beregnet) | |

*avhengig av bekreftelseskrav (2 dager vs 1). Live bekreftes per time på daglig
candle inkl. dagens pris, som ligger nærmest 1-dags-varianten.

## Krypto100 (lagt til 2026-09-20)
Identisk med Krypto50, men topp 100 mynter etter volum (≥365 d historikk,
`krypto100/univers.json`, bygges med `python -m krypto50.univers 100`) og maks
2 % per mynt (80 % totalt). Backtest ~3 år: +66,5 % (-28,0 % maks nedgang);
med 4 % per mynt +95,7 % men -40,3 % nedgang; stokket signal -9,5 %.
System 1 heter nå Krypto13 i dashbordet (mappen er fortsatt `state/system1`).

## Exit-reglene endret (2026-09-25)
Backtest over ~3 år viste at take-profit på 20 % og stop-loss på 8 % kostet mye:
de kuttet vinnerne og kastet ut posisjoner i vanlig støy. Nye regler for alle tre
systemene: stop-loss 15 %, ingen take-profit. Krypto13 fikk i tillegg trendvindu
SMA 10/40 (fra 8/33).

| System | Før | Etter |
|---|---|---|
| Krypto13 | +35,8 % (-36,7 % nedgang) | +83,9 % (-28,0 %) |
| Krypto50 | +87,8 % (-23,8 %) | +172,2 % (-26,4 %) |
| Krypto100 | +66,5 % (-28,0 %) | +138,5 % (-31,5 %) |

Helt uten stop-loss ble tallene enda bedre (Krypto50 +188,8 %), men stop-loss
beholdes som forsikring mot at én mynt kollapser.

## Flyttet til Bitvavo (2026-09-27)
Kurser og (senere) handel skjer på **Bitvavo i euro**, ikke lenger KuCoin i USDT.
Bakgrunn: Bitvavo har MiCA-lisens (nederlandske AFM), 0,15 % maker / 0,25 % taker
mot Kraken sine 0,40/0,80 %, og alle 13 Krypto13-myntene er listet.
Funding hentes fortsatt fra KuCoin futures, siden Bitvavo ikke har perpetuals og
funding er et markedsbredt signal.

Alle tre systemene ble nullstilt til 1 000 EUR samtidig; tidligere historikk i
`state/arkiv/`. Universene bygges på nytt fra Bitvavos EUR-par, nå også med et
**spread-filter på 0,30 %** - en måling viste at små par som POND (1,33 %) koster
mer i spread enn i gebyr. Krypto50 er samtidig dempet til 3 % per mynt og 70 %
totalt, og Krypto100 til 1,5 % / 70 %, for å holde maks nedgang på nivå med Krypto13.

Backtest på Bitvavos egne eurokurser, ved 0,25 % gebyr (spread ikke medregnet):

| System | Avkastning | Årlig | Maks nedgang | Stokket kontroll |
|---|---|---|---|---|
| Krypto13 (3,9 år) | +99,4 % | +19,2 % | -31,4 % | +36,2 % |
| Krypto50 (3,0 år) | +91,9 % | +24,0 % | -42,0 % | -30,4 % |

Krypto50-tallet gjelder 4 % per mynt; med 3 % / 70 % ble det +69,1 % og -34,2 %.

## Live matchet ikke backtesten (rettet 2026-09-30)
Den ukentlige helsesjekken avdekket at systemene omsatte ca. fire ganger mer
enn backtesten forutsatte. Årsaken var at beslutninger ble tatt for ofte:

- **Krypto13** regnet TA på en dagscandle som ikke var ferdig, og godtok to
  påfølgende TIMESKJØRINGER som bekreftelse. Backtesten krever to påfølgende
  LUKKEDE dager. Rettet: kun lukkede dagscandles, én beslutning per døgn.
- **Krypto50/100** hadde riktig hysterese, men sjekket stop-loss og
  rebalansering hver time. Rettet: handler bare når en 4-timers candle lukkes.

Målt på samme data og samme handelskode:

| Krypto13, 4 år | Avkastning | Maks ned | Omsetning | Gebyr/år |
|---|---|---|---|---|
| Signal daglig (rettet) | +99,3 % | -23,0 % | 255/uke | 3,3 % |
| Signal daglig + stop-loss hver time | +83,5 % | -26,7 % | 261/uke | 3,4 % |
| Signal hver time (slik det var) | +73,7 % | -26,8 % | 562/uke | 7,3 % |

| 3 år | Stop-loss ved candle-slutt | Stop-loss løpende |
|---|---|---|
| Krypto50 | +73,7 % (-33,7 %) | +58,6 % (-36,0 %) |
| Krypto100 | +54,6 % (-33,4 %) | +42,1 % (-37,0 %) |

Daglig vant i seks av sju nabo-oppsett for Krypto13. Hyppigere sjekk ga
lavere avkastning OG dypere fall i alle tre systemene: posisjoner kastes ut
på støy som er hentet inn igjen ved candle-slutt.
