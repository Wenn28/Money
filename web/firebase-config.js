// Isi dengan config web app dari Firebase Console (Project settings > Your apps > Web app).
// Config ini memang publik; yang melindungi data adalah firestore.rules.
// Biarkan null untuk memakai berkas JSON lokal (pengembangan).
window.FIREBASE_CONFIG = null;
/* Contoh:
window.FIREBASE_CONFIG = {
  apiKey: "...",
  authDomain: "PROJECT_ID.firebaseapp.com",
  projectId: "PROJECT_ID",
  appId: "...",
};
*/
