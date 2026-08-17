# パチスロ分析プロジェクト - 実装状況レポート

**更新日**: 2026-08-17（残タスクの実装状況をコード検証で反映）  
**プロジェクト**: pachinko-analysis  
**目的**: スロット営業データのスクレイピング・ML分析・予測システム

---

## 🎯 プロジェクト目標

- 1～5店舗（パイロット）からスロット営業データをスクレイピング
- 複数の機械学習モデルで「当たり確率」「期待値」「パターン」を予測
- DB蓄積 → 特徴量生成 → 学習 → 予測 → 検証 の完全パイプライン構築
- Web ダッシュボードで実運用に耐える分析結果を表示

---

## ✅ 実装完了（Phase 1～4）

### Phase 1: 基盤整備

#### DB設計（新規テーブル5個）
```sql
✅ raw_machine_data
   - スクレイピング生データの蓄積
   - (store_id, machine_type, unit_number, target_date, source_hash)

✅ daily_machine_stats
   - 日次集計済みデータ
   - games_count, diff, stddev, min_diff, max_diff を保有

✅ ml_features
   - 学習用特徴量（自動生成）
   - 17個の時系列・統計・トレンド特徴量

✅ slot_predictions
   - スロット予測結果
   - hit_probability, expected_value, confidence_score

✅ prediction_results
   - 予測検証用テーブル
   - actual_diff, actual_label, was_correct
```

**ファイル**: `src/database/migrations/001_init.sql`

#### 共通特徴量モジュール
```python
✅ src/analysis/features.py
   - 生成特徴量（17個）
     * prev_1d_diff, prev_2d_diff, prev_3d_diff
     * avg_3d_diff, avg_7d_diff, avg_30d_diff
     * stddev_3d, stddev_7d, stddev_30d
     * trend_up_days_7d, trend_down_days_7d, positive_ratio_7d
     * max_diff_30d, min_diff_30d, volatility_30d
     * total_games_1d, day_of_week
   - 機能：prediction_date より前のデータのみ使用（当日データ除外）
```

**ファイル**: `src/analysis/features.py`  
**責務**: 時系列特徴量の共通化・統一管理

---

### Phase 2: スロット分析

#### 当たり確率予測モデル
```python
✅ src/analysis/slots.py
   - アルゴリズム: RandomForestClassifier
   - 特徴量: 17個（全て）
   - 学習期間: prediction_date より前の 60 日
   - テスト期間: 過去 7 日
   - ラベル: diff > 1000 → 1, else → 0
   - 出力: hit_probability (0.0～1.0)
   - 評価指標: Accuracy, Precision, Recall, F1, ROC-AUC
```

**ファイル**: `src/analysis/slots.py`  
**関数**:
- `train_hit_probability_model()` - モデル学習＆評価
- `predict_hit_probability()` - 本日予測＆DB保存
- `get_prediction_metadata()` - モデルメタ情報

#### 期待値計算（改善版）
```python
✅ src/analysis/expected_value.py
   - 方式: 条件付き期待値（4段階fallback）
   
   優先順位:
   1. 曜日×機種 (≥3サンプル)
   2. 曜日別 (≥3サンプル)
   3. 機種別 (≥1サンプル)
   4. 全体平均 (最後の砦)
   
   - 参照期間: 過去 90 日
   - 出力: expected_value, source, sample_count, confidence
```

**ファイル**: `src/analysis/expected_value.py`  
**関数**:
- `calculate_expected_value_by_machine()` - 機種別期待値
- `calculate_overall_expected_value()` - 全体期待値

#### パターン分析（改善版）
```python
✅ src/analysis/patterns.py
   - アルゴリズム: K-means クラスタリング
   - 特徴量（4個）: avg_diff, stddev_diff, volatility, win_rate
   - クラスタ数: 3
   - ラベル（中立化）:
     * high_variance_positive (高差枚・高変動)
     * stable_mid (中程度)
     * low_performance (低差枚)
   - 出力: パターン別要約統計
```

**ファイル**: `src/analysis/patterns.py`

---

### Phase 4: 検証・API層

#### 予測検証モジュール
```python
✅ src/analysis/evaluation.py
   - 機能: 過去予測と実績の突合
   - 検証項目:
     * accuracy, precision, recall, f1
     * 予測ラベル vs 実績ラベルの比較
     * was_correct フラグ記録
```

**ファイル**: `src/analysis/evaluation.py`  
**関数**:
- `verify_predictions()` - 指定日の予測を検証
- `get_model_evaluation_stats()` - N日間の統計

#### API ルーター（再設計）
```python
✅ src/routers/analysis.py
   
   【スロット専用エンドポイント】
   GET /api/analysis/slots/predictions
     - 当たり確率 Top 10
   
   GET /api/analysis/slots/dashboard
     - 統合ダッシュボード
     - 期待値ランキング
     - パターン分析
     - モデル評価指標
   
   【パチンコ専用エンドポイント】
   GET /api/analysis/pachinko/expected-value
     - パチンコ期待値ランキング
   
   【検証エンドポイント】
   GET /api/evaluation/verify
     - 予測結果検証
   
   GET /api/evaluation/stats
     - 評価統計（過去N日）
   
   【レガシー（互換性維持）】
   GET /api/expected-value
   GET /api/patterns
   GET /api/dashboard
```

**ファイル**: `src/routers/analysis.py`

#### 依存関係更新
```
✅ requirements.txt
   - lightgbm==4.1.0 追加（LightGBM対応準備）
```

---

## 📊 現在のシステムアーキテクチャ

```
【データフロー】

スクレイパー (scraper.py)
    ↓
daily_results (既存)
    ↓
daily_machine_stats (集計層)
    ↓
ml_features (特徴量層)
    ↓
slots.py (学習・予測)
    ↓
slot_predictions (予測結果DB保存)
    ↓
evaluation.py (検証・精度評価)
    ↓
API ルーター (analysis.py)
    ↓
ダッシュボード (dashboard.html)


【モジュール責務】
features.py
  ├─ 生データから特徴量生成
  ├─ NaN処理・標準化
  └─ DB へ INSERT

slots.py
  ├─ RandomForestClassifier 学習
  ├─ 当たり確率予測
  └─ 評価指標計算

expected_value.py
  ├─ 条件付き期待値（4段階）
  └─ 信頼度計算

patterns.py
  ├─ K-means クラスタリング
  └─ パターン別要約

evaluation.py
  ├─ 予測と実績の突合
  └─ 精度指標自動計算

analysis.py (ルーター)
  └─ 上記モジュールを API で公開
```

---

## ⏳ 実装残（Phase 3, 5, 補完）

### Phase 3: パチンコ分析（未実装）

**必要な新規モジュール**
```
src/analysis/pachinko.py
   - 統計ベース分析（ML不要）
   - 期待値、曜日別傾向、信頼区間
   - スロットと異なる特徴量セット
```

**優先度**: 中（スロット完成後）

---

### Phase 5: ダッシュボード UI 更新（部分実装）

**現状**
- `backend/dashboard.html` 存在
- 旧エンドポイント対応（古い API）
- スロット/パチンコ分離表示なし

**必要な修正**
```html
1. 新エンドポイント対応
   - /api/analysis/slots/dashboard
   - /api/analysis/slots/predictions
   - /api/evaluation/stats

2. 表示内容の追加
   - 当たり確率ランキング（Top 10）
   - 期待値ランキング（条件付き）
   - モデル評価指標パネル
   - 検証統計グラフ

3. UI/UX 改善
   - タブ分離（スロット/パチンコ）
   - モデル信頼度の可視化
   - 実績との比較表示
```

**優先度**: 高（Phase 4 後すぐ）

---

### 補完実装: データ流路の完成

#### 1. スクレイパー修正（raw_machine_data 蓄積）
```python
現状: daily_results へ保存
必要: raw_machine_data へ保存（生データ蓄積）

修正箇所: src/routers/scraper.py
  └─ crud.insert_raw_machine_data() 呼び出し追加
```

**優先度**: 高

#### 2. daily_machine_stats 集計パイプライン
```python
必要な機能:
  - daily_results → daily_machine_stats の日次集計ジョブ
  - APScheduler に登録（夜間に実行）
  
ファイル案: src/scheduler/aggregation_job.py
```

**優先度**: 高（特徴量生成に必須）

#### 3. ml_features 自動生成パイプライン
```python
現状: generate_features_for_training() は存在
必要: APScheduler で毎日実行

ファイル案: src/scheduler/feature_generation_job.py
  - 毎日深夜に実行
  - prediction_date = today として特徴量生成
  - 過去60日のデータを使用
```

**優先度**: 高

#### 4. 予測結果DB保存パイプライン
```python
現状: API で予測実行時に保存
必要: スケジューラで自動化

ファイル案: src/scheduler/prediction_job.py
  - 毎朝 prediction_date = today で予測実行
  - slot_predictions テーブルに自動保存
```

**優先度**: 中

---

## 🔧 技術スタック

| レイヤー | 技術 |
|---------|------|
| **バックエンド** | FastAPI, SQLAlchemy, Pydantic |
| **ML・分析** | scikit-learn (RF), pandas, numpy |
| **ML（準備済み）** | LightGBM (4.1.0) |
| **DB** | PostgreSQL |
| **スクレイピング** | Selenium, BeautifulSoup |
| **スケジューラ** | APScheduler |
| **フロントエンド** | HTML/CSS/JavaScript (Vanilla) |
| **コンテナ** | Docker, Docker Compose |

---

## 📈 学習データ要件

| 項目 | 値 |
|------|-----|
| **学習対象期間** | prediction_date より前 60 日 |
| **テスト対象期間** | prediction_date より前 7 日 |
| **当日データ** | ❌ 除外（データリーク防止） |
| **最小サンプル数** | 30（学習） |
| **特徴量数** | 17個 |
| **ラベル定義** | diff > 1000 = 1, else = 0 |

---

## 🚀 実行例

### 1. スロット当たり確率予測
```bash
curl http://localhost:8000/api/analysis/slots/predictions?store_id=1 | jq .

# 出力:
{
  "status": "success",
  "store_id": 1,
  "machine_type": "スロット",
  "predictions": [
    {
      "machine_id": 15,
      "machine_name": "Lバジリスク絆2",
      "hit_probability": 0.78,
      "expected_value": 450.5,
      "confidence_score": 0.78
    },
    ...
  ],
  "total_count": 82
}
```

### 2. スロット統合ダッシュボード
```bash
curl http://localhost:8000/api/analysis/slots/dashboard?store_id=1 | jq .

# 出力:
{
  "status": "success",
  "overall_expected_value": {...},
  "hit_probability_predictions": [...],
  "expected_value_ranking": [...],
  "patterns": [...],
  "model_evaluation": {
    "overall_accuracy": 0.82,
    "daily_stats": [...]
  },
  "metadata": {
    "hit_threshold": 1000,
    "feature_columns": [...],
    "data_period_days": 30
  }
}
```

### 3. 予測検証
```bash
curl http://localhost:8000/api/evaluation/verify?store_id=1&days_back=1

# 出力:
{
  "status": "success",
  "verification_date": "2026-04-10",
  "verified_count": 82,
  "accuracy": 0.82,
  "precision": 0.85,
  "recall": 0.79,
  "f1": 0.82
}
```

---

## 📋 今後の優先順位

> **2026-08-17 更新**: 下記 1〜6 はコード検証により実装済みを確認。
> スケジューラ各ジョブは分割ファイルではなく `backend/src/scheduler/jobs.py` に集約
> （scrape 01:00 → aggregate 02:00 → features 02:30 → predict 03:00）。

```
【実装済み（確認済み）】
1. ✅ スクレイパー修正 → raw_machine_data 蓄積        (routers/scraper.py)
2. ✅ daily_machine_stats 集計ジョブ                 (jobs.py:aggregate_daily_stats_job)
3. ✅ ml_features 自動生成ジョブ                     (jobs.py:generate_ml_features_job)
4. ✅ ダッシュボード UI 更新（残: E2E疎通検証=#4）    (dashboard.html)
5. ✅ パチンコ分析モジュール (pachinko.py)
6. ✅ 予測結果自動保存ジョブ                         (jobs.py:run_daily_predictions_job)

【真の残タスク】
7. ⏳ ダッシュボード詳細表示（SHAP等）  → Issue #7

【今後の改善】
8. 🔮 LightGBM への切り替え
9. 🔮 Hyperパラメータ最適化 (Optuna)
10. 🔮 複数店舗対応（モデル共用 vs 店舗別）
11. 🔮 外部特徴量（イベント日、天候等）
12. 🔮 長期予測（1日先 → 1週先）
```

---

## ✨ 現在の成果

| 項目 | 状態 |
|------|------|
| **ML モデル** | ✅ 実装済み（RandomForest） |
| **API エンドポイント** | ✅ 実装済み（6個） |
| **特徴量管理** | ✅ 統一・共通化済み |
| **予測検証** | ✅ 実装済み |
| **当日データ除外** | ✅ 実装済み |
| **DB 設計** | ✅ 完成 |
| **スロット分析** | ✅ 完成 |
| **パチンコ分析** | ✅ 実装済み（統計ベース pachinko.py） |
| **ダッシュボード** | ✅ 新EP対応済み（残: E2E疎通検証 #4） |
| **スケジューラ統合** | ✅ jobs.py に集約（scrape/aggregate/features/predict） |

---

## 📝 次のステップ

**本期間中（推奨）**:
1. スクレイパー修正（raw_machine_data へ）
2. 集計・特徴量ジョブの自動化
3. ダッシュボード UI 完成

**その後**:
4. パチンコ分析モジュール実装
5. 全体的な検証・負荷テスト

---

**プロジェクト開始日**: 2026-03-05  
**本実装開始日**: 2026-04-11  
**次マイルストーン**: 2026-04-25（ダッシュボード完成 + 自動化）
