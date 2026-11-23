"""Akumulasi/distribusi lintas broker (EOD, Pasar Reguler): Delta HHI, rasio, konsentrasi Top-N."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerRow:
    broker: str
    beli_vol: float
    beli_nilai: float
    jual_vol: float
    jual_nilai: float

    @property
    def net_nilai(self) -> float:
        return self.beli_nilai - self.jual_nilai

    @property
    def avg_beli(self) -> float | None:
        return self.beli_nilai / self.beli_vol if self.beli_vol else None

    @property
    def avg_jual(self) -> float | None:
        return self.jual_nilai / self.jual_vol if self.jual_vol else None


@dataclass(frozen=True)
class Ambang:
    """BELUM DIKALIBRASI: nilai awal tebakan, kalibrasi dengan backtest sebelum dipercaya."""
    delta_hhi_besar: float = 500.0
    delta_hhi_moderat: float = 150.0
    top3_besar_pct: float = 60.0
    top3_moderat_pct: float = 45.0
    rasio_besar_beli_maks: float = 0.8
    rasio_besar_jual_min: float = 1.25


@dataclass(frozen=True)
class Skor:
    hhi_beli: float
    hhi_jual: float
    delta_hhi: float
    n_net_buyer: int
    n_net_seller: int
    rasio_buyer_seller: float
    top_beli_pct: tuple[float, float, float]  # Top-1, Top-3, Top-5
    top_jual_pct: tuple[float, float, float]
    status: str


def _hhi_dan_top(net: list[float]) -> tuple[float, tuple[float, float, float]]:
    """net = nilai positif per broker pada satu sisi. Pangsa dalam persen."""
    total = sum(net)
    if total <= 0:
        return 0.0, (0.0, 0.0, 0.0)
    pangsa = sorted((n / total * 100 for n in net), reverse=True)
    return sum(p * p for p in pangsa), (sum(pangsa[:1]), sum(pangsa[:3]), sum(pangsa[:5]))


def klasifikasi(delta_hhi: float, rasio: float, top3_beli: float, top3_jual: float, a: Ambang = Ambang()) -> str:
    if delta_hhi >= a.delta_hhi_besar and top3_beli >= a.top3_besar_pct and rasio <= a.rasio_besar_beli_maks:
        return "BIG_ACCUMULATION"
    if delta_hhi <= -a.delta_hhi_besar and top3_jual >= a.top3_besar_pct and rasio >= a.rasio_besar_jual_min:
        return "BIG_DISTRIBUTION"
    if delta_hhi >= a.delta_hhi_moderat and top3_beli >= a.top3_moderat_pct:
        return "MODERATE_ACCUMULATION"
    if delta_hhi <= -a.delta_hhi_moderat and top3_jual >= a.top3_moderat_pct:
        return "DISTRIBUTION"
    return "NEUTRAL"


def hitung_skor(baris: Iterable[BrokerRow], ambang: Ambang = Ambang()) -> Skor:
    nets = [b.net_nilai for b in baris]
    pembeli = [n for n in nets if n > 0]
    penjual = [-n for n in nets if n < 0]
    hhi_beli, top_beli = _hhi_dan_top(pembeli)
    hhi_jual, top_jual = _hhi_dan_top(penjual)
    delta = hhi_beli - hhi_jual
    rasio = len(pembeli) / max(len(penjual), 1)
    return Skor(
        hhi_beli, hhi_jual, delta, len(pembeli), len(penjual), rasio, top_beli, top_jual,
        klasifikasi(delta, rasio, top_beli[1], top_jual[1], ambang),
    )


def selisih_harga_vs_vwap(avg_harga: float | None, vwap: float) -> float | None:
    """Persen harga rata-rata broker terhadap VWAP (atau Close); None jika broker tidak bertransaksi di sisi itu."""
    if avg_harga is None or vwap <= 0:
        return None
    return (avg_harga - vwap) / vwap * 100
