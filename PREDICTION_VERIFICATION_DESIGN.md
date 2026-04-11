# 予測結果自動検証フロー - 設計書

**目的**: 朝の予測と営業終了後の実績を自動突合し、予測精度を検証・記録  
**前提**: 既存 raw → stats → features → predictions パイプラインを活用

---

## 1️⃣ 必要なデータ項目

### 予測時に保存すべき項目（slot_predictions）
```
既存:
- store_id
- machine_id
- prediction_date
- hit_probability

追加:
- prediction_timestamp (何時に予測したか)
- threshold_value (当時の閾値、後で変更可能にするため)
- predicted_label (0 or 1)
```

### 実績突合時に記録すべき項目（prediction_results テーブル）
```
基本:
- store_id
- machine_id
- prediction_date
- hit_probability (朝の予測値)
- predicted_label (朝の予測ラベル)

実績:
- actual_diff (営業終了後に取得)
- actual_label (0 or 1)
- was_correct (True/False)

メタデータ:
- verification_timestamp (検証実行時刻)
- verification_method ('auto' or 'manual')
- notes (デバッグ用)
```

---

## 2️⃣ 予測保存フロー

### タイミング: 朝 23:45 (run_daily_predictions_job)

```
朝の予測実行
  ├─ generate_ml_features() で当日の特徴量を生成
  ├─ RandomForestClassifier.predict_proba() で hit_probability 算出
  ├─ hit_probability >= 0.5 で predicted_label を決定
  └─ slot_predictions テーブルに保存
       └─ 追加: prediction_timestamp, threshold_value, predicted_label
```

### slot_predictions テーブルの役割
- **用途**: 当日の予測値をキャッシュ（実績との突合用）
- **保持期間**: 無期限（精度検証の履歴として）
- **索引**: (store_id, machine_id, prediction_date) に複合インデックス

---

## 3️⃣ 営業終了後の検証フロー

### タイミング: 毎晩 00:30 (新規ジョブ: verify_predictions_job)

```
Step 1: 昨日の実績データを取得
  └─ raw_machine_data or daily_machine_stats から
     target_date = yesterday の diff を取得

Step 2: 昨日の予測結果を取得
  └─ slot_predictions where prediction_date = yesterday

Step 3: 突合処理（機種ごと）
  └─ for each machine:
       ├─ actual_diff を取得
       ├─ actual_label = 1 if actual_diff > threshold else 0
       ├─ predicted_label = 予測時の値
       ├─ was_correct = (predicted_label == actual_label)
       └─ 結果を prediction_results に INSERT

Step 4: ログ出力
  └─ 正解数, 不正解数, 正解率(%) をログに記録
```

### 検証ジョブの特性
- **依存**: run_daily_predictions_job → aggregate_daily_stats_job → verify_predictions_job
- **冪等性**: 同じ日付で複数回実行しても OK（UPSERT で上書き）
- **エラーハンドリ**: データ不足時は skip（ログに警告）

---

## 4️⃣ 評価指標の優先順位

### Priority 1（必須）
1. **正解率** (Accuracy)
   - `count(was_correct) / total_count * 100`
   - 集計単位: 日別、店舗別、機種別

2. **精密度/再現率** (Precision/Recall)
   - Precision: `TP / (TP + FP)` （予測が当たりの中、実際に当たった率）
   - Recall: `TP / (TP + FN)` （実際に当たったもので、予測できた率）

### Priority 2（補助）
3. **予測分布**
   - 予測が当たりと予測した件数 / 全体
   - 実績で当たった件数 / 全体

4. **日別トレンド**
   - 7日移動平均の正解率推移

### Priority 3（参考）
5. **TopN 命中率**
   - top 10 の高確率機種での命中率

6. **差枚の相関性**
   - actual_diff と hit_probability の相関係数

---

## 5️⃣ DBテーブルの見直し

### 既存テーブルの役割整理

| テーブル | 用途 | 保持データ |
|----------|------|----------|
| **slot_predictions** | 予測値キャッシュ | 当日の hit_probability |
| **prediction_results** | 検証結果 | 予測値 + 実績値 + 判定結果 |
| **daily_machine_stats** | 統計値 | 日次の diff, games_count など |

### 必須変更
- `slot_predictions` に `predicted_label`, `threshold_value` カラム追加
- `prediction_results` に `verification_timestamp` カラム追加（検証時刻追跡）

### 推奨追加テーブル
- **prediction_evaluation_metrics** (集計結果用)
  ```
  store_id, evaluation_date, accuracy, precision, recall, 
  total_count, correct_count, incorrect_count
  ```
  - 用途: 日別評価の快速参照（ダッシュボード用）
  - 集計頻度: verify_predictions_job 実行後に自動計算
  - 索引: (store_id, evaluation_date)

---

## 6️⃣ Scheduler に追加すべきジョブ

### ジョブ 1: verify_predictions_job（新規）
```
CronTrigger(hour=0, minute=30)  # 毎晩 00:30
└─ 昨日分の予測と実績を突合
   └─ prediction_results に INSERT/UPDATE
   └─ prediction_evaluation_metrics に集計結果 INSERT
```

### ジョブ 2: aggregate_prediction_metrics（新規・オプション）
```
CronTrigger(hour=1, minute=0)  # 毎晩 01:00
└─ prediction_results から集計指標を計算
   └─ prediction_evaluation_metrics に集約
   └─ 用途: ダッシュボード高速化
```

### 既存ジョブの修正
- `run_daily_predictions_job` (23:45)
  - 予測時に `predicted_label`, `threshold_value` を一緒に保存

### スケジュール全体（修正後）
```
09:00 - Scrape Slots
09:30 - Scrape Pachinko
23:00 - Aggregate Daily Stats
23:30 - Generate ML Features
23:45 - Run Predictions        ← predicted_label 保存
00:30 - Verify Predictions     ← 昨日分の検証実行
01:00 - Aggregate Metrics      ← 集計結果の計算（オプション）
```

---

## 7️⃣ ダッシュボードに追加すべき項目

### 新規タブ: 「予測精度検証」

#### セクション 1: サマリー
```
日別の精度推移（7日間）
├─ 正解率グラフ（折れ線）
├─ 当たり予測件数 vs 実績当たり件数（横棒）
└─ 精密度/再現率（双軸）
```

#### セクション 2: 詳細分析
```
日別 × 評価指標マトリクス
├─ 日付別の正解率、精密度、再現率、サンプル数
├─ ソート機能: 正解率昇順/降順
└─ フィルタ: 日付範囲、店舗選択
```

#### セクション 3: 機種別パフォーマンス
```
機種ごとの命中率ランキング
├─ 機種名、正解率、サンプル数（ N >= 3 のみ表示）
├─ Top 10 / Bottom 5
└─ 信頼度バッジ（サンプル数で色分け）
```

#### セクション 4: しきい値分析（パラメータ感度）
```
閾値を変えた場合のシミュレーション
├─ スライダー: 0.3 - 0.7
└─ 正解率の変化を動的に表示
```

---

## 8️⃣ 実装優先順位

### Phase 1: 基礎検証フロー（高優先度）【1週間】
- [ ] `slot_predictions` に `predicted_label`, `threshold_value` 追加
- [ ] `prediction_results` テーブルの役割確定
- [ ] `verify_predictions_job` 実装
- [ ] 手動テスト（昨日分の予測と実績を突合して精度確認）
- [ ] スケジューラに登録・自動実行確認

**出口**: 毎晩の自動検証が動作すること

---

### Phase 2: 評価指標計算（中優先度）【1週間】
- [ ] `prediction_evaluation_metrics` テーブル作成
- [ ] 正解率、精密度、再現率の計算ロジック実装
- [ ] `aggregate_prediction_metrics` ジョブ実装
- [ ] 集計結果のログ出力確認

**出口**: 日別・店舗別の評価指標が自動計算されること

---

### Phase 3: ダッシュボード（中優先度）【2週間】
- [ ] API エンドポイント: `/evaluation/daily-metrics`
- [ ] API エンドポイント: `/evaluation/machine-ranking`
- [ ] フロント実装: 予測精度検証タブ
- [ ] グラフ表示（Chart.js）
- [ ] フィルタ・ソート機能

**出口**: ダッシュボードで予測精度が可視化されること

---

### Phase 4: パラメータ分析（低優先度）【1週間】
- [ ] 閾値感度分析ロジック
- [ ] シミュレーション API
- [ ] 動的グラフ表示

**出口**: 最適な閾値の提案が可能になること

---

## 📋 参考: 検証フローの全体図

```
朝（23:45）
  ↓ run_daily_predictions_job
  └─ hit_probability → predicted_label に変換
     └─ slot_predictions に保存 ✅

夜（00:30）
  ↓ verify_predictions_job
  └─ raw_machine_data から actual_diff を取得
     └─ actual_label に変換
        └─ predicted_label と比較
           └─ prediction_results に保存 ✅

夜（01:00）
  ↓ aggregate_prediction_metrics（オプション）
  └─ prediction_results から集計
     └─ prediction_evaluation_metrics に保存 ✅

朝
  ↓ ダッシュボード表示
  └─ prediction_evaluation_metrics を快速クエリ
     └─ 精度推移を表示 ✅
```

---

## ⚠️ 注意事項

### 1. 閾値の可変性
- `slot_predictions.threshold_value` に保存することで、後から変更可能に
- 評価指標の再計算は必要（が容易）

### 2. データの整合性
- 実績データが raw_machine_data に確定するタイミングを確認
  - 現在: 23:00 の aggregate_daily_stats_job で daily_machine_stats に確定
  - 検証タイミング 00:30 で十分なはず

### 3. エラーハンドリング
- 実績データがない場合: ジョブはスキップ（警告ログ出力）
- 予測データがない場合: 同上

### 4. パフォーマンス
- prediction_results は増え続けるテーブル
- 集計用テーブル `prediction_evaluation_metrics` で高速参照を実現

---

## 📌 まとめ

| 項目 | 内容 |
|------|------|
| **DBテーブル** | 既存 + 1つ追加（prediction_evaluation_metrics） |
| **ジョブ** | 2つ追加（verify_predictions_job, aggregate_prediction_metrics） |
| **カラム追加** | `slot_predictions` に 2列、`prediction_results` に 1列 |
| **ダッシュボード** | 新規タブ「予測精度検証」を追加 |
| **実装工数** | Phase 1-3 で約 4週間 |
| **破壊的変更** | なし（既存パイプラインは変更なし） |
