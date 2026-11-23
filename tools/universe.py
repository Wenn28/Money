"""Baca daftar saham resmi IDX (xlsx), rangking likuiditas dari Yahoo, tulis data/emiten_master.json dan data/universe.json.

Jalankan: uv run --no-project --python 3.12 --with openpyxl tools/universe.py [jumlah_teratas]
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from yahoo import ambil_chart  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SUMBER = next((ROOT / "data").glob("Daftar Saham*.xlsx"))
TOP = int(sys.argv[1]) if len(sys.argv) > 1 else 120
MIN_HARI = 20
BULAN = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Mei": 5, "Jun": 6, "Jul": 7, "Agt": 8, "Sep": 9, "Okt": 10, "Nov": 11, "Des": 12}
PAPAN = {"Utama": "UTAMA", "Pengembangan": "PENGEMBANGAN", "Akselerasi": "AKSELERASI", "Ekonomi Baru": "EKONOMI_BARU", "Pemantauan Khusus": "PEMANTAUAN_KHUSUS"}


def baca_daftar() -> list[dict]:
    ws = openpyxl.load_workbook(SUMBER, read_only=True).active
    baris = list(ws.iter_rows(values_only=True))
    assert baris[0][:6] == ("No", "Kode", "Nama Perusahaan", "Tanggal Pencatatan", "Saham", "Papan Pencatatan"), baris[0]
    hasil = []
    for _, kode, nama, tgl, saham, papan in baris[1:]:
        h, b, t = tgl.split()
        hasil.append({
            "kode": kode.strip(), "nama": nama.strip(), "tanggal_pencatatan": datetime(int(t), BULAN[b], int(h)).date().isoformat(),
            "saham": int(str(saham).replace(".", "")), "papan_catat": PAPAN[papan.strip()],
        })
    return hasil


def likuiditas(e: dict) -> tuple[str, float | None, int]:
    bar = ambil_chart(e["kode"], "1d", "3mo")
    if not bar:
        return e["kode"], None, 0
    # bar hari ini bisa belum lengkap, jadi 20 hari penuh diambil dari yang sebelumnya
    hari = [b for b in bar if b["volume"] > 0][-21:-1]
    if len(hari) < MIN_HARI:
        return e["kode"], None, len(hari)
    return e["kode"], sum(b["volume"] * b["close"] for b in hari) / len(hari), len(hari)


def main() -> None:
    daftar = baca_daftar()
    kode_unik = {e["kode"] for e in daftar}
    assert len(kode_unik) == len(daftar), "kode ganda di daftar"
    print(f"{len(daftar)} emiten dibaca dari {SUMBER.name}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        hasil = list(pool.map(likuiditas, daftar))
    ok = {k: v for k, v, _ in hasil if v is not None}
    gagal = [(k, n) for k, v, n in hasil if v is None]
    print(f"Yahoo ok: {len(ok)}, tanpa data cukup/gagal: {len(gagal)}")
    teratas = sorted(ok, key=ok.get, reverse=True)[:TOP]
    out = ROOT / "data"
    (out / "emiten_master.json").write_text(json.dumps(daftar, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "universe.json").write_text(
        json.dumps([{"kode": k, "nilai_rata_20h": round(ok[k])} for k in teratas], indent=1), encoding="utf-8"
    )
    print("10 teratas:", ", ".join(f"{k} {ok[k] / 1e9:,.1f}M" for k in teratas[:10]))
    print("tanpa data (contoh):", gagal[:8])


if __name__ == "__main__":
    main()
