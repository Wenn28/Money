# Saham

Aplikasi pemantau saham BEI (IDX) yang menandai emiten dengan lonjakan volume tidak biasa, untuk investor ritel.

## Language

**Emiten**:
Perusahaan yang sahamnya tercatat di BEI.
_Avoid_: Saham (untuk perusahaan), ticker, stock

**Hari Bursa**:
Hari saat BEI membuka perdagangan. Akhir pekan dan hari libur bursa bukan Hari Bursa.
_Avoid_: Hari kerja, trading day

**Volume Harian**:
Total lembar saham sebuah Emiten yang diperdagangkan dalam satu hari bursa.
_Avoid_: Transaksi, turnover

**Volume Berjalan**:
Volume Harian yang terkumpul sejak pembukaan bursa hari ini sampai pengecekan terakhir.
_Avoid_: Volume realtime, volume intraday

**Baseline Harian**:
Volume Harian penuh pada Hari Bursa terakhir sebelum hari ini.
_Avoid_: Baseline (tanpa kata sifat), normal

**Baseline 20 Hari**:
Rata-rata terpangkas (10% tertinggi dan 10% terendah dibuang) Volume Harian Pasar Reguler selama 20 Hari Bursa terakhir, dengan median sebagai alternatif. Pembanding untuk Volume Berjalan.
_Avoid_: Rata-rata, kebiasaan, SMA 20

**Profil Volume**:
Fraksi kumulatif Volume Harian sebuah Emiten yang biasanya sudah terjadi pada menit tertentu sesi, terpisah untuk Senin sampai Kamis dan Jumat.
_Avoid_: Kurva volume, pola intraday

**RVOL**:
Volume Berjalan dibagi hasil kali Baseline 20 Hari dan Profil Volume pada menit yang sama.
_Avoid_: Rasio volume, relative volume

**Lonjakan Volume**:
Kondisi saat RVOL sebuah Emiten mencapai 3,5 atau lebih dan nilai transaksi kumulatifnya melewati Ambang Likuiditas.
_Avoid_: Anomali, ledakan, spike

**Ambang Likuiditas**:
Nilai transaksi kumulatif minimal (dalam rupiah) agar Lonjakan Volume dihitung sebagai Alert.
_Avoid_: Filter, batas minimum

**Alert**:
Catatan di aplikasi bahwa sebuah Emiten mengalami Lonjakan Volume pada hari tertentu.
_Avoid_: Notifikasi, peringatan

## Broker

**Broker**:
Anggota bursa (perusahaan sekuritas) yang mengeksekusi order jual-beli, dikenali dengan kode dua huruf.
_Avoid_: Sekuritas, bandar

**Net Lot**:
Lot beli dikurangi lot jual sebuah Broker pada satu Emiten dalam satu Hari Bursa. Satu lot sama dengan 100 lembar.
_Avoid_: Selisih, net volume

**Akumulasi**:
Keadaan saat Net Lot sebuah Broker pada satu Emiten positif.
_Avoid_: Penumpukan, borong

**Distribusi**:
Keadaan saat Net Lot sebuah Broker pada satu Emiten negatif.
_Avoid_: Pembuangan, guyur

**Status Akumulasi**:
Penilaian satu Emiten dari sebaran Broker pembeli dan penjual bersih: Akumulasi Besar, Akumulasi Moderat, Netral, Distribusi Moderat, atau Distribusi Besar. Berbeda dari Akumulasi dan Distribusi, yang melekat pada satu Broker.
_Avoid_: Skor, sinyal

**Harga Rata-rata Beli**:
Harga per lembar rata-rata tertimbang dari semua pembelian sebuah Broker pada satu Emiten dalam satu Hari Bursa.
_Avoid_: Avg, rata-rata harga
