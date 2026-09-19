"""Nyhetssentiment: gratis RSS-overskrifter + VADER. Markedsbredt signal."""
import xml.etree.ElementTree as ET
from .http import get

FEEDS = ["https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss",
         "https://decrypt.co/feed", "https://bitcoinmagazine.com/feed"]


def score():
    """Gjennomsnittlig VADER compound i [-1,1], eller None hvis ingenting kunne hentes."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError:
        return None, 0
    ana = SentimentIntensityAnalyzer()
    titler = []
    for url in FEEDS:
        try:
            rot = ET.fromstring(get(url, retries=2, timeout=15))
            titler += [e.text for e in rot.iter("title") if e.text][1:30]
        except Exception:  # noqa: BLE001 - én død kilde skal ikke stoppe kjøringen
            continue
    if not titler:
        return None, 0
    return sum(ana.polarity_scores(t)["compound"] for t in titler) / len(titler), len(titler)
