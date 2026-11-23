"""Kirim snapshot (web/data) ke Firestore sebagai satu dokumen snapshot/latest.

Perlu env FIREBASE_SERVICE_ACCOUNT (isi JSON service account). Tanpa itu, pakai --dry untuk cek ukuran saja.
Jalankan: uv run --no-project --python 3.12 --with firebase-admin tools/publish_firestore.py [--dry]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "web" / "data"
BATAS_BYTE = 900_000  # batas dokumen Firestore 1 MiB; sisakan ruang untuk overhead


def susun() -> dict:
    layar = json.loads((DATA / "screener.json").read_text(encoding="utf-8"))
    detail = {}
    for f in (DATA / "emiten").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        # seri disimpan sebagai string agar jumlah entri indeks per dokumen tetap kecil
        detail[d["kode"]] = {
            "baseline_trimmed": d["baseline_trimmed"],
            "baseline_median": d["baseline_median"],
            "menit": ",".join(str(x) for x in d["seri"]["menit"]),
            "rvol": ",".join("" if x is None else str(x) for x in d["seri"]["rvol"]),
        }
    return {
        "screener": layar,
        "alerts": json.loads((DATA / "alerts.json").read_text(encoding="utf-8")),
        "detail": detail,
    }


def main() -> None:
    payload = susun()
    ukuran = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    print(f"{len(payload['screener']['emiten'])} emiten, {len(payload['alerts'])} alert, {ukuran / 1024:.0f} KiB")
    if ukuran > BATAS_BYTE:
        raise SystemExit(f"dokumen {ukuran} byte melewati batas {BATAS_BYTE}; kurangi universe atau pecah dokumen")
    if "--dry" in sys.argv:
        return
    import firebase_admin
    from firebase_admin import credentials, firestore

    firebase_admin.initialize_app(credentials.Certificate(json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"])))
    firestore.client().collection("snapshot").document("latest").set({**payload, "diperbarui": firestore.SERVER_TIMESTAMP})
    print("terkirim ke snapshot/latest")


if __name__ == "__main__":
    main()
