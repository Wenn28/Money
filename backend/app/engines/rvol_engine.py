"""RVOL ternormalisasi kurva-U: RVOL(t) = V_cum(t) / (Baseline20H * F(t))."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time

MIN_RVOL = 3.5
MIN_NILAI_IDR = 5_000_000_000
# shortcut: F(t) di bawah ini dianggap terlalu dini untuk RVOL andal, naikkan kalau alarm menit pembukaan berisik.
MIN_FRAKSI = 0.02

# Sesi perdagangan (buka, tutup) per jenis hari. Tutup 15:50 tidak termasuk.
_SESI = {
    "SEN_KAM": ((time(9, 0), time(12, 0)), (time(13, 30), time(15, 50))),
    "JUM": ((time(9, 0), time(11, 30)), (time(14, 0), time(15, 50))),
}


def jenis_hari(tanggal: date) -> str:
    return "JUM" if tanggal.weekday() == 4 else "SEN_KAM"


def menit_sesi(waktu: datetime) -> int | None:
    """Indeks menit perdagangan sejak buka (0-based, tanpa jeda istirahat). None di luar sesi."""
    terpakai = 0
    t = waktu.time().replace(second=0, microsecond=0)
    for buka, tutup in _SESI[jenis_hari(waktu.date())]:
        if buka <= t < tutup:
            return terpakai + (t.hour * 60 + t.minute) - (buka.hour * 60 + buka.minute)
        terpakai += (tutup.hour * 60 + tutup.minute) - (buka.hour * 60 + buka.minute)
    return None


def baseline_trimmed_mean(volumes: Sequence[float], trim: float = 0.10) -> float:
    """Rata-rata setelah membuang trim di tiap ekor (20 hari: 2 terendah dan 2 tertinggi dibuang)."""
    if not volumes:
        raise ValueError("volumes kosong")
    urut = sorted(volumes)
    k = int(len(urut) * trim)
    inti = urut[k : len(urut) - k]
    return sum(inti) / len(inti)


def baseline_median(volumes: Sequence[float]) -> float:
    if not volumes:
        raise ValueError("volumes kosong")
    urut = sorted(volumes)
    n = len(urut)
    return urut[n // 2] if n % 2 else (urut[n // 2 - 1] + urut[n // 2]) / 2


def fraksi_kumulatif(profil: Sequence[float], menit: int) -> float:
    """F(t): fraksi kumulatif volume sampai akhir menit sesi ke-`menit` (0-based)."""
    return profil[min(menit, len(profil) - 1)]


def rvol_norm(v_cum: float, baseline: float, fraksi: float) -> float | None:
    """None jika baseline atau F(t) belum cukup untuk perbandingan yang andal."""
    if baseline <= 0 or fraksi < MIN_FRAKSI:
        return None
    return v_cum / (baseline * fraksi)


def is_lonjakan(
    rvol: float | None,
    nilai_kumulatif: float,
    min_rvol: float = MIN_RVOL,
    min_nilai: float = MIN_NILAI_IDR,
) -> bool:
    return rvol is not None and rvol >= min_rvol and nilai_kumulatif >= min_nilai
