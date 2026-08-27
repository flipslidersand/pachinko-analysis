# pachinko-analysis

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.3-F7931E?logo=scikitlearn)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![License](https://img.shields.io/badge/License-MIT-green)

---

## English

A production-grade pachinko/slot machine analysis system that scrapes parlor operational data, stores it in PostgreSQL, applies machine-learning models, and exposes results via a FastAPI dashboard.

### Features

| Feature | Description |
|---------|-------------|
| **Hit-probability prediction** | RandomForestClassifier trained on 17 time-series features; outputs per-machine win probability (0.0–1.0) |
| **Conditional expected value** | 4-tier fallback (weekday×model → weekday → model → global) with confidence scoring |
| **Pattern analysis** | K-means clustering (k=3) labelled as `high_variance_positive`, `stable_mid`, `low_performance` |
| **Prediction verification** | Auto-reconciliation of past predictions vs. actuals; computes accuracy / precision / recall / F1 |
| **Automated pipeline** | APScheduler jobs at 01:00 scrape → 02:00 aggregate → 02:30 features → 03:00 predict |

### Architecture

```
Scraper (Selenium + BS4)
    ↓
PostgreSQL
  ├─ raw_machine_data
  ├─ daily_machine_stats
  ├─ ml_features
  ├─ slot_predictions
  └─ prediction_results
    ↓
FastAPI (analysis.py routers)
    ↓
HTML Dashboard (dashboard.html)
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLAlchemy, Pydantic |
| ML / Analysis | scikit-learn (RandomForest), LightGBM, SHAP, pandas, numpy |
| Database | PostgreSQL |
| Scraping | Selenium, BeautifulSoup4 |
| Scheduler | APScheduler |
| Frontend | HTML / CSS / JavaScript (Vanilla) |
| Container | Docker, Docker Compose |

### Quick Start

```bash
# 1. Start all services
docker-compose up -d

# 2. Check slot hit-probability predictions
curl http://localhost:8000/api/analysis/slots/predictions?store_id=1 | jq .

# 3. Open integrated dashboard
open http://localhost:8000/dashboard
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/analysis/slots/predictions` | Top-10 hit probability ranking |
| GET | `/api/analysis/slots/dashboard` | Integrated dashboard data |
| GET | `/api/analysis/pachinko/expected-value` | Pachinko expected-value ranking |
| GET | `/api/evaluation/verify` | Verify past predictions |
| GET | `/api/evaluation/stats` | Evaluation statistics (past N days) |

### Dataset

- Slot machines: 846 units (SUPER CONCORDE Ichino store)
- Pachinko machines: 664 units
- Training window: 60 days prior to prediction date
- Minimum training samples: 30
- Feature dimensions: 17
- Label: `diff > 1000 coins → hit (1)`, otherwise miss (0)

---

## 日本語

パチンコ・スロット営業データのスクレイピング → DB蓄積 → ML分析 → ダッシュボード表示を行う、実運用対応の予測・分析システムです。

### 主要機能

| 機能 | 概要 |
|------|------|
| **当たり確率予測** | RandomForestClassifier + 17個の時系列特徴量。各台の当たり確率を 0.0～1.0 で出力 |
| **条件付き期待値** | 曜日×機種 → 曜日 → 機種 → 全体 の4段階fallback。信頼度スコア付き |
| **パターン分析** | K-means クラスタリング（k=3）: `high_variance_positive` / `stable_mid` / `low_performance` |
| **予測検証** | 過去予測と実績を自動突合。accuracy / precision / recall / F1 を自動計算 |
| **自動パイプライン** | APScheduler: 01:00 スクレイプ → 02:00 集計 → 02:30 特徴量生成 → 03:00 予測 |

### システム構成

```
スクレイパー (Selenium + BS4)
    ↓
PostgreSQL
  ├─ raw_machine_data       (生データ蓄積)
  ├─ daily_machine_stats    (日次集計層)
  ├─ ml_features            (特徴量層)
  ├─ slot_predictions       (予測結果)
  └─ prediction_results     (検証データ)
    ↓
FastAPI (analysis.py ルーター)
    ↓
HTML ダッシュボード (dashboard.html)
```

### 技術スタック

| レイヤー | 技術 |
|---------|------|
| バックエンド | FastAPI, SQLAlchemy, Pydantic |
| ML・分析 | scikit-learn (RF), LightGBM, SHAP, pandas, numpy |
| DB | PostgreSQL |
| スクレイピング | Selenium, BeautifulSoup4 |
| スケジューラ | APScheduler |
| フロントエンド | HTML/CSS/JavaScript (Vanilla) |
| コンテナ | Docker, Docker Compose |

### クイックスタート

```bash
# 1. 全サービス起動
docker-compose up -d

# 2. スロット当たり確率予測を確認
curl http://localhost:8000/api/analysis/slots/predictions?store_id=1 | jq .

# 3. 統合ダッシュボードを開く
open http://localhost:8000/dashboard
```

### API エンドポイント

| メソッド | パス | 説明 |
|--------|------|------|
| GET | `/api/analysis/slots/predictions` | 当たり確率 Top 10 |
| GET | `/api/analysis/slots/dashboard` | 統合ダッシュボードデータ |
| GET | `/api/analysis/pachinko/expected-value` | パチンコ期待値ランキング |
| GET | `/api/evaluation/verify` | 予測検証 |
| GET | `/api/evaluation/stats` | 評価統計（過去N日） |

### データ特性

| 項目 | 値 |
|------|-----|
| スロット機種数 | 846台（SUPER CONCORDE 市野） |
| パチンコ機種数 | 664台 |
| 学習対象期間 | prediction_date より前 60日 |
| 最小学習サンプル | 30 |
| 特徴量次元 | 17 |
| ラベル定義 | 差枚 > 1000 → 当たり (1), else → ハズレ (0) |

### よくある質問

**Q: 当たり確率とは何か？**  
A: 「差枚 > 1000 の成績となる確率」。各台について 0.0～1.0 で表示します。

**Q: 期待値の「条件付き」とは？**  
A: 曜日や機種ごとの条件下での期待値。データが少ない時は自動的に広い条件にfallbackします。

**Q: 当日データを学習に使わないのはなぜか？**  
A: 朝に予測するので、その日のデータはまだ不完全。前日までのデータだけで学習（データリーク防止）。

**Q: モデルはどの期間で自動更新されるか？**  
A: 毎日深夜 03:00 に APScheduler が自動実行。新しいデータが増えるたびにモデルが改善されます。
