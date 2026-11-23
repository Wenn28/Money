"""Snapshot RVOL asli: bar 1 menit hari bursa terakhir dari Yahoo + baseline/profil -> web/data/*.json.
Alert dihitung ulang dengan memutar seluruh hari ini, jadi hasilnya deterministik tanpa state tersimpan.

Jalankan tiap ~5 menit di jam bursa: uv run --no-project --python 3.12 tools/fetch_snapshot.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "backend"))
from app.engines import alert_dispatcher as ad  # noqa: E402
from app.engines import rvol_engine as rv  # noqa: E402
from yahoo import WIB, ambil_chart  # noqa: E402

DATA, OUT = ROOT / "data", ROOT / "web" / "data"
LANGKAH = 5  # menit antar titik seri dan evaluasi alert


def baca(nama: str):
    return json.loads((DATA / nama).read_text(encoding="utf-8"))


def jam_dari_menit(hari: date, m: int) -> datetime:
    """Kebalikan rv.menit_sesi: tambahkan jeda istirahat (90 menit Sen-Kam, 150 menit Jumat)."""
    sesi2, jeda = (150, 150) if hari.weekday() == 4 else (180, 90)
    return datetime(hari.year, hari.month, hari.day, 9, 0, tzinfo=WIB) + timedelta(minutes=m + (jeda if m >= sesi2 else 0))


def olah(args):
    """Bar hari terakhir -> (ringkasan, detail, kandidat alert). None bila data tidak cukup."""
    e, bar, harian, profil = args
    if not bar:
        return None
    hari = bar[-1]["ts"].date()
    bar = [b for b in bar if b["ts"].date() == hari]
    # baseline: 20 hari bursa PENUH sebelum hari ini, dari volume harian Yahoo
    sebelum = [v for d, v in harian if date.fromisoformat(d) < hari][-20:]
    if len(sebelum) < 20:
        return None
    trimmed, median = rv.baseline_trimmed_mean(sebelum), rv.baseline_median(sebelum)
    f = profil[rv.jenis_hari(hari)]

    kumulatif = []  # (menit sesi, v_cum, nilai_cum) di akhir tiap bar dalam sesi
    v = n = 0.0
    for b in bar:
        v += b["volume"]
        n += b["volume"] * b["close"]
        m = rv.menit_sesi(b["ts"])
        if m is not None:
            kumulatif.append((m, v, n))
    if not kumulatif:
        return None

    def pada(m: int):
        ke = [k for k in kumulatif if k[0] <= m]
        return ke[-1] if ke else None

    akhir_m = kumulatif[-1][0]
    titik = list(range(LANGKAH - 1, akhir_m, LANGKAH)) + [akhir_m]
    seri_m, seri_r, langkah = [], [], []
    for m in titik:
        k = pada(m)
        if k is None:
            continue
        rr = rv.rvol_norm(k[1], trimmed, rv.fraksi_kumulatif(f, m))
        seri_m.append(m)
        seri_r.append(None if rr is None else round(rr, 3))
        langkah.append((m, k[1], k[2], rr))

    _, v_cum, nilai, rvol = langkah[-1]
    harga = bar[-1]["close"]
    risiko = [{"jenis": "FCA_X", "nilai_pct": None}] if e["papan_catat"] == "PEMANTAUAN_KHUSUS" else []
    lencana = [ad.lencana(r["jenis"], r["nilai_pct"]) for r in risiko]
    kandidat = [
        ad.AlertEvent(jam_dari_menit(hari, m), e["kode"], "GABUNGAN", rr, nl, None, None, lencana)
        for m, _, nl, rr in langkah if rv.is_lonjakan(rr, nl)
    ]
    ringkas = {
        "kode": e["kode"], "nama": e["nama"], "papan_catat": e["papan_catat"], "harga": harga, "v_cum": round(v_cum),
        "nilai": round(nilai), "baseline": round(trimmed), "rvol": None if rvol is None else round(rvol, 3),
        "cvd": None, "ofi": None, "risiko": risiko, "status_5h": None, "lonjakan": rv.is_lonjakan(rvol, nilai),
    }
    detail = {
        "kode": e["kode"], "baseline_trimmed": round(trimmed), "baseline_median": round(median),
        "seri": {"menit": seri_m, "rvol": seri_r}, "broker": None,
    }
    return ringkas, detail, kandidat, bar[-1]["ts"], hari


def main() -> None:
    master = {e["kode"]: e for e in baca("emiten_master.json")}
    universe = [u["kode"] for u in baca("universe.json")]
    harian, profil = baca("baseline.json")["harian"], baca("profil.json")
    with ThreadPoolExecutor(max_workers=4) as pool:
        bars = list(pool.map(lambda k: ambil_chart(k, "1m", "1d"), universe))
        hasil = [olah((master[k], b, harian.get(k, []), profil)) for k, b in zip(universe, bars)]
    ok = [h for h in hasil if h]
    if not ok:
        raise SystemExit("tidak ada data yang bisa diolah")
    hari = max(h[4] for h in ok)
    ok = [h for h in ok if h[4] == hari]  # buang emiten dengan bar hari lain (tidak ada trade hari ini)
    terbaru = max(h[3] for h in ok)

    (OUT / "emiten").mkdir(parents=True, exist_ok=True)
    for f in (OUT / "emiten").glob("*.json"):
        f.unlink()
    kandidat = []
    for s, d, k, _, _ in ok:
        kandidat += k
        (OUT / "emiten" / f"{s['kode']}.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")

    terkirim: list[dict] = []

    async def catat(e: ad.AlertEvent, pesan: str) -> None:
        terkirim.append({"ts": e.ts.replace(tzinfo=None).isoformat(timespec="minutes"), "kode": e.kode, "rvol": round(e.rvol, 2), "pesan": pesan})

    async def putar() -> None:
        d = ad.AlertDispatcher(ad.StoreMemori(), [catat])
        for e in sorted(kandidat, key=lambda x: (x.ts, x.kode)):
            await d.dispatch(e)

    asyncio.run(putar())
    meta = {
        "simulasi": False, "snapshot": terbaru.replace(tzinfo=None).isoformat(timespec="minutes"), "tanggal": hari.isoformat(),
        "sumber": "Yahoo Finance (tertunda sekitar 10 menit)", "baseline_metode": "TRIMMED_MEAN",
        "min_rvol": rv.MIN_RVOL, "min_nilai_idr": rv.MIN_NILAI_IDR, "disclaimer": ad.DISCLAIMER, "jumlah_universe": len(universe),
        "punya_orderflow": False, "punya_broker": False, "risiko_tersedia": ["FCA_X"],
    }
    (OUT / "screener.json").write_text(json.dumps({"meta": meta, "emiten": [h[0] for h in ok]}, separators=(",", ":")), encoding="utf-8")
    (OUT / "alerts.json").write_text(json.dumps(terkirim, separators=(",", ":")), encoding="utf-8")
    print(f"{hari} sampai {terbaru:%H:%M}: {len(ok)}/{len(universe)} emiten, {len(terkirim)} alert, lonjakan saat ini: {sum(h[0]['lonjakan'] for h in ok)}")


if __name__ == "__main__":
    main()
