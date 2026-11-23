"""Tarik volume harian (3 bulan) dan bar 1 menit (5 hari) dari Yahoo untuk universe.
Tulis data/baseline.json (volume harian per emiten) dan data/profil.json (Profil Volume F(t)).

Jalankan sekali per hari bursa, sesudah penutupan: uv run --no-project --python 3.12 tools/refresh_baseline.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "backend"))
from app.engines import rvol_engine as rv  # noqa: E402
from yahoo import WIB, ambil_chart  # noqa: E402

PANJANG = {"SEN_KAM": 320, "JUM": 260}


def tarik(kode: str):
    return kode, ambil_chart(kode, "1d", "3mo"), ambil_chart(kode, "1m", "5d")


def main() -> None:
    universe = [u["kode"] for u in json.loads((ROOT / "data" / "universe.json").read_text())]
    with ThreadPoolExecutor(max_workers=4) as pool:
        hasil = list(pool.map(tarik, universe))

    harian, tot, tambah, terakhir = {}, defaultdict(float), {}, {}
    rasio = []
    for kode, daily, m1 in hasil:
        if daily:
            harian[kode] = [[b["ts"].date().isoformat(), b["volume"]] for b in daily if b["volume"] > 0][-30:]
        for b in m1 or []:
            hari = b["ts"].date()
            tot[hari] += b["volume"]
            terakhir[hari] = max(terakhir.get(hari, b["ts"]), b["ts"])
            m = rv.menit_sesi(b["ts"])
            if m is not None:
                tambah.setdefault(hari, [0.0] * PANJANG[rv.jenis_hari(hari)])[m] += b["volume"]
        if daily and m1:  # cek kewajaran: jumlah bar 1 menit vs bar harian hari penuh terakhir
            d = {b["ts"].date(): b["volume"] for b in daily}
            for hari in {b["ts"].date() for b in m1}:
                if d.get(hari):
                    rasio.append(sum(b["volume"] for b in m1 if b["ts"].date() == hari) / d[hari])

    profil, dipakai = {}, defaultdict(list)
    for hari, cum in tambah.items():
        if terakhir[hari].time() < datetime(2000, 1, 1, 15, 45).time():
            continue  # hari belum selesai, lewati
        total, acc, f = tot[hari], 0.0, []
        for v in cum:
            acc += v
            f.append(acc / total)
        profil.setdefault(rv.jenis_hari(hari), []).append(f)
        dipakai[rv.jenis_hari(hari)].append(hari.isoformat())
    for jenis in PANJANG:
        if jenis not in profil:
            raise SystemExit(f"tidak ada hari lengkap bertipe {jenis} dalam 5 hari terakhir")
    keluar = {
        "catatan": "Profil pasar gabungan (berbobot volume), bukan per emiten. Bar Yahoo tanpa lelang pembukaan.",
        "dibuat": datetime.now(WIB).isoformat(timespec="minutes"),
        "hari_dipakai": dipakai,
        **{j: [round(statistics.fmean(col), 5) for col in zip(*profil[j])] for j in PANJANG},
    }
    (ROOT / "data" / "profil.json").write_text(json.dumps(keluar), encoding="utf-8")
    (ROOT / "data" / "baseline.json").write_text(
        json.dumps({"dibuat": keluar["dibuat"], "harian": harian}, separators=(",", ":")), encoding="utf-8"
    )
    print(f"baseline: {len(harian)}/{len(universe)} emiten, profil dari hari: {dict(dipakai)}")
    print(f"F(akhir sesi) SEN_KAM={keluar['SEN_KAM'][-1]:.3f} JUM={keluar['JUM'][-1]:.3f}")
    if rasio:
        print(f"jumlah bar 1m / volume harian: median {statistics.median(rasio):.3f} (n={len(rasio)})")


if __name__ == "__main__":
    main()
