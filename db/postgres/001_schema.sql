-- PostgreSQL 16: master data, overlay risiko, aturan alert, RBAC, audit.
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE papan_pencatatan AS ENUM ('UTAMA', 'PENGEMBANGAN', 'AKSELERASI', 'PEMANTAUAN_KHUSUS');
CREATE TYPE papan_perdagangan AS ENUM ('REGULER', 'NEGOSIASI', 'TUNAI');
CREATE TYPE jenis_risiko AS ENUM ('FCA_X', 'UMA', 'SUSPENSI', 'HSC');
CREATE TYPE domisili_broker AS ENUM ('LOKAL', 'ASING');
CREATE TYPE status_broker AS ENUM ('AKTIF', 'NONAKTIF');
CREATE TYPE peran_user AS ENUM ('ADMIN', 'ANALIS', 'PENGAMAT');
CREATE TYPE metode_baseline AS ENUM ('TRIMMED_MEAN', 'MEDIAN');
CREATE TYPE kanal_notifikasi AS ENUM ('DASHBOARD', 'TELEGRAM');

-- Emiten ---------------------------------------------------------------
CREATE TABLE emiten (
    kode             varchar(4) PRIMARY KEY CHECK (kode ~ '^[A-Z0-9]{4}$'),
    nama             text NOT NULL,
    sektor           text,
    papan_pencatatan papan_pencatatan NOT NULL,
    tanggal_listing  date,
    tanggal_delisting date,
    CHECK (tanggal_delisting IS NULL OR tanggal_listing IS NULL OR tanggal_delisting >= tanggal_listing)
);

-- Overlay risiko dengan riwayat. HSC wajib membawa persentase kepemilikan.
CREATE TABLE emiten_risiko (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kode       varchar(4) NOT NULL REFERENCES emiten(kode),
    jenis      jenis_risiko NOT NULL,
    berlaku    daterange NOT NULL,
    nilai_pct  numeric(5,2) CHECK (nilai_pct BETWEEN 0 AND 100),
    sumber     text,
    CHECK (jenis <> 'HSC' OR nilai_pct IS NOT NULL),
    EXCLUDE USING gist (kode WITH =, jenis WITH =, berlaku WITH &&)
);
CREATE INDEX emiten_risiko_kode_idx ON emiten_risiko USING gist (kode, berlaku);

-- Broker: Slowly Changing Dimension tipe 2. Kode broker stabil; status berubah
-- lewat baris baru, jadi data historis broker yang dicabut tetap utuh.
CREATE TABLE broker (
    broker_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kode       char(2) NOT NULL CHECK (kode ~ '^[A-Z]{2}$'),
    nama       text NOT NULL,
    domisili   domisili_broker NOT NULL,
    status     status_broker NOT NULL,
    berlaku    daterange NOT NULL,
    EXCLUDE USING gist (kode WITH =, berlaku WITH &&)
);
CREATE INDEX broker_kode_idx ON broker (kode);

-- Kalender Hari Bursa. Jenis sesi (Sen-Kam vs Jumat) diturunkan dari hari dalam pekan.
CREATE TABLE hari_bursa (
    tanggal    date PRIMARY KEY,
    buka       boolean NOT NULL,
    keterangan text
);

-- Pengguna, RBAC, kanal --------------------------------------------------
CREATE TABLE app_user (
    user_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username      text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    peran         peran_user NOT NULL DEFAULT 'PENGAMAT',
    aktif         boolean NOT NULL DEFAULT true,
    dibuat_pada   timestamptz NOT NULL DEFAULT now()
);

-- config_enc = pgp_sym_encrypt(token/chat_id, APP_SECRET_KEY) dari sisi aplikasi.
CREATE TABLE kanal_user (
    kanal_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    jenis      kanal_notifikasi NOT NULL,
    config_enc bytea,
    aktif      boolean NOT NULL DEFAULT true,
    UNIQUE (user_id, jenis)
);

-- user_id NULL = aturan global bawaan; kode NULL = semua emiten.
CREATE TABLE alert_rule (
    rule_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         uuid REFERENCES app_user(user_id) ON DELETE CASCADE,
    kode            varchar(4) REFERENCES emiten(kode),
    min_rvol        numeric(5,2) NOT NULL DEFAULT 3.50 CHECK (min_rvol >= 1),
    min_nilai_idr   numeric(20,0) NOT NULL DEFAULT 5000000000 CHECK (min_nilai_idr >= 0),
    metode_baseline metode_baseline NOT NULL DEFAULT 'TRIMMED_MEAN',
    cooldown_menit  integer NOT NULL DEFAULT 15 CHECK (cooldown_menit >= 0),
    naik_rvol_lagi  numeric(4,2) NOT NULL DEFAULT 1.00 CHECK (naik_rvol_lagi >= 0),
    aktif           boolean NOT NULL DEFAULT true
);
CREATE INDEX alert_rule_user_idx ON alert_rule (user_id) WHERE aktif;

INSERT INTO alert_rule (user_id, kode) VALUES (NULL, NULL);

-- Alert dan audit: partisi bulanan -----------------------------------------
CREATE TABLE alert_log (
    alert_id        bigint GENERATED ALWAYS AS IDENTITY,
    ts              timestamptz NOT NULL,
    kode            varchar(4) NOT NULL,
    papan           papan_perdagangan NOT NULL,
    rvol            numeric(8,2) NOT NULL,
    nilai_kumulatif numeric(24,2) NOT NULL,
    cvd             numeric(24,2),
    ofi             numeric(24,2),
    metode_baseline metode_baseline NOT NULL,
    lencana_risiko  text[] NOT NULL DEFAULT '{}',
    pesan           text NOT NULL,
    status_kirim    jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (alert_id, ts)
) PARTITION BY RANGE (ts);
CREATE INDEX alert_log_kode_ts_idx ON alert_log (kode, ts DESC);
CREATE INDEX alert_log_ts_idx ON alert_log (ts DESC);

CREATE TABLE audit_log (
    audit_id bigint GENERATED ALWAYS AS IDENTITY,
    ts       timestamptz NOT NULL DEFAULT now(),
    user_id  uuid,
    aksi     text NOT NULL,
    objek    text,
    detail   jsonb NOT NULL DEFAULT '{}',
    ip       inet,
    PRIMARY KEY (audit_id, ts)
) PARTITION BY RANGE (ts);
CREATE INDEX audit_log_user_ts_idx ON audit_log (user_id, ts DESC);

-- shortcut: partisi dibuat 24 bulan ke depan saat init, buat ulang dengan fungsi ini sebelum habis (jadwalkan di Tahap 4).
CREATE FUNCTION buat_partisi_bulanan(tabel regclass, mulai date, jumlah int) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    awal date;
BEGIN
    FOR i IN 0..jumlah - 1 LOOP
        awal := date_trunc('month', mulai)::date + make_interval(months => i);
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF %s FOR VALUES FROM (%L) TO (%L)',
            tabel::text || '_' || to_char(awal, 'YYYY_MM'), tabel, awal, (awal + interval '1 month')::date);
    END LOOP;
END $$;

SELECT buat_partisi_bulanan('alert_log', (now() - interval '1 month')::date, 24);
SELECT buat_partisi_bulanan('audit_log', (now() - interval '1 month')::date, 24);

-- Audit log hanya boleh ditambah.
CREATE FUNCTION tolak_ubah_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log dan alert_log bersifat append-only';
END $$;

CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION tolak_ubah_audit();
CREATE TRIGGER alert_log_append_only BEFORE UPDATE OR DELETE ON alert_log
    FOR EACH ROW EXECUTE FUNCTION tolak_ubah_audit();
