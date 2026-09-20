"""Krypto100: identisk med Krypto50 (4t candles, TA 80 / F&G 10 / funding 10,
terskel ±0,30, to bekreftelser per lukket candle), men topp 100 mynter.
Maks 2 % per mynt (halvparten av Krypto50, siden universet er dobbelt så stort),
80 % total eksponering. INGEN ekte penger."""
import os
import sys

from krypto100 import UNIVERS_FIL
from krypto50.kjor import main

if __name__ == "__main__":
    sys.exit(main(os.path.join("state", "krypto100"), UNIVERS_FIL, 0.02, "Krypto100 - 100 mynter, 4t"))
