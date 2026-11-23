"""Klien kecil Yahoo Finance chart API (tidak resmi, tertunda ~10 menit). Hanya stdlib."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{kode}.JK?interval={interval}&range={rng}"


def ambil_chart(kode: str, interval: str, rng: str, coba: int = 4) -> list[dict] | None:
    """Bar [{ts: datetime WIB, close, volume}] atau None bila gagal. Mundur eksponensial saat 429."""
    req = urllib.request.Request(
        _URL.format(kode=kode, interval=interval, rng=rng), headers={"User-Agent": "Mozilla/5.0"}
    )
    for n in range(coba):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                hasil = json.load(r)["chart"]["result"]
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and n < coba - 1:
                time.sleep(2 ** (n + 1))
                continue
            return None
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
            if n < coba - 1:
                time.sleep(1)
                continue
            return None
    if not hasil or "timestamp" not in hasil[0]:
        return None
    h = hasil[0]
    q = h["indicators"]["quote"][0]
    return [
        {"ts": datetime.fromtimestamp(t, WIB), "close": c, "volume": v}
        for t, c, v in zip(h["timestamp"], q["close"], q["volume"])
        if c is not None and v is not None
    ]
