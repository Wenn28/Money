# Saham

Pemantau lonjakan volume emiten BEI. Halaman statis (HTML/CSS/JS) membaca JSON hasil skrip Python.

Data asli dari Yahoo Finance (tidak resmi, tertunda ~10 menit). Daftar emiten dari file resmi IDX di `data/`.
Belum ada: CVD/OFI (butuh tick dan order book), broker summary (butuh sumber berlisensi), overlay UMA/HSC/suspensi.

## Jalankan di komputer sendiri

Satu kali (atau saat daftar saham IDX berubah):

```
uv run --no-project --python 3.12 --with openpyxl tools/universe.py 120   # rangking likuiditas, tulis data/universe.json
```

Sekali per hari bursa, sesudah tutup:

```
uv run --no-project --python 3.12 tools/refresh_baseline.py                # baseline 20 hari + Profil Volume
```

Tiap beberapa menit:

```
uv run --no-project --python 3.12 tools/fetch_snapshot.py                  # tulis web/data/*.json
uv run --no-project --python 3.12 python -m http.server 8080 -d web        # buka http://localhost:8080
```

JSON harus dibuka lewat server lokal, bukan klik ganda `index.html`.

## Online (GitHub + Firebase + Vercel)

Alur: GitHub Actions menarik Yahoo tiap ~5 menit, menulis satu dokumen `snapshot/latest` ke Firestore. Halaman statis di Vercel
membaca dokumen itu setelah login Google. Data tidak pernah ikut ke Vercel (`.vercelignore`) atau repo (`.gitignore`).

1. Firebase Console: buat proyek, aktifkan Firestore (mode produksi) dan Authentication > Sign-in method > Google.
2. Authentication > Settings > Authorized domains: tambahkan domain Vercel-mu.
3. Isi daftar email di `firestore.rules` (ganti dua placeholder), lalu deploy aturan: `firebase deploy --only firestore:rules`.
4. Project settings > Your apps > Web app: salin config ke `web/firebase-config.js`.
5. Project settings > Service accounts > Generate new private key. Isi file JSON itu disimpan sebagai GitHub Secret `FIREBASE_SERVICE_ACCOUNT`. Jangan commit file itu.
6. Push repo GitHub (privat). Jalankan workflow `data` sekali lewat tab Actions (workflow_dispatch) untuk mengisi snapshot pertama.
7. Vercel: import repo. Biarkan Framework "Other"; `vercel.json` sudah mengarahkan output ke `web`.

Workflow, login, dan pembacaan Firestore belum pernah dijalankan di proyek nyata.

## Tes engine

```
cd backend && uv run --no-project --python 3.12 --with pytest pytest -q
```

## Isi

- `backend/app/engines/`: RVOL, order flow, Delta HHI, dispatcher alert.
- `tools/`: `yahoo.py`, `universe.py`, `refresh_baseline.py`, `fetch_snapshot.py`. `generate_data.py` membuat data simulasi (untuk demo broker/CVD/OFI).
- `web/`: antarmuka. `web/data/` hasil skrip.
- `db/`, `docker-compose.yml`, `frontend/`: rancangan lama, tidak dipakai.
- `GLOSSARY.md`: istilah domain.
