"""スロット専用分析・予測モデル"""
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from src.analysis.features import generate_features_for_training
from src.database import crud

logger = logging.getLogger(__name__)

# 定数
HIT_THRESHOLD = 1000
MODEL_VERSION = "v1.0"
MIN_SAMPLES_FOR_TRAINING = 30


def train_hit_probability_model(
    db: Session,
    store_id: int,
    prediction_date: date,
    training_days: int = 60,
    test_days: int = 7
) -> Optional[Dict]:
    """
    当たり確率予測モデルを学習

    Args:
        db: DB セッション
        store_id: 店舗ID
        prediction_date: 予測対象日（学習時はこの日より前のデータのみ使用）
        training_days: 学習対象期間（日数）
        test_days: テスト期間（日数）

    Returns:
        モデル評価指標
    """
    try:
        logger.info(
            f"🎓 Training hit probability model for store {store_id}, "
            f"prediction_date {prediction_date}"
        )

        # 特徴量を生成（prediction_date より前のデータのみ）
        features_df = generate_features_for_training(
            db,
            store_id=store_id,
            machine_type="S",
            prediction_date=prediction_date,
            lookback_days=training_days
        )

        if len(features_df) < MIN_SAMPLES_FOR_TRAINING:
            logger.warning(
                f"⚠️ Not enough samples for training: {len(features_df)} < {MIN_SAMPLES_FOR_TRAINING}"
            )
            return None

        # 特徴量とラベルを分離
        feature_cols = [
            "day_of_week",
            "prev_1d_diff", "prev_2d_diff", "prev_3d_diff",
            "avg_3d_diff", "avg_7d_diff", "avg_30d_diff",
            "stddev_3d", "stddev_7d", "stddev_30d",
            "trend_up_days_7d", "trend_down_days_7d",
            "positive_ratio_7d",
            "max_diff_30d", "min_diff_30d", "volatility_30d",
            "total_games_1d"
        ]

        # NaN処理
        features_df[feature_cols] = features_df[feature_cols].fillna(0)

        X = features_df[feature_cols].values
        y = features_df["hit_label"].values

        # 学習 / テストセット分割（時系列順）
        test_size = int(len(features_df) * (test_days / training_days))
        X_train = X[:-test_size] if test_size > 0 else X
        y_train = y[:-test_size] if test_size > 0 else y
        X_test = X[-test_size:] if test_size > 0 else X
        y_test = y[-test_size:] if test_size > 0 else y

        # 標準化
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # モデル学習
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=15,
            min_samples_split=10,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train_scaled, y_train)

        # 評価
        y_pred = model.predict(X_test_scaled)
        y_pred_proba = model.predict_proba(X_test_scaled)[:, 1]

        accuracy = float(accuracy_score(y_test, y_pred))
        precision = float(precision_score(y_test, y_pred, zero_division=0))
        recall = float(recall_score(y_test, y_pred, zero_division=0))
        f1 = float(f1_score(y_test, y_pred, zero_division=0))

        try:
            roc_auc = float(roc_auc_score(y_test, y_pred_proba))
        except ValueError:
            roc_auc = None

        logger.info(
            f"✅ Model trained. "
            f"Accuracy={accuracy:.3f}, Precision={precision:.3f}, "
            f"Recall={recall:.3f}, F1={f1:.3f}"
        )

        return {
            "model": model,
            "scaler": scaler,
            "feature_cols": feature_cols,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "roc_auc": roc_auc,
            "samples_train": len(X_train),
            "samples_test": len(X_test),
        }

    except Exception as e:
        logger.error(f"❌ Error training model: {e}")
        return None


def predict_hit_probability(
    db: Session,
    store_id: int,
    prediction_date: date = None,
    training_days: int = 60
) -> List[Dict]:
    """
    本日の当たり確率を予測

    Args:
        db: DB セッション
        store_id: 店舗ID
        prediction_date: 予測対象日（None=本日）
        training_days: 学習対象期間

    Returns:
        予測結果リスト
    """
    try:
        if prediction_date is None:
            # 予測対象日は「集計済みの最新日（＝直近スクレイプ済み日）」に解決する。
            # 当日(date.today())は aggregate が除外して stats 行が無いため、
            # 当日固定だと常に "No features" で 0 件になる（#11 問題B と同根）。
            from sqlalchemy import text

            prediction_date = db.execute(
                text(
                    "SELECT MAX(target_date) FROM daily_machine_stats WHERE store_id = :sid"
                ),
                {"sid": store_id},
            ).scalar()
            if prediction_date is None:
                prediction_date = date.today()

        logger.info(f"🔮 Predicting hit probability for store {store_id}, date {prediction_date}")

        # モデルを学習
        model_info = train_hit_probability_model(
            db,
            store_id=store_id,
            prediction_date=prediction_date,
            training_days=training_days
        )

        if not model_info:
            logger.warning("⚠️ Failed to train model")
            return []

        model = model_info["model"]
        scaler = model_info["scaler"]
        feature_cols = model_info["feature_cols"]

        # 予測用特徴量を生成（prediction_date-1 までのデータで）
        # 本日の特徴量を生成するには前日までのデータが必要
        features_for_pred = generate_features_for_training(
            db,
            store_id=store_id,
            machine_type="S",
            prediction_date=prediction_date + timedelta(days=1),  # 本日を含めるため+1
            lookback_days=training_days
        )

        # 最新日のデータだけをフィルタ
        # reset_index が必須：フィルタ後も元の行ラベルが残ると、下の
        # hit_proba[idx]（位置ベースの numpy 配列）と添字がずれて IndexError になる
        features_for_pred = features_for_pred[
            features_for_pred["feature_date"] == (prediction_date - timedelta(days=0))
        ].reset_index(drop=True)

        if features_for_pred.empty:
            logger.warning("⚠️ No features for prediction date")
            return []

        # NaN処理
        features_for_pred[feature_cols] = features_for_pred[feature_cols].fillna(0)

        X_pred = features_for_pred[feature_cols].values
        X_pred_scaled = scaler.transform(X_pred)

        # 予測
        hit_proba = model.predict_proba(X_pred_scaled)[:, 1]

        # 機種情報を取得
        results = []
        for idx, row in features_for_pred.iterrows():
            machine_id = int(row["machine_id"])
            machine_name = row["machine_name"]
            hit_prob = float(hit_proba[idx])

            # 期待値を計算（簡易的：過去平均 * 当たり確率）
            expected_value = float(row["avg_7d_diff"] * hit_prob) if row["avg_7d_diff"] else 0.0

            result = {
                "machine_id": machine_id,
                "machine_name": machine_name,
                "hit_probability": hit_prob,
                "expected_value": expected_value,
                "confidence_score": max(hit_prob, 1.0 - hit_prob),  # 確信度
                "feature_date": str(row["feature_date"]),
            }

            results.append(result)

            # DB に保存
            crud.insert_slot_prediction(
                db,
                store_id=store_id,
                machine_id=machine_id,
                prediction_date=prediction_date,
                model_version=MODEL_VERSION,
                hit_probability=hit_prob,
                expected_value=expected_value,
                confidence_score=result["confidence_score"]
            )

        # ランキングソート（当たり確率降順）
        results = sorted(results, key=lambda x: x["hit_probability"], reverse=True)

        logger.info(f"✅ Predicted {len(results)} machines")

        return results

    except Exception as e:
        logger.error(f"❌ Error predicting: {e}")
        return []


def get_prediction_metadata(model_info: Dict) -> Dict:
    """
    予測モデルのメタ情報を取得

    Returns:
        メタ情報
    """
    return {
        "model_version": MODEL_VERSION,
        "accuracy": model_info.get("accuracy"),
        "precision": model_info.get("precision"),
        "recall": model_info.get("recall"),
        "f1": model_info.get("f1"),
        "roc_auc": model_info.get("roc_auc"),
        "samples_train": model_info.get("samples_train"),
        "samples_test": model_info.get("samples_test"),
        "hit_threshold": HIT_THRESHOLD,
    }
