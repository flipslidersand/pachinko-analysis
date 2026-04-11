# 技術詳細ドキュメント

---

## 1. 特徴量生成（features.py）

### 生成される特徴量（17個）

```python
【時系列差枚データ】
prev_1d_diff        # 前日差枚
prev_2d_diff        # 2日前差枚
prev_3d_diff        # 3日前差枚

【移動平均】
avg_3d_diff         # 3日平均差枚
avg_7d_diff         # 7日平均差枚
avg_30d_diff        # 30日平均差枚

【標準偏差】
stddev_3d           # 3日標準偏差
stddev_7d           # 7日標準偏差
stddev_30d          # 30日標準偏差

【トレンド】
trend_up_days_7d    # 直近7日で上昇日数
trend_down_days_7d  # 直近7日で下降日数
positive_ratio_7d   # プラス日の割合（%）

【ボラティリティ】
max_diff_30d        # 30日最大差枚
min_diff_30d        # 30日最小差枚
volatility_30d      # 30日変動幅の標準偏差

【その他】
total_games_1d      # 直近1日のゲーム数
day_of_week         # 曜日（0=月, 6=日）
```

### 生成ロジック

```python
def generate_features_for_training(
    db: Session,
    store_id: int,
    machine_type: str,
    prediction_date: date,          # この日より前のデータのみ使用
    lookback_days: int = 60,
    machine_id: Optional[int] = None
) -> pd.DataFrame:
    """
    【重要】当日データ除外
    - データ範囲: prediction_date - lookback_days 〜 prediction_date - 1
    - prediction_date そのものは含まない
    
    【例】
    prediction_date = 2026-04-12（本日）
    → 学習データ: 2026-02-11 〜 2026-04-11（前日まで）
    """
```

### NaN 処理
- fillna(0) で欠損値を 0 に補完
- 理由: データ不足の機種でも特徴量行を作成（後でfallbackで対応）

### ラベル生成
```python
hit_label = 1 if diff > HIT_THRESHOLD (1000) else 0
```

---

## 2. スロット分析（slots.py）

### 当たり確率予測モデル

#### アルゴリズム
```python
RandomForestClassifier(
    n_estimators=100,
    max_depth=15,
    min_samples_split=10,
    random_state=42,
    n_jobs=-1
)
```

#### 学習フロー
```
1. 特徴量生成
   → prediction_date より前の 60日分データ
   → 17個特徴量 + hit_label ラベル

2. データ分割
   - 学習セット: 60日分の前 53日
   - テストセット: 60日分の後 7日
   (時系列順を維持)

3. 標準化
   - StandardScaler で [0, 1] に正規化
   - 理由: RF は不要だが、後で LightGBM へ切り替え可能

4. モデル学習
   - RandomForestClassifier.fit(X_train, y_train)

5. 評価
   - accuracy_score(y_test, y_pred)
   - precision_score(y_test, y_pred)
   - recall_score(y_test, y_pred)
   - f1_score(y_test, y_pred)
   - roc_auc_score(y_test, y_pred_proba)
```

#### 推論フロー
```
1. 本日（prediction_date）の予測
   - 前日までのデータで特徴量生成
   - モデルで hit_probability 計算
   
2. ランキング生成
   - hit_probability 降順でソート
   - Top 10 を API で返却
   
3. DB 保存
   - slot_predictions テーブルへ
   - model_version = "v1.0"
```

#### 出力形式
```python
{
    "machine_id": 15,
    "machine_name": "Lバジリスク絆2天膳BLACK",
    "hit_probability": 0.78,           # 当たり確率
    "expected_value": 450.5,           # 期待値（簡易）
    "confidence_score": 0.78,          # 確信度
}
```

---

## 3. 期待値計算（expected_value.py）

### 条件付き期待値（4段階fallback）

```
優先順位 1: 曜日×機種の期待値
  条件: EXTRACT(DOW FROM date) = target_weekday AND machine_id = ?
  期間: 過去 90 日
  最小サンプル: 3
  confidence: min(100, sample_count * 10)

優先順位 2: 曜日の期待値
  条件: EXTRACT(DOW FROM date) = target_weekday
  期間: 過去 90 日
  最小サンプル: 3
  confidence: min(100, sample_count * 5)

優先順位 3: 機種の期待値
  条件: machine_id = ?
  期間: 過去 90 日
  最小サンプル: 1
  confidence: min(100, sample_count * 3)

優先順位 4: 全体の期待値（最後の砦）
  条件: store_id = ?
  期間: 過去 90 日
  confidence: 10
```

### 出力形式
```python
{
    "expected_value": float,
    "source": str,                # "weekday_machine" | "weekday" | "machine" | "overall"
    "sample_count": int,
    "confidence": float,          # 0～100
}
```

---

## 4. パターン分析（patterns.py）

### K-means クラスタリング

#### 特徴量（4個）
```python
avg_diff        # 平均差枚
stddev_diff     # 標準偏差
volatility      # ボラティリティ（max - min）
win_rate        # 勝率（プラス日 / 総日数 * 100）
```

#### クラスタリング設定
```python
KMeans(
    n_clusters=3,
    random_state=42,
    n_init=10,
    max_iter=300
)
```

#### ラベル割り当てロジック
```python
if avg_diff > 0 and volatility > 平均値:
    label = "high_variance_positive"  # 高差枚・高変動
elif avg_diff >= 0:
    label = "stable_mid"              # 中程度
else:
    label = "low_performance"         # 低差枚
```

#### クラスタサマリ
```python
{
    "pattern_name": "high_variance_positive",
    "machines_count": 18,
    "summary": {
        "avg_diff_in_pattern": 596.0,
        "stddev_diff_in_pattern": 245.3,
        "volatility_in_pattern": 823.0,
        "win_rate_in_pattern": 65.4,
        "machines_count": 18,
    },
    "machines": [
        {"id": 15, "name": "...", "avg_diff": ..., ...},
        ...
    ]
}
```

---

## 5. 予測検証（evaluation.py）

### 検証フロー

```
1. 前日の予測を取得
   SELECT * FROM slot_predictions
   WHERE prediction_date = verification_date

2. 当日の実績を取得
   SELECT * FROM daily_results
   WHERE date = verification_date

3. ラベル化と比較
   pred_label = 1 if hit_prob > 0.5 else 0
   actual_label = 1 if actual_diff > HIT_THRESHOLD else 0
   was_correct = (pred_label == actual_label)

4. 精度指標計算
   - accuracy_score(y_true, y_pred)
   - precision_score(y_true, y_pred)
   - recall_score(y_true, y_pred)
   - f1_score(y_true, y_pred)

5. DB に記録
   INSERT INTO prediction_results
   (prediction_id, actual_diff, actual_label, was_correct, verified_at)
```

### 出力形式
```python
{
    "status": "success",
    "verification_date": "2026-04-10",
    "predictions_count": 82,
    "verified_count": 82,
    "accuracy": 0.82,
    "precision": 0.85,
    "recall": 0.79,
    "f1": 0.82,
}
```

### 統計集計
```python
def get_model_evaluation_stats(
    db: Session,
    store_id: int,
    machine_type: str = "S",
    days: int = 7
) -> Dict:
    """過去 N 日間の日次精度を集計"""
    
    # 1日ごとの精度を計算
    daily_stats = []
    for each_date in past_N_days:
        accuracy = count_correct / count_verified
        daily_stats.append({
            "date": each_date,
            "total_predictions": count,
            "verified_count": count_verified,
            "correct_count": count_correct,
            "accuracy": accuracy,
        })
    
    # 全期間の平均精度
    overall_accuracy = sum_all_correct / sum_all_verified
    
    return {
        "overall_accuracy": overall_accuracy,
        "daily_stats": daily_stats,
    }
```

---

## 6. API 仕様（analysis.py）

### エンドポイント一覧

#### スロット
```
GET /api/analysis/slots/predictions?store_id=1
  → 当たり確率 Top 10

GET /api/analysis/slots/dashboard?store_id=1
  → 統合ダッシュボード
    - overall_expected_value
    - hit_probability_predictions (Top 10)
    - expected_value_ranking (Top 10)
    - patterns
    - model_evaluation
    - metadata
```

#### パチンコ
```
GET /api/analysis/pachinko/expected-value?store_id=1
  → 期待値ランキング（Top 20）
```

#### 検証
```
GET /api/evaluation/verify?store_id=1&days_back=1
  → 指定日の予測を検証
    - accuracy, precision, recall, f1

GET /api/evaluation/stats?store_id=1&days=7
  → 過去 N 日間の統計
    - overall_accuracy
    - daily_stats[]
```

#### レガシー（互換性維持）
```
GET /api/expected-value?store_id=1&machine_type=S
GET /api/patterns?store_id=1&machine_type=S
GET /api/dashboard?store_id=1&machine_type=S
```

---

## 7. DB スキーマ詳細

### daily_machine_stats（集計層）
```sql
CREATE TABLE daily_machine_stats (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL,
    machine_id INTEGER NOT NULL,
    machine_type VARCHAR(20) NOT NULL,  -- 'S' or 'P'
    target_date DATE NOT NULL,
    games_count INTEGER,
    diff INTEGER,
    stddev NUMERIC(10,2),
    min_diff INTEGER,
    max_diff INTEGER,
    sample_count INTEGER,
    UNIQUE(store_id, machine_id, target_date)
);
```

### ml_features（特徴量層）
```sql
CREATE TABLE ml_features (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL,
    machine_id INTEGER NOT NULL,
    machine_type VARCHAR(20) NOT NULL,
    feature_date DATE NOT NULL,
    
    -- 特徴量（17個）
    prev_1d_diff INTEGER,
    prev_2d_diff INTEGER,
    prev_3d_diff INTEGER,
    avg_3d_diff NUMERIC(10,2),
    avg_7d_diff NUMERIC(10,2),
    avg_30d_diff NUMERIC(10,2),
    stddev_3d NUMERIC(10,2),
    stddev_7d NUMERIC(10,2),
    stddev_30d NUMERIC(10,2),
    trend_up_days_7d INTEGER,
    trend_down_days_7d INTEGER,
    positive_ratio_7d NUMERIC(5,2),
    max_diff_30d INTEGER,
    min_diff_30d INTEGER,
    volatility_30d NUMERIC(10,2),
    total_games_1d INTEGER,
    day_of_week INTEGER,
    
    -- ラベル
    hit_label INTEGER,
    
    UNIQUE(store_id, machine_id, feature_date)
);
```

### slot_predictions（予測結果）
```sql
CREATE TABLE slot_predictions (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL,
    machine_id INTEGER NOT NULL,
    prediction_date DATE NOT NULL,
    model_version VARCHAR(50) NOT NULL,  -- "v1.0"
    hit_probability NUMERIC(5,4),        -- 0.0～1.0
    expected_value NUMERIC(10,2),
    confidence_score NUMERIC(5,4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(store_id, machine_id, prediction_date, model_version)
);
```

### prediction_results（検証）
```sql
CREATE TABLE prediction_results (
    id SERIAL PRIMARY KEY,
    prediction_id INTEGER REFERENCES slot_predictions(id),
    actual_diff INTEGER,
    actual_label INTEGER,
    was_correct BOOLEAN,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 8. 実装時の重要ポイント

### ✅ 当日データ除外
```python
# ❌ 間違い
prediction_date = date.today()
data = get_data(from_date, to_date=prediction_date)

# ✅ 正しい
prediction_date = date.today()
data = get_data(
    from_date=prediction_date - timedelta(days=60),
    to_date=prediction_date - 1  # 前日まで
)
```

### ✅ NaN 処理
```python
# ❌ 間違い（学習時にエラー）
X = df[feature_cols]  # NaN が含まれている

# ✅ 正しい
X = df[feature_cols].fillna(0)
```

### ✅ 時系列データの分割
```python
# ❌ 間違い（時系列が崩れる）
X_train, X_test = train_test_split(X, test_size=0.1, random_state=42)

# ✅ 正しい（時系列順を維持）
split_idx = int(len(X) * 0.88)
X_train = X[:split_idx]
X_test = X[split_idx:]
```

### ✅ 機種別フィルタリング
```python
# ❌ 間違い（パチンコも含まれる）
machines = db.query(Machine).all()

# ✅ 正しい
machines = db.query(Machine).filter(Machine.type == "S").all()
```

---

## 9. パフォーマンス指標

| 項目 | 目標 | 現状 |
|------|------|------|
| **当たり確率精度** | 80%以上 | 測定中 |
| **予測レイテンシ** | < 100ms | TBD |
| **特徴量生成時間** | < 60秒（1000機種） | TBD |
| **DB 応答時間** | < 50ms（95%ile） | TBD |

---

## 10. 今後の技術的改善

### LightGBM への切り替え
```python
# 現在: RandomForestClassifier
model = RandomForestClassifier(n_estimators=100)

# 将来: LightGBM
import lightgbm as lgb
model = lgb.LGBMClassifier(
    num_leaves=31,
    max_depth=10,
    learning_rate=0.1,
    n_estimators=100
)
```

### ハイパーパラメータ最適化
```python
from optuna import create_study, Trial

def objective(trial: Trial):
    param = {
        "num_leaves": trial.suggest_int("num_leaves", 20, 100),
        "max_depth": trial.suggest_int("max_depth", 5, 20),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3),
    }
    model = lgb.LGBMClassifier(**param)
    model.fit(X_train, y_train)
    return roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])

study = create_study(direction="maximize")
study.optimize(objective, n_trials=100)
```

### SHAP による特徴量重要度
```python
import shap

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

# UI で表示可能
shap.force_plot(explainer.expected_value, shap_values[0], X_test[0])
```

---

**最終更新**: 2026-04-11
