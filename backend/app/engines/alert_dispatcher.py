"""Cooldown, deduplikasi, format pesan patuh (data kuantitatif saja), dan pengiriman alert."""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

DISCLAIMER = "Data kuantitatif objektif, bukan rekomendasi investasi. Keputusan dan risiko ditanggung pengguna."
# POJK 6/2026: pesan tidak boleh berisi perintah transaksi atau target harga.
_DILARANG = re.compile(r"\b(beli|jual|buy|sell|target\s+harga)\b", re.IGNORECASE)


@dataclass(frozen=True)
class AturanAlert:
    cooldown_detik: int = 15 * 60
    naik_rvol_lagi: float = 1.0


@dataclass(frozen=True)
class AlertEvent:
    ts: datetime
    kode: str
    papan: str
    rvol: float
    nilai_kumulatif: float
    cvd: float | None = None
    ofi: float | None = None
    lencana_risiko: list[str] = field(default_factory=list)


class StoreCooldown(Protocol):
    async def ambil(self, kode: str) -> tuple[float, float] | None: ...
    async def simpan(self, kode: str, ts: float, rvol: float, ttl_detik: int) -> None: ...


class StoreMemori:
    def __init__(self) -> None:
        self.data: dict[str, tuple[float, float]] = {}

    async def ambil(self, kode: str) -> tuple[float, float] | None:
        return self.data.get(kode)

    async def simpan(self, kode: str, ts: float, rvol: float, ttl_detik: int) -> None:
        self.data[kode] = (ts, rvol)


class StoreValkey:
    """State cooldown di Valkey; kunci kedaluwarsa sendiri setelah cooldown."""

    def __init__(self, url: str) -> None:
        import valkey.asyncio as valkey

        self.r = valkey.from_url(url, decode_responses=True)

    async def ambil(self, kode: str) -> tuple[float, float] | None:
        v = await self.r.get(f"alert:terakhir:{kode}")
        if v is None:
            return None
        ts, rvol = v.split("|")
        return float(ts), float(rvol)

    async def simpan(self, kode: str, ts: float, rvol: float, ttl_detik: int) -> None:
        await self.r.set(f"alert:terakhir:{kode}", f"{ts}|{rvol}", ex=ttl_detik)


def boleh_kirim(terakhir: tuple[float, float] | None, ts: float, rvol: float, aturan: AturanAlert) -> bool:
    """Kirim bila belum ada alert, cooldown habis, atau RVOL naik lagi sejauh naik_rvol_lagi dari alert terakhir."""
    if terakhir is None:
        return True
    ts0, rvol0 = terakhir
    return ts - ts0 >= aturan.cooldown_detik or rvol >= rvol0 + aturan.naik_rvol_lagi


def _angka(x: float, desimal: int) -> str:
    return f"{x:.{desimal}f}".replace(".", ",")


def rupiah_singkat(x: float) -> str:
    """Tanda eksplisit; T = triliun, M = miliar, Jt = juta."""
    tanda = "+" if x >= 0 else "-"
    a = abs(x)
    for batas, sufiks in ((1e12, "T"), (1e9, "M"), (1e6, "Jt")):
        if a >= batas:
            return f"{tanda}Rp{_angka(a / batas, 1)}{sufiks}"
    return f"{tanda}Rp{_angka(a, 0)}"


def lencana(jenis: str, nilai_pct: float | None = None) -> str:
    if jenis == "FCA_X":
        return "[FCA-X]"
    if jenis == "HSC" and nilai_pct is not None:
        return f"[HSC >= {_angka(nilai_pct, 1)}%]"
    return f"[{jenis}]"


def arah_ofi(ofi: float | None) -> str:
    return "n/a" if ofi is None else "Positif" if ofi > 0 else "Negatif" if ofi < 0 else "Netral"


def format_pesan(e: AlertEvent) -> str:
    bagian = [
        f"ANOMALI VOLUME TERDETEKSI: {e.kode}",
        f"RVOL {_angka(e.rvol, 2)}x",
        f"CVD {'n/a' if e.cvd is None else rupiah_singkat(e.cvd)}",
        f"OFI {arah_ofi(e.ofi)}",
        f"Status: [{e.papan}]",
    ]
    baris = " | ".join(bagian)
    if e.lencana_risiko:
        baris += " " + " ".join(e.lencana_risiko)
    pesan = f"{baris}\n{DISCLAIMER}"
    pastikan_patuh(pesan)
    return pesan


def pastikan_patuh(pesan: str) -> None:
    if m := _DILARANG.search(pesan):
        raise ValueError(f"pesan alert memuat kata terlarang: {m.group(0)!r}")


Notifier = Callable[[AlertEvent, str], Awaitable[None]]


def telegram_notifier(token: str, chat_id: str) -> Notifier:
    async def kirim(_: AlertEvent, pesan: str) -> None:
        import httpx

        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": pesan})
            r.raise_for_status()

    return kirim


class AlertDispatcher:
    """Mesin alert tidak dithrottle: setiap event dievaluasi, hanya cooldown yang menahan."""

    def __init__(self, store: StoreCooldown, notifiers: list[Notifier], aturan: AturanAlert = AturanAlert()) -> None:
        self.store, self.notifiers, self.aturan = store, notifiers, aturan

    async def dispatch(self, e: AlertEvent) -> str | None:
        ts = e.ts.timestamp()
        if not boleh_kirim(await self.store.ambil(e.kode), ts, e.rvol, self.aturan):
            return None
        pesan = format_pesan(e)
        # shortcut: tanpa kunci atomik, aman bila satu worker memproses satu emiten; kunci Lua bila worker diparalelkan.
        await self.store.simpan(e.kode, ts, e.rvol, self.aturan.cooldown_detik)
        for kirim in self.notifiers:
            try:
                await kirim(e, pesan)
            except Exception:
                pass  # satu kanal gagal tidak boleh menahan kanal lain; log kegagalan dipasang di Tahap 4
        return pesan
