"use strict";

const STATUS = {
  BIG_ACCUMULATION: ["Akumulasi Besar", "pos", 0],
  MODERATE_ACCUMULATION: ["Akumulasi Moderat", "pos", 1],
  NEUTRAL: ["Netral", "", 2],
  DISTRIBUTION: ["Distribusi Moderat", "neg", 3],
  BIG_DISTRIBUTION: ["Distribusi Besar", "neg", 4],
};
const PAPAN = { UTAMA: "Utama", PENGEMBANGAN: "Pengembangan", AKSELERASI: "Akselerasi", EKONOMI_BARU: "Ekonomi Baru", PEMANTAUAN_KHUSUS: "Pem. Khusus" };
const TANPA_STATUS = ["-", "", 2];
const ROW_OVERSCAN = 8;

const $ = (s) => document.querySelector(s);
const state = { rows: [], semua: [], sort: { key: "rvol", dir: -1 }, dipilih: null, periode: "5", meta: null };
const cacheDetail = new Map();

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (x, d = 0) => new Intl.NumberFormat("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d }).format(x);

function rupiah(x) {
  const tanda = x >= 0 ? "+" : "-";
  const a = Math.abs(x);
  for (const [batas, suf] of [[1e12, "T"], [1e9, "M"], [1e6, "Jt"]]) {
    if (a >= batas) return `${tanda}Rp${fmt(a / batas, 1)}${suf}`;
  }
  return `${tanda}Rp${fmt(a, 0)}`;
}
const rupiahPolos = (x) => rupiah(Math.abs(x)).replace("+", "");
const persen = (x) => (x == null ? "-" : `${x >= 0 ? "+" : "-"}${fmt(Math.abs(x), 2)}%`);
const jam = (menit) => {
  const m = 9 * 60 + menit;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};

function lencana(r) {
  if (r.jenis === "FCA_X") return "[FCA-X]";
  if (r.jenis === "HSC") return `[HSC >= ${fmt(r.nilai_pct, 1)}%]`;
  return `[${r.jenis}]`;
}
const lencanaHtml = (rs) => rs.map((r) => `<span class="lencana">${esc(lencana(r))}</span>`).join("");
const arahOfi = (x) => (x == null ? ["-", ""] : x > 0 ? ["Positif", "pos"] : x < 0 ? ["Negatif", "neg"] : ["Netral", ""]);
const statusDari = (s) => (s ? STATUS[s] : TANPA_STATUS);

async function ambil(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

/* ---------- Screener ---------- */

function tampilkanStatus(html) {
  const el = $("#status");
  el.innerHTML = html;
  $("#scroll").hidden = Boolean(html);
}

function terapkanFilter() {
  const q = $("#q").value.trim().toUpperCase();
  const papan = $("#papan").value;
  const risiko = $("#risiko").value;
  const hanya = $("#lonjakan").checked;
  const { key, dir } = state.sort;
  const nilai = (e) => (key === "status_5h" ? (e.status_5h ? STATUS[e.status_5h][2] : null) : e[key]);

  state.rows = state.semua
    .filter((e) => (!q || e.kode.includes(q)) && (!papan || e.papan_catat === papan) && (!hanya || e.lonjakan))
    .filter((e) => !risiko || (risiko === "TANPA" ? e.risiko.length === 0 : e.risiko.some((r) => r.jenis === risiko)))
    .sort((a, b) => {
      const x = nilai(a), y = nilai(b);
      if (x == null) return y == null ? 0 : 1; // nilai kosong selalu di bawah
      if (y == null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * dir;
    });

  $("#hitung").textContent = `${fmt(state.rows.length)} dari ${fmt(state.semua.length)} emiten`;
  for (const th of document.querySelectorAll("thead th[data-key]")) {
    th.setAttribute("aria-sort", th.dataset.key === key ? (dir > 0 ? "ascending" : "descending") : "none");
  }
  $("#scroll").scrollTop = 0;
  if (state.rows.length === 0) {
    tampilkanStatus('Tidak ada emiten yang cocok dengan filter.<br><button type="button" id="reset">Atur ulang filter</button>');
    return;
  }
  tampilkanStatus("");
  gambarBaris();
}

function barisHtml(e) {
  const [ofiTeks, ofiKelas] = arahOfi(e.ofi);
  const [stTeks, stKelas] = statusDari(e.status_5h);
  const cls = [e.lonjakan ? "lonjakan" : "", e.kode === state.dipilih ? "dipilih" : ""].join(" ").trim();
  return `<tr data-kode="${esc(e.kode)}" class="${cls}"${e.kode === state.dipilih ? ' aria-current="true"' : ""}>
    <td><button type="button" class="kode" data-kode="${esc(e.kode)}">${esc(e.kode)}</button>${e.lonjakan ? '<span class="tag">LONJAKAN</span>' : ""}</td>
    <td>${esc(PAPAN[e.papan_catat])}</td>
    <td class="num">${fmt(e.harga)}</td>
    <td class="num">${e.rvol == null ? "-" : fmt(e.rvol, 2) + "x"}</td>
    <td class="num">${rupiahPolos(e.nilai)}</td>
    <td class="num ${e.cvd > 0 ? "pos" : e.cvd < 0 ? "neg" : ""}">${e.cvd == null ? "-" : rupiah(e.cvd)}</td>
    <td class="${ofiKelas}">${ofiTeks}</td>
    <td class="${stKelas}">${stTeks}</td>
    <td>${lencanaHtml(e.risiko)}</td></tr>`;
}

function gambarBaris() {
  const sc = $("#scroll");
  const rowH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--row-h")) || 40;
  const kepala = sc.querySelector("thead").offsetHeight;
  const awal = Math.max(0, Math.floor((sc.scrollTop - kepala) / rowH) - ROW_OVERSCAN);
  const akhir = Math.min(state.rows.length, Math.ceil((sc.scrollTop + sc.clientHeight) / rowH) + ROW_OVERSCAN);
  const spacer = (n) => (n > 0 ? `<tr class="spacer" aria-hidden="true"><td colspan="9" style="height:${n}px"></td></tr>` : "");
  $("#isi").innerHTML =
    spacer(awal * rowH) + state.rows.slice(awal, akhir).map(barisHtml).join("") + spacer((state.rows.length - akhir) * rowH);
}

/* ---------- Detail ---------- */

function grafikRvol(seri) {
  const W = 420, H = 150, kiri = 34, kanan = 10, atas = 10, bawah = 22;
  const pts = seri.menit.map((m, i) => [m, seri.rvol[i]]).filter(([, v]) => v != null);
  if (pts.length < 2) return '<p class="muted">Tidak ada seri RVOL (emiten tidak diperdagangkan).</p>';
  const ymax = Math.max(4.5, ...pts.map(([, v]) => v)) * 1.08;
  const x0 = pts[0][0], x1 = pts[pts.length - 1][0];
  const X = (m) => kiri + ((m - x0) / (x1 - x0)) * (W - kiri - kanan);
  const Y = (v) => H - bawah - (v / ymax) * (H - atas - bawah);
  const garis = pts.map(([m, v]) => `${X(m).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const akhir = pts[pts.length - 1][1];
  return `<svg class="grafik" viewBox="0 0 ${W} ${H}" role="img" aria-label="RVOL dari ${fmt(pts[0][1], 2)}x pada ${jam(x0)} menjadi ${fmt(akhir, 2)}x pada ${jam(x1)}. Ambang 3,5x.">
    <line class="ambang" x1="${kiri}" x2="${W - kanan}" y1="${Y(3.5)}" y2="${Y(3.5)}"/>
    <text x="${kiri - 4}" y="${Y(3.5) + 3}" text-anchor="end">3,5x</text>
    <text x="${kiri - 4}" y="${Y(0) + 3}" text-anchor="end">0</text>
    <polyline class="garis" points="${garis}"/>
    <text x="${kiri}" y="${H - 6}">${jam(x0)}</text>
    <text x="${W - kanan}" y="${H - 6}" text-anchor="end">${jam(x1)}</text></svg>`;
}

function barisBroker(b, kelas, maks) {
  return `<tr><td>${esc(b.broker)}<span class="bar-w ${kelas}"><i style="width:${(Math.abs(b.net_nilai) / maks) * 100}%"></i></span></td>
    <td class="num">${rupiahPolos(b.net_nilai)}</td><td class="num">${persen(kelas === "p" ? b.vs_vwap_beli : b.vs_vwap_jual)}</td></tr>`;
}

function sisiBroker(judul, daftar, kelas, maks) {
  const isi = daftar.length ? daftar.map((b) => barisBroker(b, kelas, maks)).join("") : '<tr><td colspan="3" class="muted">Tidak ada</td></tr>';
  return `<div><h3>${judul}</h3><table class="mini"><thead><tr><th scope="col">Broker</th><th scope="col" class="num">Net</th><th scope="col" class="num">vs VWAP</th></tr></thead><tbody>${isi}</tbody></table></div>`;
}

function matriksBroker(d) {
  const p = d.broker[state.periode];
  const maks = Math.max(1, ...[...p.buyers, ...p.sellers].map((b) => Math.abs(b.net_nilai)));
  const [stTeks, stKelas] = STATUS[p.status];
  const bar = (label, a, b) => `<tr><th scope="row">${label}</th>
    <td><span class="bar-w p"><i style="width:${a}%"></i></span>${fmt(a, 1)}%</td>
    <td><span class="bar-w n"><i style="width:${b}%"></i></span>${fmt(b, 1)}%</td></tr>`;
  return `<div class="periode" role="group" aria-label="Rentang periode">${["1", "5", "20", "60"]
    .map((k) => `<button type="button" data-periode="${k}" aria-pressed="${k === state.periode}">${k}H</button>`)
    .join("")}</div>
  <p class="statistik"><span>Status: <b class="${stKelas}">${stTeks}</b></span>
    <span>Delta HHI: <b>${fmt(p.delta_hhi, 0)}</b></span>
    <span>Net Buyer / Seller: <b>${p.n_net_buyer} / ${p.n_net_seller}</b></span>
    <span>VWAP: <b>${fmt(p.vwap)}</b></span></p>
  <div class="dua">${sisiBroker("Top Net Buyer", p.buyers, "p", maks)}${sisiBroker("Top Net Seller", p.sellers, "n", maks)}</div>
  <h3 class="sec">Konsentrasi Top-1 / 3 / 5</h3>
  <table class="mini"><thead><tr><th scope="col"></th><th scope="col">Sisi Net Buyer</th><th scope="col">Sisi Net Seller</th></tr></thead><tbody>
    ${bar("Top-1", p.top_beli[0], p.top_jual[0])}${bar("Top-3", p.top_beli[1], p.top_jual[1])}${bar("Top-5", p.top_beli[2], p.top_jual[2])}</tbody></table>`;
}

async function pilih(kode) {
  state.dipilih = kode;
  gambarBaris();
  const el = $("#detail");
  const e = state.semua.find((x) => x.kode === kode);
  el.innerHTML = `<h2 id="h-detail">Rincian ${esc(kode)}</h2><p class="muted">Memuat…</p>`;
  try {
    if (!cacheDetail.has(kode)) cacheDetail.set(kode, await sumber.ambilDetail(kode));
    if (state.dipilih !== kode) return; // pilihan sudah berganti selama memuat
    const d = cacheDetail.get(kode);
    const [ofiTeks, ofiKelas] = arahOfi(e.ofi);
    el.innerHTML = `<div class="judul"><h2 id="h-detail">Rincian <strong>${esc(kode)}</strong></h2>
      <span class="muted">${esc(e.nama)} · ${esc(PAPAN[e.papan_catat])}</span>${lencanaHtml(e.risiko)}</div>
      <dl class="ringkas">
        <div><dt>RVOL</dt><dd>${e.rvol == null ? "-" : fmt(e.rvol, 2) + "x"}</dd></div>
        <div><dt>Nilai berjalan</dt><dd>${rupiahPolos(e.nilai)}</dd></div>
        ${state.meta.punya_orderflow ? `<div><dt>CVD</dt><dd class="${e.cvd >= 0 ? "pos" : "neg"}">${rupiah(e.cvd)}</dd></div>
        <div><dt>OFI</dt><dd class="${ofiKelas}">${ofiTeks}</dd></div>` : ""}
        <div><dt>Baseline 20 Hari (trimmed)</dt><dd>${fmt(d.baseline_trimmed)} lbr</dd></div>
        <div><dt>Baseline 20 Hari (median)</dt><dd>${fmt(d.baseline_median)} lbr</dd></div>
      </dl>
      ${grafikRvol(d.seri)}
      <h3 class="sec">Broker Summary EOD</h3>
      ${d.broker ? matriksBroker(d) : '<p class="muted">Belum tersedia: butuh sumber data broker berlisensi.</p>'}`;
  } catch (err) {
    el.innerHTML = `<h2 id="h-detail">Rincian ${esc(kode)}</h2><p class="neg">Gagal memuat rincian: ${esc(err.message)}</p><button type="button" class="coba" data-ulang="${esc(kode)}">Coba lagi</button>`;
  }
}

/* ---------- Log alert ---------- */

function gambarAlert(daftar) {
  const ol = $("#alert");
  if (!daftar.length) {
    ol.innerHTML = '<li class="kosong">Belum ada alert pada sesi ini.</li>';
    return;
  }
  ol.innerHTML = [...daftar].reverse()
    .map((a) => `<li><time datetime="${esc(a.ts)}">${esc(a.ts.slice(11))}</time><span>${esc(a.pesan.split("\n")[0])}</span>
      <button type="button" data-kode="${esc(a.kode)}" aria-label="Lihat rincian ${esc(a.kode)}">Lihat</button></li>`)
    .join("");
}

/* ---------- Mulai ---------- */

/* Sumber data: berkas JSON lokal (pengembangan) atau Firestore (online, lihat sumber.js). */
const sumberLokal = {
  async ambilSemua() {
    const [screener, alerts] = await Promise.all([ambil("data/screener.json"), ambil("data/alerts.json")]);
    return { screener, alerts };
  },
  ambilDetail: (kode) => ambil(`data/emiten/${kode}.json`),
};
let sumber = sumberLokal;
let berlangganan = false;

function pasang({ screener: scr, alerts }) {
  cacheDetail.clear();
  state.semua = scr.emiten;
  state.meta = scr.meta;
  const m = scr.meta;
  const hariIni = new Date().toLocaleDateString("sv-SE");
  $("#sim").innerHTML = m.simulasi
    ? "<strong>DATA SIMULASI.</strong> Kode emiten dan semua angka sintetis, bukan data pasar."
    : `<strong>Data asli,</strong> ${esc(m.sumber)}. ${m.tanggal === hariIni ? "" : "Hari bursa terakhir, bukan hari ini."}`;
  $("#snapshot").textContent = `${m.simulasi ? "Cuplikan" : "Data"} ${m.snapshot.replace("T", " ")} WIB · ${fmt(m.jumlah_universe || state.semua.length)} emiten · ambang RVOL ${fmt(m.min_rvol, 1)}x dan nilai ${rupiahPolos(m.min_nilai_idr)}`;
  if (!m.simulasi) {
    $("#catatan").textContent = "RVOL = Volume Berjalan / (Baseline 20 Hari x Profil Volume). Nilai transaksi adalah perkiraan (volume x harga bar). Volume Yahoo tidak memisahkan Pasar Reguler dan Negosiasi. Profil Volume adalah profil pasar gabungan, bukan per emiten.";
  }
  $("table").classList.toggle("tanpa-orderflow", m.punya_orderflow === false);
  $("table").classList.toggle("tanpa-broker", m.punya_broker === false);
  if (m.risiko_tersedia) {
    for (const o of document.querySelectorAll("#risiko option")) {
      if (o.value && o.value !== "TANPA" && !m.risiko_tersedia.includes(o.value)) o.remove();
    }
  }
  $("#disclaimer").textContent = m.disclaimer;
  gambarAlert(alerts);
  terapkanFilter();
  const masihAda = state.dipilih && state.semua.some((e) => e.kode === state.dipilih);
  if (masihAda) pilih(state.dipilih);
  else if (state.rows[0]) pilih(state.rows[0].kode);
}

function tampilkanLogin(pesan = "") {
  tampilkanStatus(`Halaman ini pribadi.${pesan ? `<br><span class="neg">${esc(pesan)}</span>` : ""}<br><button type="button" id="masuk">Masuk dengan Google</button>`);
}

function tampilkanAkun(pengguna) {
  const el = $("#akun");
  el.hidden = !pengguna;
  el.innerHTML = pengguna ? `${esc(pengguna.email)} <button type="button" id="keluar">Keluar</button>` : "";
}

async function muat() {
  tampilkanStatus("Memuat data…");
  try {
    if (sumber === sumberLokal && window.FIREBASE_CONFIG) {
      sumber = (await import("./sumber.js")).buatSumber(window.FIREBASE_CONFIG);
    }
    if (sumber.sesi) {
      const pengguna = await sumber.sesi();
      tampilkanAkun(pengguna);
      if (!pengguna) return tampilkanLogin();
    }
    pasang(await sumber.ambilSemua());
    if (sumber.langganan && !berlangganan) {
      berlangganan = true;
      sumber.langganan(pasang, (err) => tampilkanStatus(`Koneksi data terputus (${esc(err.message)}).<br><button type="button" id="ulang">Coba lagi</button>`));
    }
  } catch (err) {
    tampilkanStatus(`Gagal memuat data (${esc(err.message)}).<br><button type="button" id="ulang">Coba lagi</button>`);
  }
}

let menunggu = false;
$("#scroll").addEventListener("scroll", () => {
  if (menunggu) return;
  menunggu = true;
  requestAnimationFrame(() => { menunggu = false; gambarBaris(); });
});
for (const id of ["#q", "#papan", "#risiko", "#lonjakan"]) $(id).addEventListener("input", terapkanFilter);
document.addEventListener("click", (ev) => {
  const t = ev.target;
  const th = t.closest("thead th[data-key]");
  if (th) {
    const key = th.dataset.key;
    state.sort = { key, dir: state.sort.key === key ? -state.sort.dir : key === "kode" || key === "papan_catat" || key === "status_5h" ? 1 : -1 };
    return terapkanFilter();
  }
  const kode = t.closest("button[data-kode]");
  if (kode) return pilih(kode.dataset.kode);
  const periode = t.closest("button[data-periode]");
  if (periode) { state.periode = periode.dataset.periode; return pilih(state.dipilih); }
  const ulang = t.closest("button[data-ulang]");
  if (ulang) { cacheDetail.delete(ulang.dataset.ulang); return pilih(ulang.dataset.ulang); }
  if (t.closest("#reset")) {
    $("#q").value = ""; $("#papan").value = ""; $("#risiko").value = ""; $("#lonjakan").checked = false;
    return terapkanFilter();
  }
  if (t.closest("#ulang")) muat();
  if (t.closest("#masuk")) sumber.masuk().then(muat).catch((err) => tampilkanLogin(err.message));
  if (t.closest("#keluar")) sumber.keluar().then(() => { state.semua = []; state.rows = []; muat(); });
});

muat();
