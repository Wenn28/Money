"""Membuat data SIMULASI (JSON) untuk web/ memakai engine Tahap 3. Semua angka sintetis.

Jalankan dari akar repo: uv run --no-project --python 3.12 tools/generate_data.py
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.engines import alert_dispatcher as ad  # noqa: E402
from app.engines import broker_hhi_engine as bh  # noqa: E402
from app.engines import orderflow_engine as of  # noqa: E402
from app.engines import rvol_engine as rv  # noqa: E402

OUT = ROOT / "web" / "data"
N_EMITEN, N_BROKER, HARI_HIST = 970, 88, 60
SNAPSHOT = datetime(2026, 11, 23, 10, 42)  # Senin, Sesi I
MENIT_SNAP = rv.menit_sesi(SNAPSHOT)
LANGKAH = list(range(5, MENIT_SNAP, 6)) + [MENIT_SNAP]
BROKERS = [a + b for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"][:N_BROKER]
rng = random.Random(20261123)


def profil_u(n: int = 320) -> list[float]:
    """F(t) bentuk U: ramai di pembukaan, setelah istirahat, dan penutupan."""
    w = [
        1 + 3 * math.exp(-m / 18) + 2.5 * math.exp(-(n - 1 - m) / 22) + (1.2 * math.exp(-(m - 180) / 12) if m >= 180 else 0)
        for m in range(n)
    ]
    total, acc, out = sum(w), 0.0, []
    for x in w:
        acc += x / total
        out.append(acc)
    return out


PROFIL = profil_u()


def tick_size(p: float) -> int:
    return 1 if p < 200 else 2 if p < 500 else 5 if p < 2000 else 10 if p < 5000 else 25


def bulat_harga(p: float) -> int:
    t = tick_size(p)
    return max(t, round(p / t) * t)


def smooth(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def simulasi_cvd(harga: int, v_cum: float, bias: float) -> float:
    t, prev_p, prev_s, trades = tick_size(harga), None, "U", []
    for _ in range(40):
        bid, ask = harga - t, harga + t
        p = ask if rng.random() < 0.5 + bias / 2 else bid
        s = of.lee_ready(p, bid, ask, prev_p, prev_s)
        trades.append((s, v_cum / 40 * rng.uniform(0.5, 1.5) * p))
        prev_p, prev_s = p, s
    return of.cvd(trades)


def simulasi_ofi(harga: int, v_cum: float, bias: float) -> float:
    t, unit = tick_size(harga), v_cum / 200

    def buku(bid0: int, ask0: int) -> of.Book:
        return of.Book(
            tuple(bid0 - t * j for j in range(5)), tuple(unit * rng.uniform(1, 3) for _ in range(5)),
            tuple(ask0 + t * j for j in range(5)), tuple(unit * rng.uniform(1, 3) for _ in range(5)),
        )

    geser = t if rng.random() < 0.5 + bias / 2 else -t
    return of.ofi(buku(harga - t, harga + t), buku(harga - t + geser, harga + t + geser))


def r(x: float, d: int = 2) -> float:
    return round(x, d)


def simulasi_broker(harga: int, base_vol: float, rezim: str) -> dict:
    aktif = rng.sample(BROKERS, rng.randint(18, 40))
    sb, ss = {"acc": (0.4, 4.0), "dist": (4.0, 0.4), "net": (8.0, 8.0)}[rezim]
    wb = [rng.gammavariate(sb, 1) + 1e-3 for _ in aktif]
    ws = [rng.gammavariate(ss, 1) + 1e-3 for _ in aktif]
    acc = {b: [0.0, 0.0, 0.0, 0.0] for b in aktif}  # beli_vol, beli_nilai, jual_vol, jual_nilai
    hasil = {}
    for d in range(1, HARI_HIST + 1):  # d=1 hari bursa terakhir
        p_d = harga * math.exp(rng.gauss(0, 0.015))
        nilai_hari = base_vol * p_d * rng.uniform(0.6, 1.4)
        for sisi, w in ((0, wb), (2, ws)):
            mentah = [x * rng.lognormvariate(0, 0.3) for x in w]
            skala = nilai_hari / sum(mentah)
            for b, m in zip(aktif, mentah):
                nilai = m * skala
                harga_b = p_d * (1 + rng.gauss(0, 0.003))
                acc[b][sisi] += nilai / harga_b
                acc[b][sisi + 1] += nilai
        if d in (1, 5, 20, 60):
            baris = [bh.BrokerRow(b, *v) for b, v in acc.items()]
            skor = bh.hitung_skor(baris)
            vwap = sum(x.beli_nilai for x in baris) / sum(x.beli_vol for x in baris)

            def ringkas(x: bh.BrokerRow) -> dict:
                return {
                    "broker": x.broker, "net_nilai": r(x.net_nilai, 0), "net_lot": r((x.beli_vol - x.jual_vol) / 100, 0),
                    "vs_vwap_beli": None if x.avg_beli is None else r(bh.selisih_harga_vs_vwap(x.avg_beli, vwap), 2),
                    "vs_vwap_jual": None if x.avg_jual is None else r(bh.selisih_harga_vs_vwap(x.avg_jual, vwap), 2),
                }

            urut = sorted(baris, key=lambda x: x.net_nilai, reverse=True)
            hasil[str(d)] = {
                "vwap": r(vwap), "hhi_beli": r(skor.hhi_beli, 1), "hhi_jual": r(skor.hhi_jual, 1),
                "delta_hhi": r(skor.delta_hhi, 1), "n_net_buyer": skor.n_net_buyer, "n_net_seller": skor.n_net_seller,
                "rasio": r(skor.rasio_buyer_seller, 2), "top_beli": [r(x, 1) for x in skor.top_beli_pct],
                "top_jual": [r(x, 1) for x in skor.top_jual_pct], "status": skor.status,
                "buyers": [ringkas(x) for x in urut[:5] if x.net_nilai > 0],
                "sellers": [ringkas(x) for x in urut[::-1][:5] if x.net_nilai < 0],
            }
    return hasil


def buat_emiten(i: int, kategori: str) -> tuple[dict, dict, list[ad.AlertEvent]]:
    kode = f"S{i + 1:03d}"
    if kategori == "anomali":
        base, harga = rng.lognormvariate(math.log(4e7), 0.5), max(500.0, rng.lognormvariate(math.log(2000), 0.6))
    elif kategori == "likuid_rendah":
        base, harga = 3e5, 80.0
    else:
        base, harga = rng.lognormvariate(math.log(5e6), 1.3), min(max(rng.lognormvariate(math.log(1200), 1.1), 50), 30000)
    harga = bulat_harga(harga)
    hist = [base * rng.lognormvariate(0, 0.25) for _ in range(20)]
    if rng.random() < 0.1:
        hist[rng.randrange(20)] *= 8  # outlier ekstrem, baseline trimmed harus kebal
    baseline, mediana = rv.baseline_trimmed_mean(hist), rv.baseline_median(hist)

    target = {
        "anomali": rng.uniform(3.7, 6.5), "likuid_rendah": rng.uniform(4.0, 6.0), "dekat": rng.uniform(2.8, 3.4),
    }.get(kategori, min(rng.lognormvariate(0, 0.3), 2.2))
    naik = kategori in ("anomali", "likuid_rendah", "dekat")
    mulai = rng.randint(35, 85)

    seri_menit, seri_rvol, langkah, v_prev = [], [], [], 0.0
    if kategori != "suspensi":
        for m in LANGKAH:
            level = 1 + (target - 1) * smooth((m - mulai) / (MENIT_SNAP - mulai)) if naik else target * (1 + rng.gauss(0, 0.04))
            f = rv.fraksi_kumulatif(PROFIL, m)
            v = max(baseline * f * level, v_prev)
            v_prev = v
            seri_menit.append(m)
            seri_rvol.append(r(rv.rvol_norm(v, baseline, f), 3))
            langkah.append((m, v, rv.rvol_norm(v, baseline, f)))

    bias = rng.choice([-1, 1]) * rng.uniform(0.3, 0.8) if kategori == "anomali" else rng.uniform(-0.2, 0.2)
    v_cum = v_prev
    cvd = simulasi_cvd(harga, v_cum, bias) if v_cum else 0.0
    ofi = simulasi_ofi(harga, v_cum, bias) if v_cum else 0.0

    risiko = []
    if kategori == "suspensi":
        risiko.append({"jenis": "SUSPENSI", "nilai_pct": None})
    if rng.random() < 0.05 or (kategori == "anomali" and rng.random() < 0.15):
        risiko.append({"jenis": "FCA_X", "nilai_pct": None})
    if rng.random() < 0.03 or (kategori == "anomali" and rng.random() < 0.2):
        risiko.append({"jenis": "UMA", "nilai_pct": None})
    if rng.random() < 0.015:
        risiko.append({"jenis": "HSC", "nilai_pct": r(rng.uniform(92.5, 99.0), 1)})
    fca = any(x["jenis"] == "FCA_X" for x in risiko)
    papan_catat = "PEMANTAUAN_KHUSUS" if fca else rng.choices(["UTAMA", "PENGEMBANGAN", "AKSELERASI"], [55, 32, 13])[0]

    rezim = rng.choice(["acc", "acc", "dist"]) if kategori == "anomali" else rng.choices(["acc", "dist", "net"], [6, 6, 88])[0]
    broker = simulasi_broker(harga, base, rezim)
    nego = r(base * harga * rng.uniform(0.5, 3), 0) if rng.random() < 0.1 else 0

    rvol = None if kategori == "suspensi" else rv.rvol_norm(v_cum, baseline, rv.fraksi_kumulatif(PROFIL, MENIT_SNAP))
    nilai = v_cum * harga
    lencana = [ad.lencana(x["jenis"], x["nilai_pct"]) for x in risiko]
    kandidat = [
        ad.AlertEvent(
            SNAPSHOT.replace(hour=9, minute=0) + timedelta(minutes=m), kode, "REGULER", rr, v * harga,
            cvd * v / v_cum, ofi * v / v_cum, lencana,
        )
        for m, v, rr in langkah if rv.is_lonjakan(rr, v * harga)
    ]
    ringkas = {
        "kode": kode, "nama": f"Emiten Simulasi {kode}", "papan_catat": papan_catat, "harga": harga,
        "v_cum": r(v_cum, 0), "nilai": r(nilai, 0), "baseline": r(baseline, 0), "rvol": None if rvol is None else r(rvol, 3),
        "cvd": r(cvd, 0), "ofi": r(ofi, 0), "risiko": risiko, "status_5h": broker["5"]["status"],
        "lonjakan": rv.is_lonjakan(rvol, nilai),
    }
    detail = {
        "kode": kode, "baseline_trimmed": r(baseline, 0), "baseline_median": r(mediana, 0), "negosiasi_nilai": nego,
        "seri": {"menit": seri_menit, "rvol": seri_rvol}, "broker": broker,
    }
    return ringkas, detail, kandidat


def main() -> None:
    (OUT / "emiten").mkdir(parents=True, exist_ok=True)
    ids = list(range(N_EMITEN))
    rng.shuffle(ids)
    kategori = {}
    for urut, jumlah in (("anomali", 14), ("likuid_rendah", 6), ("dekat", 8), ("suspensi", 10)):
        for _ in range(jumlah):
            kategori[ids.pop()] = urut

    ringkasan, kandidat = [], []
    for i in range(N_EMITEN):
        s, d, k = buat_emiten(i, kategori.get(i, "normal"))
        ringkasan.append(s)
        kandidat += k
        (OUT / "emiten" / f"{s['kode']}.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")

    terkirim: list[dict] = []

    async def catat(e: ad.AlertEvent, pesan: str) -> None:
        terkirim.append({"ts": e.ts.isoformat(timespec="minutes"), "kode": e.kode, "rvol": r(e.rvol, 2), "pesan": pesan})

    async def putar() -> None:
        d = ad.AlertDispatcher(ad.StoreMemori(), [catat])
        for e in sorted(kandidat, key=lambda x: (x.ts, x.kode)):
            await d.dispatch(e)

    asyncio.run(putar())
    meta = {
        "simulasi": True, "snapshot": SNAPSHOT.isoformat(timespec="minutes"), "baseline_metode": "TRIMMED_MEAN",
        "min_rvol": rv.MIN_RVOL, "min_nilai_idr": rv.MIN_NILAI_IDR, "disclaimer": ad.DISCLAIMER,
    }
    (OUT / "screener.json").write_text(json.dumps({"meta": meta, "emiten": ringkasan}, separators=(",", ":")), encoding="utf-8")
    (OUT / "alerts.json").write_text(json.dumps(terkirim, separators=(",", ":")), encoding="utf-8")
    print(f"{len(ringkasan)} emiten, {len(terkirim)} alert, lonjakan saat ini: {sum(x['lonjakan'] for x in ringkasan)}")


if __name__ == "__main__":
    main()
