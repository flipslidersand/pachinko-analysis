"""分析 API ルーター（Phase 2 改善版）"""
import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.analysis import expected_value, patterns, slots, evaluation, pachinko, explain

logger = logging.getLogger(__name__)
router = APIRouter()


# ========== スロット分析エンドポイント ==========

@router.get("/slots/predictions")
async def get_slot_predictions(
    store_id: int,
    db: Session = Depends(get_db)
):
    """スロット当たり確率予測を取得（Top 10）

    Args:
        store_id: 店舗ID
        db: DB セッション

    Returns:
        当たり確率ランキング
    """
    try:
        logger.info(f"🎰 Predicting hit probability for store {store_id}")

        predictions = slots.predict_hit_probability(db, store_id)

        return {
            "status": "success",
            "store_id": store_id,
            "machine_type": "スロット",
            "predictions": predictions[:10],  # Top 10
            "total_count": len(predictions),
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/slots/dashboard")
async def get_slots_dashboard(
    store_id: int,
    db: Session = Depends(get_db)
):
    """スロット分析ダッシュボード（統合）

    Args:
        store_id: 店舗ID
        db: DB セッション

    Returns:
        スロット統合分析結果
    """
    try:
        logger.info(f"📊 Getting slots dashboard for store {store_id}")

        # 当たり確率予測
        predictions = slots.predict_hit_probability(db, store_id)

        # 期待値
        ev_list = expected_value.calculate_expected_value_by_machine(db, store_id, "S")
        overall_ev = expected_value.calculate_overall_expected_value(db, store_id, "S")

        # パターン分析
        patterns_result = patterns.analyze_machine_patterns(db, store_id, "S")

        # 評価指標
        eval_stats = evaluation.get_model_evaluation_stats(db, store_id, "S", days=7)

        return {
            "status": "success",
            "store_id": store_id,
            "machine_type": "スロット",
            "overall_expected_value": overall_ev,
            "hit_probability_predictions": predictions[:10],
            "expected_value_ranking": ev_list[:10],
            "patterns": patterns_result.get("patterns", []),
            "model_evaluation": eval_stats,
            "metadata": {
                "hit_threshold": 1000,
                "feature_columns": [
                    "day_of_week", "prev_1d_diff", "prev_2d_diff", "prev_3d_diff",
                    "avg_3d_diff", "avg_7d_diff", "avg_30d_diff",
                    "stddev_3d", "stddev_7d", "stddev_30d",
                    "trend_up_days_7d", "trend_down_days_7d", "positive_ratio_7d",
                    "max_diff_30d", "min_diff_30d", "volatility_30d"
                ],
                "data_period_days": overall_ev.get("data_period_days", 0),
            }
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/slots/explain")
async def explain_slot_predictions(
    store_id: int,
    machine_id: int = None,
    top_n: int = 5,
    db: Session = Depends(get_db)
):
    """スロット予測の根拠（SHAP 寄与度）を取得

    予測対象日は daily_machine_stats の最新日（＝直近スクレイプ済み日）。

    Args:
        store_id: 店舗ID
        machine_id: 特定台に絞る場合に指定（未指定で全台）
        top_n: 各予測で返す上位寄与特徴量の数
        db: DB セッション

    Returns:
        台ごとの hit_probability + base_value + top_features
    """
    try:
        logger.info(f"🔬 Explaining slot predictions for store {store_id}")

        explanations = explain.explain_store_predictions(db, store_id, top_n=top_n)

        if machine_id is not None:
            explanations = [e for e in explanations if e["machine_id"] == machine_id]

        return {
            "status": "success",
            "store_id": store_id,
            "machine_type": "スロット",
            "explanations": explanations,
            "total_count": len(explanations),
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== パチンコ分析エンドポイント ==========

@router.get("/pachinko/expected-value")
async def get_pachinko_expected_value(
    store_id: int,
    db: Session = Depends(get_db)
):
    """パチンコ期待値を取得

    Args:
        store_id: 店舗ID
        db: DB セッション

    Returns:
        期待値ランキング
    """
    try:
        logger.info(f"🎲 Getting pachinko expected value for store {store_id}")

        ev_list = expected_value.calculate_expected_value_by_machine(db, store_id, "P")
        overall_ev = expected_value.calculate_overall_expected_value(db, store_id, "P")

        return {
            "status": "success",
            "store_id": store_id,
            "machine_type": "パチンコ",
            "overall": overall_ev,
            "by_machine": ev_list[:20],
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pachinko/dashboard")
async def get_pachinko_dashboard(
    store_id: int,
    db: Session = Depends(get_db)
):
    """パチンコ分析ダッシュボード（統合）

    Args:
        store_id: 店舗ID
        db: DB セッション

    Returns:
        パチンコ統合分析結果
    """
    try:
        logger.info(f"📊 Getting pachinko dashboard for store {store_id}")

        data = pachinko.get_dashboard(db, store_id)

        return data

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 予測検証エンドポイント ==========

@router.get("/evaluation/verify")
async def verify_recent_predictions(
    store_id: int,
    days_back: int = 1,
    db: Session = Depends(get_db)
):
    """過去予測を検証

    Args:
        store_id: 店舗ID
        days_back: 何日前の予測を検証するか（1=昨日）
        db: DB セッション

    Returns:
        検証結果
    """
    try:
        logger.info(f"🔍 Verifying predictions for store {store_id}")

        from datetime import timedelta
        verification_date = date.today() - timedelta(days=days_back)

        result = evaluation.verify_predictions(db, store_id, verification_date)

        return result

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evaluation/stats")
async def get_evaluation_stats(
    store_id: int,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """評価統計を取得

    Args:
        store_id: 店舗ID
        days: 統計対象日数
        db: DB セッション

    Returns:
        評価統計
    """
    try:
        logger.info(f"📈 Getting evaluation stats for store {store_id}")

        stats = evaluation.get_model_evaluation_stats(db, store_id, "S", days)

        return stats

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== レガシーエンドポイント（互換性維持） ==========

@router.get("/expected-value")
async def get_expected_value(
    store_id: int,
    machine_type: str = "S",
    db: Session = Depends(get_db)
):
    """機種別期待値を取得（レガシー）

    Args:
        store_id: 店舗 ID
        machine_type: 機種タイプ（S=スロット, P=パチンコ）
        db: DB セッション

    Returns:
        期待値データ
    """
    try:
        logger.info(f"📊 Calculating expected values for store {store_id}")

        machine_ev = expected_value.calculate_expected_value_by_machine(db, store_id, machine_type)
        overall_ev = expected_value.calculate_overall_expected_value(db, store_id, machine_type)

        return {
            "status": "success",
            "store_id": store_id,
            "machine_type": "スロット" if machine_type == "S" else "パチンコ",
            "overall": overall_ev,
            "by_machine": machine_ev[:20]
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns")
async def get_patterns(
    store_id: int,
    machine_type: str = "S",
    db: Session = Depends(get_db)
):
    """出玉パターン分析を取得（レガシー）

    Args:
        store_id: 店舗 ID
        machine_type: 機種タイプ
        db: DB セッション

    Returns:
        パターン分析結果
    """
    try:
        logger.info(f"🎯 Analyzing patterns for store {store_id}")

        pat = patterns.analyze_machine_patterns(db, store_id, machine_type)

        return {
            "status": "success",
            "store_id": store_id,
            "machine_type": "スロット" if machine_type == "S" else "パチンコ",
            "patterns": pat.get("patterns", []) if pat.get("status") == "success" else []
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def get_dashboard(
    store_id: int,
    machine_type: str = "S",
    db: Session = Depends(get_db)
):
    """ダッシュボード用の統合データを取得（レガシー）

    Args:
        store_id: 店舗 ID
        machine_type: 機種タイプ
        db: DB セッション

    Returns:
        統合分析結果
    """
    try:
        logger.info(f"📈 Getting dashboard data for store {store_id}")

        # スロットの場合は新しいエンドポイントを使用
        if machine_type == "S":
            return await get_slots_dashboard(store_id, db)

        # パチンコの場合は既存ロジック
        ev = expected_value.calculate_expected_value_by_machine(db, store_id, machine_type)
        overall_ev = expected_value.calculate_overall_expected_value(db, store_id, machine_type)
        pat = patterns.analyze_machine_patterns(db, store_id, machine_type)

        return {
            "status": "success",
            "store_id": store_id,
            "machine_type": "パチンコ",
            "overall_expected_value": overall_ev,
            "top_machines": ev[:10],
            "performance_prediction": [],
            "patterns": pat.get("patterns", []) if pat.get("status") == "success" else []
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
