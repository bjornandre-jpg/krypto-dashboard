"""Enkel HTTP-henting med kun standardbiblioteket."""
import json
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (krypto-bot papirhandel)"}


def get(url, params=None, retries=3, timeout=25):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET {url} feilet etter {retries} forsøk: {last}")


def get_json(url, params=None, **kw):
    return json.loads(get(url, params, **kw).decode("utf-8"))
