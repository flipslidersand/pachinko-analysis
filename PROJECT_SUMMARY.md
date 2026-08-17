# パチスロ分析プロジェクト - プロジェクトサマリー

**2026-04-11 現在**

## 📊 一行説明
スロット営業データをスクレイピング → DB蓄積 → ML分析 → ダッシュボード表示する、実運用対応の予測・分析システム

---

## 🎯 主要機能

### 1. 当たり確率予測（スロット専用）
- **モデル**: RandomForestClassifier (LightGBM対応可)
- **入力**: 17個の時系列特徴量
- **出力**: 各台の当たり確率（0.0～1.0）
- **精度**: Accuracy/Precision/Recall/F1/ROC-AUC で検証可能

### 2. 条件付き期待値計算
- **方式**: 曜日×機種 → 曜日 → 機種 → 全体 の4段階fallback
- **信頼度**: サンプル数に応じて自動計算
- **用途**: 高精度が求められる機種別の収支予測

### 3. 出玉パターン分析
- **手法**: K-means クラスタリング
- **パターン**: high_variance_positive / stable_mid / low_performance
- **特徴量**: 平均差枚、変動性、勝率など

### 4. 予測検証・精度管理
- **機能**: 過去予測と実績を自動で突合
- **メトリクス**: accuracy, precision, recall, f1 自動計算
- **用途**: モデル改善の比較材料

---

## 🏗️ システム構成

```
Frontend
  ↓
API (FastAPI)
  ├─ /api/analysis/slots/predictions       ← 当たり確率 Top 10
  ├─ /api/analysis/slots/dashboard         ← 統合ダッシュボード
  ├─ /api/analysis/pachinko/expected-value ← パチンコ期待値
  ├─ /api/evaluation/verify                ← 予測検証
  └─ /api/evaluation/stats                 ← 評価統計
  
Analyzer (Python)
  ├─ slots.py          → 当たり確率予測
  ├─ expected_value.py → 期待値計算
  ├─ patterns.py       → パターン分析
  ├─ evaluation.py     → 検証・評価
  └─ features.py       → 特徴量生成（共通）

Database (PostgreSQL)
  ├─ daily_results      (既存：スクレイピング元)
  ├─ daily_machine_stats (新：集計層)
  ├─ ml_features         (新：特徴量層)
  ├─ slot_predictions    (新：予測結果)
  └─ prediction_results  (新：検証データ)

Scheduler (APScheduler)
  ├─ 9:00  → スロットスクレイピング
  ├─ 9:30  → パチンコスクレイピング
  └─ (準備中) 深夜 → 集計・特徴量生成・予測実行
```

---

## ✅ 実装完了リスト

### Phase 1: 基盤
- [x] DB テーブル設計（5テーブル）
- [x] 特徴量生成モジュール（features.py）
- [x] CRUD拡張（新テーブル対応）

### Phase 2: スロット分析
- [x] 当たり確率予測モデル（slots.py）
- [x] 条件付き期待値（expected_value.py）
- [x] パターン分析改善（patterns.py）

### Phase 4: 検証・API
- [x] 予測検証モジュール（evaluation.py）
- [x] API ルーター再設計（analysis.py）
- [x] LightGBM依存関係追加

---

## ⏳ 実装残タスク

> **2026-08-17 更新**: 下記「優先度：高／中」の大半は実装済みであることをコード検証で確認。
> スケジューラは分割ファイルではなく `scheduler/jobs.py` に集約されている。

### 優先度：高（すぐに必要）
- [x] スクレイパー修正 → raw_machine_data 蓄積 … `routers/scraper.py` 実装済
- [x] daily_machine_stats 集計ジョブ（APScheduler）… `jobs.py:aggregate_daily_stats_job` 02:00
- [x] ml_features 自動生成ジョブ（APScheduler）… `jobs.py:generate_ml_features_job` 02:30
- [x] ダッシュボード UI 更新 … `dashboard.html` 新EP対応済（残: E2E疎通検証 = Issue #4）

### 優先度：中（その次）
- [x] パチンコ分析モジュール（pachinko.py）… 実装済（統計ベース）
- [x] 予測結果自動保存ジョブ … `jobs.py:run_daily_predictions_job` 03:00
- [ ] ダッシュボード詳細グラフ追加（SHAP等）… Issue #7

### 優先度：低（今後の改善）
- [ ] LightGBM への切り替え
- [ ] Hyperパラメータ最適化
- [ ] 複数店舗対応
- [ ] 外部特徴量統合
- [ ] 長期予測機能

---

## 📂 ファイル構成（新規追加分）

```
backend/src/analysis/
  ├─ features.py          ✅ 特徴量生成（17個）
  ├─ slots.py             ✅ スロット分析（当たり確率）
  ├─ expected_value.py    ✅ 期待値計算（条件付き）
  ├─ patterns.py          ✅ パターン分析（K-means）
  └─ evaluation.py        ✅ 検証・精度計算

backend/src/routers/
  └─ analysis.py          ✅ API ルーター（6エンドポイント）

backend/src/database/
  ├─ migrations/001_init.sql ✅ テーブル設計（+5テーブル）
  └─ crud.py              ✅ CRUD 拡張

backend/requirements.txt   ✅ lightgbm==4.1.0 追加

backend/dashboard.html     ⏳ UI更新予定

backend/src/scheduler/
  └─ (新規作成予定)
     ├─ aggregation_job.py  集計ジョブ
     ├─ feature_generation_job.py  特徴量生成ジョブ
     └─ prediction_job.py   予測実行ジョブ
```

---

## 🚀 使用開始ガイド

### 1. 環境構築
```bash
cd pachinko-analysis
docker-compose up -d
```

### 2. API テスト
```bash
# スロット当たり確率予測
curl http://localhost:8000/api/analysis/slots/predictions?store_id=1

# スロット統合ダッシュボード
curl http://localhost:8000/api/analysis/slots/dashboard?store_id=1

# 予測検証
curl http://localhost:8000/api/evaluation/verify?store_id=1&days_back=1
```

### 3. ダッシュボード表示
```
http://localhost:8000/dashboard
```

---

## 💾 データ特性

| 項目 | 値 |
|------|-----|
| **スロット機種数** | 846台（SUPER CONCORDE 市野） |
| **パチンコ機種数** | 664台 |
| **学習対象期間** | prediction_date より前 60日 |
| **最小学習サンプル** | 30 |
| **当日データ** | ❌ 除外（データリーク防止） |
| **特徴量次元** | 17 |

---

## 📈 性能指標

**スロット当たり確率モデル（現在）**
- Accuracy: 建設中
- Precision: 建設中
- Recall: 建設中
- F1: 建設中

*今後の予測検証で確定*

---

## 👥 プロジェクト情報

- **開始**: 2026-03-05（計画）
- **本実装**: 2026-04-11
- **マイルストーン**: 2026-04-25（ダッシュボード完成 + 自動化）
- **目標完成**: 2026-05-11（パイロット3ヶ月運用）

---

## 🔗 関連ドキュメント

- [詳細実装状況](IMPLEMENTATION_STATUS.md)
- [プロジェクト計画](README.md)（別途作成推奨）

---

## ❓ よくある質問

**Q: 当たり確率とは何か？**  
A: 「差枚 > 1000 の成績となる確率」。各台について 0.0～1.0 で表示。

**Q: 期待値の「条件付き」とは？**  
A: 曜日や機種ごとの条件下での期待値。データが少ない時は自動的に広い条件にfallback。

**Q: パチンコには対応しないのか？**  
A: 現在はスロット優先。パチンコは統計ベースで期待値のみ（Phase 3で拡張予定）。

**Q: 当日データを学習に使わないのはなぜか？**  
A: 朝に予測するので、その日のデータはまだ不完全。前日までのデータだけで学習（データリーク防止）。

**Q: モデルはどの期間で自動更新されるか？**  
A: 毎日深夜に自動学習（APScheduler予定）。新しいデータが増えるたびにモデルが改善される。
