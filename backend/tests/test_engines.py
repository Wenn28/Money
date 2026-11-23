import asyncio
from datetime import datetime

import pytest

from app.engines import alert_dispatcher as ad
from app.engines import broker_hhi_engine as bh
from app.engines import orderflow_engine as of
from app.engines import rvol_engine as rv

SENIN = datetime(2026, 11, 23)  # Senin
JUMAT = datetime(2026, 11, 20)


# --- RVOL ---------------------------------------------------------------

def test_baseline_kebal_outlier_sma_tidak():
    vol = [100.0] * 18 + [10_000.0, 1.0]
    assert rv.baseline_trimmed_mean(vol) == 100.0
    assert rv.baseline_median(vol) == 100.0
    assert sum(vol) / len(vol) == pytest.approx(590.05)  # SMA 20 hari rusak oleh outlier


def test_rvol_tepat_3_5_memicu_dengan_baseline_trimmed():
    baseline = rv.baseline_trimmed_mean([100_000.0] * 18 + [5_000_000.0, 1.0])
    f = 0.2
    rvol = rv.rvol_norm(70_000, baseline, f)
    assert rvol == pytest.approx(3.5)
    assert rv.is_lonjakan(rvol, 6e9)
    # SMA mentah (baseline 346k) tidak akan memicu pada volume yang sama
    assert not rv.is_lonjakan(rv.rvol_norm(70_000, 346_000, f), 6e9)


def test_rvol_di_bawah_ambang_dan_filter_likuiditas():
    assert not rv.is_lonjakan(rv.rvol_norm(69_990, 100_000, 0.2), 6e9)
    assert not rv.is_lonjakan(3.88, 4_999_999_999)  # RVOL lolos, nilai transaksi tidak


def test_rvol_ditolak_saat_fraksi_terlalu_dini_atau_baseline_nol():
    assert rv.rvol_norm(1_000, 100_000, 0.001) is None
    assert rv.rvol_norm(1_000, 0, 0.5) is None


def test_menit_sesi_senin_kamis_dan_jumat():
    t = lambda d, h, m: d.replace(hour=h, minute=m)
    assert rv.menit_sesi(t(SENIN, 9, 0)) == 0
    assert rv.menit_sesi(t(SENIN, 11, 59)) == 179
    assert rv.menit_sesi(t(SENIN, 12, 30)) is None
    assert rv.menit_sesi(t(SENIN, 13, 30)) == 180
    assert rv.menit_sesi(t(SENIN, 15, 49)) == 319
    assert rv.menit_sesi(t(SENIN, 15, 50)) is None
    assert rv.menit_sesi(t(JUMAT, 11, 29)) == 149
    assert rv.menit_sesi(t(JUMAT, 11, 30)) is None
    assert rv.menit_sesi(t(JUMAT, 14, 0)) == 150
    assert rv.menit_sesi(t(JUMAT, 15, 49)) == 259


# --- Order flow -----------------------------------------------------------

def test_lee_ready():
    assert of.lee_ready(101, 100, 102, None) == "U"  # tepat di tengah, tanpa tick sebelumnya
    assert of.lee_ready(102, 100, 102, 99) == "B"
    assert of.lee_ready(100, 100, 102, 99) == "S"
    assert of.lee_ready(101, 100, 102, 100) == "B"  # tengah, tick naik
    assert of.lee_ready(101, 100, 102, 102) == "S"  # tengah, tick turun
    assert of.lee_ready(101, 100, 102, 101, "B") == "B"  # zero-tick ikut sisi sebelumnya


def test_cvd_abaikan_netral():
    assert of.cvd([("B", 30.0), ("S", 10.0), ("U", 99.0)]) == 20.0


def _book(bid0=(100, 10), ask0=(102, 8)):
    # Hanya level 1 yang bisa diubah; level 2-5 tetap agar kontribusinya nol.
    return of.Book(
        (bid0[0], 99, 98, 97, 96), (bid0[1], 5, 5, 5, 5),
        (ask0[0], 103, 104, 105, 106), (ask0[1], 5, 5, 5, 5),
    )


def test_ofi_bid_naik_dan_level_lain_tetap():
    assert of.ofi(_book(), _book(bid0=(101, 5))) == 5  # harga bid naik: + volume bid baru
    assert of.ofi(_book(), _book()) == 0  # tidak ada perubahan


def test_ofi_bid_turun_negatif():
    assert of.ofi(_book(), _book(bid0=(99, 5))) == -10  # harga bid turun: - volume bid lama


def test_net_asing():
    assert of.net_asing(10.0, 4.0) == 6.0


# --- Delta HHI ------------------------------------------------------------

def _baris(kode, net):
    return bh.BrokerRow(kode, 1, max(net, 0), 1, max(-net, 0))


def test_delta_hhi_dan_big_accumulation():
    # Pembeli bersih 60/30/10 -> HHI 4600. Penjual bersih 4x25 -> HHI 2500.
    rows = [_baris("AA", 60), _baris("BB", 30), _baris("CC", 10)]
    rows += [_baris(k, -25) for k in ("DD", "EE", "FF", "GG")]
    s = bh.hitung_skor(rows)
    assert s.hhi_beli == pytest.approx(4600)
    assert s.hhi_jual == pytest.approx(2500)
    assert s.delta_hhi == pytest.approx(2100)
    assert (s.n_net_buyer, s.n_net_seller) == (3, 4)
    assert s.rasio_buyer_seller == pytest.approx(0.75)
    assert s.top_beli_pct == pytest.approx((60, 100, 100))
    assert s.status == "BIG_ACCUMULATION"


def test_big_distribution_cermin():
    rows = [_baris(k, 25) for k in ("DD", "EE", "FF", "GG")]
    rows += [_baris("AA", -60), _baris("BB", -30), _baris("CC", -10)]
    s = bh.hitung_skor(rows)
    assert s.delta_hhi == pytest.approx(-2100)
    assert s.status == "BIG_DISTRIBUTION"


def test_netral_saat_sebaran_seimbang():
    rows = [_baris(f"B{i}", 10) for i in range(5)] + [_baris(f"S{i}", -10) for i in range(5)]
    s = bh.hitung_skor(rows)
    assert s.delta_hhi == pytest.approx(0)
    assert s.status == "NEUTRAL"


def test_broker_net_nol_dan_tanpa_penjual_tidak_error():
    s = bh.hitung_skor([_baris("AA", 0), _baris("BB", 50)])
    assert (s.n_net_buyer, s.n_net_seller, s.hhi_jual) == (1, 0, 0.0)
    assert bh.hitung_skor([]).status == "NEUTRAL"


def test_harga_rata_rata_vs_vwap():
    r = bh.BrokerRow("AA", 100, 10_500, 0, 0)
    assert r.avg_beli == 105 and r.avg_jual is None
    assert bh.selisih_harga_vs_vwap(r.avg_beli, 100) == pytest.approx(5)
    assert bh.selisih_harga_vs_vwap(None, 100) is None


# --- Alert dispatcher -----------------------------------------------------

def _event(menit=0, rvol=3.88, **kw):
    return ad.AlertEvent(
        ts=SENIN.replace(hour=10, minute=menit), kode="BBCA", papan="REGULER", rvol=rvol,
        nilai_kumulatif=8e9, cvd=18.4e9, ofi=1.0, **kw,
    )


def test_format_pesan_sesuai_contoh_dan_patuh():
    pesan = ad.format_pesan(_event(lencana_risiko=["[FCA-X]", ad.lencana("HSC", 92.5)]))
    assert pesan.splitlines()[0] == (
        "ANOMALI VOLUME TERDETEKSI: BBCA | RVOL 3,88x | CVD +Rp18,4M | OFI Positif | Status: [REGULER]"
        " [FCA-X] [HSC >= 92,5%]"
    )
    assert pesan.endswith(ad.DISCLAIMER)
    assert "—" not in pesan


@pytest.mark.parametrize("kata", ["BELI SEKARANG", "jual", "TARGET HARGA 5000", "Buy now"])
def test_kata_terlarang_ditolak(kata):
    with pytest.raises(ValueError):
        ad.pastikan_patuh(f"BBCA {kata}")


def test_rupiah_singkat():
    assert ad.rupiah_singkat(-2.5e12) == "-Rp2,5T"
    assert ad.rupiah_singkat(950e6) == "+Rp950,0Jt"
    assert ad.rupiah_singkat(500) == "+Rp500"


def test_cooldown_dan_naik_rvol_lagi():
    kirim: list[str] = []

    async def notif(_e, pesan):
        kirim.append(pesan)

    d = ad.AlertDispatcher(ad.StoreMemori(), [notif])

    async def jalan():
        assert await d.dispatch(_event(0, 3.6))  # alert pertama
        assert await d.dispatch(_event(5, 4.0)) is None  # dalam cooldown, naik < 1,0x
        assert await d.dispatch(_event(6, 4.6))  # naik 1,0x dari 3,6 -> lolos cooldown
        assert await d.dispatch(_event(15, 4.7)) is None  # 9 menit sejak alert 4,6
        assert await d.dispatch(_event(21, 4.7))  # 15 menit sejak 4,6 -> cooldown habis

    asyncio.run(jalan())
    assert len(kirim) == 3


def test_kanal_gagal_tidak_menahan_kanal_lain():
    diterima: list[str] = []

    async def rusak(_e, _p):
        raise RuntimeError("telegram down")

    async def sehat(_e, pesan):
        diterima.append(pesan)

    d = ad.AlertDispatcher(ad.StoreMemori(), [rusak, sehat])
    asyncio.run(d.dispatch(_event()))
    assert len(diterima) == 1
