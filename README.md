# Krypto papirhandel - Krypto13, Krypto50 og Krypto100 på GitHub Actions

**Simulert papirhandel. Ingen ekte penger, ingen API-nøkler, ingen ordre sendes til noen børs.**

Gjenoppbygd 2026-09-19 etter at PC-en som kjørte systemene ble ødelagt.
Alt kjører nå hver time på GitHub sine servere (`.github/workflows/handel.yml`),
status lagres i `state/` og committes tilbake, og dashbordet (`index.html`,
GitHub Pages) leser `state/*/dashboard.json` direkte.

| | System 1 | Krypto50 |
|---|---|---|
| Mynter | 13 faste (inkl. CAKE) | Topp 50 etter volum, ≥365 d historikk |
| Candles | Daglige, SMA 8/33 (giret opp 2026-09-19) | 4-timers, SMA 50/200 (= 8/33 dager) |
| Signal | Nyheter, on-chain (BTC), TA, Fear&Greed, funding | TA 80 %, Fear&Greed 10 %, funding 10 % |
| Hysterese | 2 like beslutninger på rad (kjøringer) | 2 like på rad per LUKKET candle (8 t) |
| Grenser | 10 % per mynt, 60 % totalt | 4 % per mynt, 80 % totalt |

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
