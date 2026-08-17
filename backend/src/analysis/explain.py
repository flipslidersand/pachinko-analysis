"""SHAP による予測寄与度（説明性）の算出

slots.py の当たり確率モデル（RandomForestClassifier）に対し、
各予測がどの特徴量にどれだけ押し引きされたかを SHAP で算出する。

- compute_shap_contributions(): 学習済みモデル + 特徴量行列から寄与度を返す純関数
- explain_store_predictions(): 店舗の最新予測日について、台ごとの top-N 寄与を返す
"""
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np
import shap
from sqlalchemy.orm import Session

from src.analysis import slots
from src.analysis.features import generate_features_for_training

logger = logging.getLogger(__name__)


def compute_shap_contributions(
    model,
    X_scaled: np.ndarray,
    feature_cols: List[str],
    top_n: int = 5,
) -> List[Dict]:
    """学習済みツリーモデルの各サンプル予測に対する feature 寄与度を SHAP で算出。

    Args:
        model: 学習済みツリーモデル（RandomForestClassifier 等）
        X_scaled: 標準化済み特徴量行列 (n_samples, n_features)
        feature_cols: 特徴量名（X_scaled の列順と一致）
        top_n: 返す上位寄与特徴量の数

    Returns:
        サンプルごとの寄与度辞書のリスト。各要素:
        {
            "base_value": float,                     # 期待値（当たり側）
            "top_features": [
                {"feature": str, "shap_value": float, "direction": "up"|"down"}
            ]
        }
    """
    if X_scaled.shape[0] == 0:
        return []

    explainer = shap.TreeExplainer(model)
    raw = explainer.shap_values(X_scaled)

    # RandomForestClassifier（2クラス）の shap 出力はバージョンで形が異なる:
    #  - list [class0_array, class1_array]
    #  - ndarray (n_samples, n_features)        … 単一出力
    #  - ndarray (n_samples, n_features, n_class) … 3次元
    # いずれも「当たり(class=1)」側の寄与に正規化する。
    if isinstance(raw, list):
        sv = np.asarray(raw[1] if len(raw) > 1 else raw[0])
    else:
        arr = np.asarray(raw)
        sv = arr[:, :, 1] if arr.ndim == 3 else arr

    # base value（期待値）も同様にクラス1側を取り出す
    ev = explainer.expected_value
    if isinstance(ev, (list, np.ndarray)):
        ev_arr = np.asarray(ev).ravel()
        base_value = float(ev_arr[1] if ev_arr.size > 1 else ev_arr[0])
    else:
        base_value = float(ev)

    results: List[Dict] = []
    for i in range(sv.shape[0]):
        row = sv[i]
        # 絶対値の大きい順に top_n
        order = np.argsort(np.abs(row))[::-1][:top_n]
        top_features = [
            {
                "feature": feature_cols[j],
                "shap_value": float(row[j]),
                "direction": "up" if row[j] >= 0 else "down",
            }
            for j in order
        ]
        results.append({"base_value": base_value, "top_features": top_features})

    return results


def explain_store_predictions(
    db: Session,
    store_id: int,
    prediction_date: Optional[date] = None,
    training_days: int = 60,
    top_n: int = 5,
) -> List[Dict]:
    """店舗の予測対象日について、台ごとの当たり確率と SHAP 寄与度を返す。

    予測対象日は未指定なら daily_machine_stats の最新日（＝直近スクレイプ済み日）。
    slots.predict_hit_probability と同じ特徴量生成・標準化経路を使う。

    Returns:
        [{ "machine_id", "machine_name", "hit_probability",
           "base_value", "top_features": [...] }]
    """
    try:
        if prediction_date is None:
            from sqlalchemy import text

            prediction_date = db.execute(
                text(
                    "SELECT MAX(target_date) FROM daily_machine_stats WHERE store_id = :sid"
                ),
                {"sid": store_id},
            ).scalar()
            if prediction_date is None:
                logger.warning(f"⚠️ No aggregated stats for store {store_id}")
                return []

        # モデルを学習（prediction_date より前のデータのみ）
        model_info = slots.train_hit_probability_model(
            db, store_id=store_id, prediction_date=prediction_date, training_days=training_days
        )
        if not model_info:
            logger.warning("⚠️ Failed to train model for explanation")
            return []

        model = model_info["model"]
        scaler = model_info["scaler"]
        feature_cols = model_info["feature_cols"]

        # 予測対象日の特徴量を生成（predict と同じ手順）
        features_for_pred = generate_features_for_training(
            db,
            store_id=store_id,
            machine_type="S",
            prediction_date=prediction_date + timedelta(days=1),
            lookback_days=training_days,
        )
        features_for_pred = features_for_pred[
            features_for_pred["feature_date"] == prediction_date
        ].reset_index(drop=True)

        if features_for_pred.empty:
            logger.warning("⚠️ No features for explanation date")
            return []

        features_for_pred[feature_cols] = features_for_pred[feature_cols].fillna(0)
        X = features_for_pred[feature_cols].values
        X_scaled = scaler.transform(X)

        hit_proba = model.predict_proba(X_scaled)[:, 1]
        contributions = compute_shap_contributions(model, X_scaled, feature_cols, top_n=top_n)

        results: List[Dict] = []
        for idx, row in features_for_pred.iterrows():
            contrib = contributions[idx] if idx < len(contributions) else {}
            results.append(
                {
                    "machine_id": int(row["machine_id"]),
                    "machine_name": row["machine_name"],
                    "hit_probability": float(hit_proba[idx]),
                    "base_value": contrib.get("base_value"),
                    "top_features": contrib.get("top_features", []),
                }
            )

        # 当たり確率降順
        results = sorted(results, key=lambda x: x["hit_probability"], reverse=True)
        logger.info(f"✅ Explained {len(results)} predictions for store {store_id}")
        return results

    except Exception as e:
        logger.error(f"❌ Error explaining predictions: {e}")
        return []
