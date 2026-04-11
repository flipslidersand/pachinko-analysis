-- パチスロ分析プロジェクト 初期スキーマ

-- 店舗テーブル
CREATE TABLE IF NOT EXISTS stores (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    url VARCHAR(255),
    region VARCHAR(100),
    hall_id VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 機種テーブル
CREATE TABLE IF NOT EXISTS machines (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50),   -- 'pachislot' or 'pachinko'
    maker VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 日次営業データ（メインテーブル）
CREATE TABLE IF NOT EXISTS daily_results (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    machine_id INTEGER REFERENCES machines(id) ON DELETE SET NULL,
    date DATE NOT NULL,
    games_count INTEGER,
    medals_in INTEGER,
    medals_out INTEGER,
    diff INTEGER,           -- 差枚数 (out - in)
    collected_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(store_id, machine_id, date)
);

-- 予測結果（キャッシュ用）
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    predicted_diff DECIMAL(10, 2),
    confidence DECIMAL(5, 2),
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(store_id, date)
);

-- スクレイピングログ
CREATE TABLE IF NOT EXISTS scrape_logs (
    id SERIAL PRIMARY KEY,
    store_id INTEGER REFERENCES stores(id) ON DELETE SET NULL,
    status VARCHAR(50),  -- 'success', 'error', 'timeout'
    scraped_at TIMESTAMP DEFAULT NOW(),
    error_message TEXT
);

-- スクレイピング生データテーブル（Phase 1）
CREATE TABLE IF NOT EXISTS raw_machine_data (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    machine_type VARCHAR(20) NOT NULL,  -- 'S' or 'P'
    unit_number VARCHAR(20),             -- 台番号
    machine_name VARCHAR(100),
    target_date DATE NOT NULL,
    total_games INTEGER,                 -- 総ゲーム数
    bonus_count INTEGER,                 -- ボーナス/初当り回数
    payout INTEGER,                      -- 払出し数（パチンコ）
    diff INTEGER,                        -- 差枚数
    source_url VARCHAR(255),
    source_hash VARCHAR(64),             -- 重複防止用ハッシュ
    scraped_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(store_id, machine_type, unit_number, target_date, source_hash)
);

-- 日次集計済みデータテーブル
CREATE TABLE IF NOT EXISTS daily_machine_stats (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    machine_id INTEGER NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    machine_type VARCHAR(20) NOT NULL,  -- 'S' or 'P'
    target_date DATE NOT NULL,
    games_count INTEGER,
    diff INTEGER,
    stddev DECIMAL(10, 2),
    min_diff INTEGER,
    max_diff INTEGER,
    sample_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(store_id, machine_id, target_date)
);

-- 学習用特徴量テーブル（Phase 1 後半）
CREATE TABLE IF NOT EXISTS ml_features (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    machine_id INTEGER NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    machine_type VARCHAR(20) NOT NULL,  -- 'S' or 'P'
    feature_date DATE NOT NULL,

    -- 直近差枚
    prev_1d_diff INTEGER,
    prev_2d_diff INTEGER,
    prev_3d_diff INTEGER,

    -- 移動平均
    avg_3d_diff DECIMAL(10, 2),
    avg_7d_diff DECIMAL(10, 2),
    avg_30d_diff DECIMAL(10, 2),

    -- 標準偏差
    stddev_3d DECIMAL(10, 2),
    stddev_7d DECIMAL(10, 2),
    stddev_30d DECIMAL(10, 2),

    -- トレンド
    trend_up_days_7d INTEGER,
    trend_down_days_7d INTEGER,
    positive_ratio_7d DECIMAL(5, 2),

    -- ボラティリティ
    max_diff_30d INTEGER,
    min_diff_30d INTEGER,
    volatility_30d DECIMAL(10, 2),

    -- ゲーム数
    total_games_1d INTEGER,

    -- 曜日
    day_of_week INTEGER,

    -- ラベル（スロット用）
    hit_label INTEGER,  -- 1: diff > THRESHOLD, 0: else

    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(store_id, machine_id, feature_date)
);

-- 予測結果テーブル（修正版：スロット専用）
CREATE TABLE IF NOT EXISTS slot_predictions (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    machine_id INTEGER NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    prediction_date DATE NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    hit_probability DECIMAL(5, 4),       -- 0.0 - 1.0
    expected_value DECIMAL(10, 2),
    confidence_score DECIMAL(5, 4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(store_id, machine_id, prediction_date, model_version)
);

-- 予測検証テーブル
CREATE TABLE IF NOT EXISTS prediction_results (
    id SERIAL PRIMARY KEY,
    prediction_id INTEGER REFERENCES slot_predictions(id) ON DELETE CASCADE,
    actual_diff INTEGER,
    actual_label INTEGER,  -- 実績ラベル
    was_correct BOOLEAN,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_daily_results_store_id ON daily_results(store_id);
CREATE INDEX IF NOT EXISTS idx_daily_results_date ON daily_results(date);
CREATE INDEX IF NOT EXISTS idx_predictions_store_id ON predictions(store_id);
CREATE INDEX IF NOT EXISTS idx_scrape_logs_store_id ON scrape_logs(store_id);

CREATE INDEX IF NOT EXISTS idx_raw_machine_data_store_id ON raw_machine_data(store_id);
CREATE INDEX IF NOT EXISTS idx_raw_machine_data_date ON raw_machine_data(target_date);
CREATE INDEX IF NOT EXISTS idx_daily_machine_stats_store_id ON daily_machine_stats(store_id);
CREATE INDEX IF NOT EXISTS idx_daily_machine_stats_date ON daily_machine_stats(target_date);
CREATE INDEX IF NOT EXISTS idx_ml_features_store_id ON ml_features(store_id);
CREATE INDEX IF NOT EXISTS idx_ml_features_date ON ml_features(feature_date);
CREATE INDEX IF NOT EXISTS idx_slot_predictions_store_id ON slot_predictions(store_id);
CREATE INDEX IF NOT EXISTS idx_slot_predictions_date ON slot_predictions(prediction_date);
