"""予測検証・評価モジュール"""
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from src.database import crud

logger = logging.getLogger(__name__)

# 定数
HIT_THRESHOLD = 1000


def verify_predictions(
    db: Session,
    store_id: int,
    verification_date: date = None,
    machine_type: str = "S"
) -> Dict:
    """
    過去の予測と実績を突合して検証

    Args:
        db: DB セッション
        store_id: 店舗ID
        verification_date: 検証対象日（None=昨日）
        machine_type: 機種タイプ

    Returns:
        検証結果
    """
    if verification_date is None:
        verification_date = date.today() - timedelta(days=1)

    try:
        logger.info(f"🔍 Verifying predictions for {verification_date}")

        # 前日の予測を取得
        sql_predictions = """
        SELECT
            sp.id,
            sp.machine_id,
            sp.hit_probability,
            dr.diff
        FROM slot_predictions sp
        LEFT JOIN daily_results dr ON sp.machine_id = dr.machine_id
            AND dr.store_id = :store_id
            AND dr.date = :verification_date
        WHERE sp.store_id = :store_id
            AND sp.prediction_date = :verification_date
        """

        result = db.execute(text(sql_predictions), {
            "store_id": store_id,
            "verification_date": verification_date,
        }).fetchall()

        if not result:
            logger.warning(f"⚠️ No predictions found for {verification_date}")
            return {
                "status": "no_data",
                "verification_date": str(verification_date),
                "predictions_count": 0,
            }

        verified_count = 0
        y_pred_label = []
        y_true_label = []

        for prediction_id, machine_id, hit_prob, actual_diff in result:
            if actual_diff is None:
                continue

            # ラベル化
            pred_label = 1 if hit_prob > 0.5 else 0
            actual_label = 1 if actual_diff > HIT_THRESHOLD else 0

            was_correct = pred_label == actual_label

            # 検証結果を保存
            crud.insert_prediction_result(
                db,
                prediction_id=prediction_id,
                actual_diff=int(actual_diff),
                actual_label=actual_label,
                was_correct=was_correct
            )

            y_pred_label.append(pred_label)
            y_true_label.append(actual_label)
            verified_count += 1

        if not y_pred_label:
            return {
                "status": "no_actual_data",
                "verification_date": str(verification_date),
                "predictions_count": len(result),
                "verified_count": 0,
            }

        # 評価指標を計算
        accuracy = float(accuracy_score(y_true_label, y_pred_label))
        precision = float(precision_score(y_true_label, y_pred_label, zero_division=0))
        recall = float(recall_score(y_true_label, y_pred_label, zero_division=0))
        f1 = float(f1_score(y_true_label, y_pred_label, zero_division=0))

        logger.info(
            f"✅ Verified {verified_count} predictions. "
            f"Accuracy={accuracy:.3f}, Precision={precision:.3f}, "
            f"Recall={recall:.3f}, F1={f1:.3f}"
        )

        return {
            "status": "success",
            "verification_date": str(verification_date),
            "predictions_count": len(result),
            "verified_count": verified_count,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    except Exception as e:
        logger.error(f"❌ Error verifying predictions: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


def get_model_evaluation_stats(
    db: Session,
    store_id: int,
    machine_type: str = "S",
    days: int = 7
) -> Dict:
    """
    過去 N 日間の予測評価統計を取得

    Args:
        db: DB セッション
        store_id: 店舗ID
        machine_type: 機種タイプ
        days: 評価対象日数

    Returns:
        評価統計
    """
    try:
        start_date = date.today() - timedelta(days=days)

        sql = """
        SELECT
            sp.prediction_date,
            COUNT(*) as total_preds,
            SUM(CASE WHEN pr.was_correct THEN 1 ELSE 0 END) as correct_count,
            COUNT(pr.id) as verified_count
        FROM slot_predictions sp
        LEFT JOIN prediction_results pr ON sp.id = pr.prediction_id
        WHERE sp.store_id = :store_id
            AND sp.prediction_date >= :start_date
            AND sp.prediction_date < :today
        GROUP BY sp.prediction_date
        ORDER BY sp.prediction_date DESC
        """

        result = db.execute(text(sql), {
            "store_id": store_id,
            "start_date": start_date,
            "today": date.today(),
        }).fetchall()

        if not result:
            return {
                "status": "no_data",
                "days": days,
            }

        stats_list = []
        total_correct = 0
        total_verified = 0

        for pred_date, total, correct, verified in result:
            accuracy = (correct / verified * 100) if verified > 0 else 0

            stats_list.append({
                "date": str(pred_date),
                "total_predictions": int(total),
                "verified_count": int(verified) if verified else 0,
                "correct_count": int(correct) if correct else 0,
                "accuracy": float(accuracy),
            })

            total_correct += correct if correct else 0
            total_verified += verified if verified else 0

        overall_accuracy = (total_correct / total_verified * 100) if total_verified > 0 else 0

        return {
            "status": "success",
            "days": days,
            "overall_accuracy": float(overall_accuracy),
            "total_predictions": sum(s["total_predictions"] for s in stats_list),
            "total_verified": total_verified,
            "daily_stats": stats_list,
        }

    except Exception as e:
        logger.error(f"❌ Error getting evaluation stats: {e}")
        return {
            "status": "error",
            "message": str(e),
        }
