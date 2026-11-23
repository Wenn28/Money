"""Proksi arah intraday: klasifikasi Lee-Ready, CVD, OFI 5 level (Cont-Kukanov-Stoikov)."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

BELI, JUAL, NETRAL = "B", "S", "U"


@dataclass(frozen=True)
class Book:
    bid_px: tuple[float, ...]
    bid_vol: tuple[float, ...]
    ask_px: tuple[float, ...]
    ask_vol: tuple[float, ...]


def lee_ready(price: float, bid: float, ask: float, prev_price: float | None, prev_side: str = NETRAL) -> str:
    """Quote rule dulu (vs titik tengah), lalu tick test, lalu zero-tick memakai sisi sebelumnya."""
    mid = (bid + ask) / 2
    if price > mid:
        return BELI
    if price < mid:
        return JUAL
    if prev_price is None:
        return NETRAL
    if price > prev_price:
        return BELI
    if price < prev_price:
        return JUAL
    return prev_side


def cvd(trades: Iterable[tuple[str, float]]) -> float:
    """trades = (sisi agresor, nilai). Beli agresor +, jual agresor -, netral diabaikan."""
    return sum(n if s == BELI else -n if s == JUAL else 0.0 for s, n in trades)


def ofi(prev: Book, cur: Book) -> float:
    """OFI = jumlah e_n lintas level. Bid naik atau tetap menambah, bid turun atau tetap mengurangi; ask sebaliknya."""
    total = 0.0
    for n in range(len(cur.bid_px)):
        pb, pb0 = cur.bid_px[n], prev.bid_px[n]
        pa, pa0 = cur.ask_px[n], prev.ask_px[n]
        total += (
            (cur.bid_vol[n] if pb >= pb0 else 0.0)
            - (prev.bid_vol[n] if pb <= pb0 else 0.0)
            - (cur.ask_vol[n] if pa <= pa0 else 0.0)
            + (prev.ask_vol[n] if pa >= pa0 else 0.0)
        )
    return total


def net_asing(asing_beli_nilai: float, asing_jual_nilai: float) -> float:
    """Checkpoint domisili Sesi I: Net Foreign Buy (+) atau Sell (-)."""
    return asing_beli_nilai - asing_jual_nilai
