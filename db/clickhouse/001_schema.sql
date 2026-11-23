-- ClickHouse: tick, order book, bar, profil volume, baseline, matriks broker.
-- Volume dalam lembar. Waktu dalam Asia/Jakarta.
CREATE DATABASE IF NOT EXISTS saham;

-- Tick trade. aggressor diisi engine (Lee-Ready) sebelum insert; U = belum terklasifikasi.
CREATE TABLE IF NOT EXISTS saham.ticks
(
    ts        DateTime64(3, 'Asia/Jakarta') CODEC(Delta, ZSTD),
    kode      LowCardinality(String),
    papan     Enum8('REGULER' = 1, 'NEGOSIASI' = 2, 'TUNAI' = 3),
    trade_id  UInt64,
    price     Decimal(12, 2),
    volume    UInt64,
    nilai     Decimal(24, 2),
    aggressor Enum8('U' = 0, 'B' = 1, 'S' = 2) DEFAULT 'U'
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (kode, papan, ts, trade_id)
TTL toDateTime(ts) + INTERVAL 90 DAY DELETE;

CREATE TABLE IF NOT EXISTS saham.orderbook_l5
(
    ts      DateTime64(3, 'Asia/Jakarta') CODEC(Delta, ZSTD),
    kode    LowCardinality(String),
    bid_px  Array(Decimal(12, 2)),
    bid_vol Array(UInt64),
    ask_px  Array(Decimal(12, 2)),
    ask_vol Array(UInt64),
    CONSTRAINT lima_level CHECK length(bid_px) = 5 AND length(bid_vol) = 5
                              AND length(ask_px) = 5 AND length(ask_vol) = 5
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (kode, ts)
TTL toDateTime(ts) + INTERVAL 30 DAY DELETE;

-- Bar 1 menit, per papan (bar Pasar Reguler tidak tercampur crossing Negosiasi).
CREATE TABLE IF NOT EXISTS saham.bars_1m
(
    menit    DateTime('Asia/Jakarta'),
    kode     LowCardinality(String),
    papan    Enum8('REGULER' = 1, 'NEGOSIASI' = 2, 'TUNAI' = 3),
    open_s   AggregateFunction(argMin, Decimal(12, 2), DateTime64(3, 'Asia/Jakarta')),
    high     SimpleAggregateFunction(max, Decimal(12, 2)),
    low      SimpleAggregateFunction(min, Decimal(12, 2)),
    close_s  AggregateFunction(argMax, Decimal(12, 2), DateTime64(3, 'Asia/Jakarta')),
    volume   SimpleAggregateFunction(sum, UInt64),
    nilai    SimpleAggregateFunction(sum, Decimal(24, 2)),
    buy_vol  SimpleAggregateFunction(sum, UInt64),
    sell_vol SimpleAggregateFunction(sum, UInt64),
    n_trades SimpleAggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(menit)
ORDER BY (kode, papan, menit);

CREATE MATERIALIZED VIEW IF NOT EXISTS saham.bars_1m_mv TO saham.bars_1m AS
SELECT
    toStartOfMinute(ts)       AS menit,
    kode,
    papan,
    argMinState(price, ts)    AS open_s,
    max(price)                AS high,
    min(price)                AS low,
    argMaxState(price, ts)    AS close_s,
    sum(volume)               AS volume,
    sum(nilai)                AS nilai,
    sumIf(volume, aggressor = 'B') AS buy_vol,
    sumIf(volume, aggressor = 'S') AS sell_vol,
    count()                   AS n_trades
FROM saham.ticks
GROUP BY menit, kode, papan;

CREATE VIEW IF NOT EXISTS saham.bars_1m_v AS
SELECT
    menit, kode, papan,
    argMinMerge(open_s)  AS open,
    max(high)            AS high,
    min(low)             AS low,
    argMaxMerge(close_s) AS close,
    sum(volume)          AS volume,
    sum(nilai)           AS nilai,
    sum(buy_vol)         AS buy_vol,
    sum(sell_vol)        AS sell_vol,
    sum(n_trades)        AS n_trades
FROM saham.bars_1m
GROUP BY menit, kode, papan;

-- Volume Harian per papan; sumber baseline (hanya REGULER dipakai).
CREATE TABLE IF NOT EXISTS saham.volume_harian
(
    tanggal Date,
    kode    LowCardinality(String),
    papan   Enum8('REGULER' = 1, 'NEGOSIASI' = 2, 'TUNAI' = 3),
    volume  UInt64,
    nilai   Decimal(24, 2)
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(tanggal)
ORDER BY (kode, papan, tanggal);

CREATE MATERIALIZED VIEW IF NOT EXISTS saham.volume_harian_mv TO saham.volume_harian AS
SELECT toDate(ts) AS tanggal, kode, papan, sum(volume) AS volume, sum(nilai) AS nilai
FROM saham.ticks
GROUP BY tanggal, kode, papan;

-- Fraksi kumulatif volume F(t) per emiten per menit sesi.
-- menit_sesi = menit perdagangan sejak buka, tanpa jeda istirahat.
-- SEN_KAM: 09:00-12:00 dan 13:30-15:50 (320 menit). JUM: 09:00-11:30 dan 14:00-15:50 (260 menit).
CREATE TABLE IF NOT EXISTS saham.profil_volume
(
    jenis_hari  Enum8('SEN_KAM' = 1, 'JUM' = 2),
    kode        LowCardinality(String),
    menit_sesi  UInt16,
    fraksi      Float64,
    dihitung_pada Date,
    CONSTRAINT fraksi_valid CHECK fraksi >= 0 AND fraksi <= 1
)
ENGINE = ReplacingMergeTree(dihitung_pada)
ORDER BY (jenis_hari, kode, menit_sesi);

-- Baseline 20 hari (trimmed mean 10%/10% dan median) per emiten per tanggal acuan.
CREATE TABLE IF NOT EXISTS saham.baseline_rvol
(
    kode          LowCardinality(String),
    per_tanggal   Date,
    trimmed_mean  Float64,
    median        Float64,
    n_hari        UInt8,
    dihitung_pada DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(dihitung_pada)
ORDER BY (kode, per_tanggal);

-- Checkpoint domisili investor saat jeda Sesi I.
CREATE TABLE IF NOT EXISTS saham.domisili_sesi1
(
    tanggal         Date,
    kode            LowCardinality(String),
    papan           Enum8('REGULER' = 1, 'NEGOSIASI' = 2, 'TUNAI' = 3),
    asing_beli_nilai  Decimal(24, 2),
    asing_jual_nilai  Decimal(24, 2),
    lokal_beli_nilai  Decimal(24, 2),
    lokal_jual_nilai  Decimal(24, 2),
    diambil_pada    DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(diambil_pada)
PARTITION BY toYYYYMM(tanggal)
ORDER BY (tanggal, kode, papan);

-- Ringkasan harga EOD per papan, pembanding harga rata-rata broker.
CREATE TABLE IF NOT EXISTS saham.harian_eod
(
    tanggal Date,
    kode    LowCardinality(String),
    papan   Enum8('REGULER' = 1, 'NEGOSIASI' = 2, 'TUNAI' = 3),
    open    Decimal(12, 2),
    high    Decimal(12, 2),
    low     Decimal(12, 2),
    close   Decimal(12, 2),
    volume  UInt64,
    vwap    Decimal(12, 2),
    diambil_pada DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(diambil_pada)
PARTITION BY toYYYYMM(tanggal)
ORDER BY (papan, kode, tanggal);

-- Matriks Broker Summary EOD: tanggal x emiten x broker x papan.
-- ~970 x 88 x 4 papan per hari; kunci urut melayani query per emiten rentang tanggal,
-- indeks set melayani query per broker. Harga rata-rata = nilai / volume.
CREATE TABLE IF NOT EXISTS saham.broker_summary_eod
(
    tanggal      Date,
    kode         LowCardinality(String),
    broker_kode  FixedString(2),
    papan        Enum8('REGULER' = 1, 'NEGOSIASI' = 2, 'TUNAI' = 3),
    beli_vol     UInt64,
    beli_nilai   Decimal(24, 2),
    jual_vol     UInt64,
    jual_nilai   Decimal(24, 2),
    diambil_pada DateTime DEFAULT now(),
    INDEX idx_broker broker_kode TYPE set(100) GRANULARITY 4
)
ENGINE = ReplacingMergeTree(diambil_pada)
PARTITION BY toYYYYMM(tanggal)
ORDER BY (papan, kode, tanggal, broker_kode);

-- Skor akumulasi/distribusi lintas broker (Pasar Reguler), per periode 1/5/20/60 hari.
CREATE TABLE IF NOT EXISTS saham.skor_akumulasi
(
    tanggal         Date,
    periode_hari    UInt8,
    kode            LowCardinality(String),
    papan           Enum8('REGULER' = 1, 'NEGOSIASI' = 2, 'TUNAI' = 3),
    hhi_beli        Float64,
    hhi_jual        Float64,
    delta_hhi       Float64,
    n_net_buyer     UInt16,
    n_net_seller    UInt16,
    rasio_buyer_seller Float64,
    top1_beli_pct   Float64,
    top3_beli_pct   Float64,
    top5_beli_pct   Float64,
    top1_jual_pct   Float64,
    top3_jual_pct   Float64,
    top5_jual_pct   Float64,
    status          Enum8('BIG_ACCUMULATION' = 1, 'MODERATE_ACCUMULATION' = 2, 'NEUTRAL' = 3,
                          'DISTRIBUTION' = 4, 'BIG_DISTRIBUTION' = 5),
    dihitung_pada   DateTime DEFAULT now(),
    CONSTRAINT periode_valid CHECK periode_hari IN (1, 5, 20, 60)
)
ENGINE = ReplacingMergeTree(dihitung_pada)
PARTITION BY toYYYYMM(tanggal)
ORDER BY (periode_hari, tanggal, kode, papan);
