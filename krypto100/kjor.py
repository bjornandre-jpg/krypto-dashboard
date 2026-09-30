"""Krypto100: identisk med Krypto50 (Bitvavo/EUR, 4t candles, TA 80 / F&G 10 /
funding 10, terskel ±0,30, to bekreftelser per lukket candle), men topp 100 mynter.
Maks 1,5 % per mynt, 70 % totalt. INGEN ekte penger."""
import os
import sys

from krypto100 import UNIVERS_FIL
from krypto50.kjor import main

if __name__ == "__main__":
    sys.exit(main(os.path.join("state", "krypto100"), UNIVERS_FIL, 0.015, 0.70,
                  "Krypto100 - 100 mynter, 4t"))
