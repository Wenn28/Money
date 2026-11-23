// Sumber data Firestore + login Google. Dimuat hanya bila window.FIREBASE_CONFIG diisi.
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import { getAuth, onAuthStateChanged, GoogleAuthProvider, signInWithPopup, signOut } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js";
import { getFirestore, doc, getDoc, onSnapshot } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js";

const angka = (s) => (s ? s.split(",").map((x) => (x === "" ? null : Number(x))) : []);

function ramah(err) {
  return err.code === "permission-denied" ? new Error("Akun ini belum diizinkan membaca data.") : err;
}

export function buatSumber(config) {
  const auth = getAuth(initializeApp(config));
  const ref = doc(getFirestore(), "snapshot", "latest");
  let terakhir = null;

  const olah = (d) => {
    terakhir = d;
    return { screener: d.screener, alerts: d.alerts || [] };
  };

  return {
    sesi: () => new Promise((selesai) => { const lepas = onAuthStateChanged(auth, (u) => { lepas(); selesai(u); }); }),
    masuk: () => signInWithPopup(auth, new GoogleAuthProvider()),
    keluar: () => signOut(auth),
    async ambilSemua() {
      try {
        const s = await getDoc(ref);
        if (!s.exists()) throw new Error("Belum ada snapshot. Job data belum pernah berjalan.");
        return olah(s.data());
      } catch (err) {
        throw ramah(err);
      }
    },
    async ambilDetail(kode) {
      const d = terakhir?.detail?.[kode];
      if (!d) throw new Error(`Rincian ${kode} tidak ada di snapshot.`);
      return { baseline_trimmed: d.baseline_trimmed, baseline_median: d.baseline_median, seri: { menit: angka(d.menit), rvol: angka(d.rvol) }, broker: null };
    },
    langganan(pasang, galat) {
      onSnapshot(ref, (s) => s.exists() && pasang(olah(s.data())), (err) => galat(ramah(err)));
    },
  };
}
