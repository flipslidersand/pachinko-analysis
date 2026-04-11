"""期待値計算モデル（統計ベース・重み付き + 条件付き対応）"""
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
import numpy as np
from datetime import date, timedelta
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# 定数
MIN_SAMPLES_FOR_CONDITIONAL_EV = 3
RECENT_WEIGHT = 1.0
MEDIUM_WEIGHT = 0.7
HISTORICAL_WEIGHT = 0.4


def _calculate_conditional_expected_value(
    db: Session,
    store_id: int,
    machine_id: int,
    machine_name: str,
    machine_type: str,
    target_date: date = None
) -> Dict:
    """
    条件付き期待値を計算（曜日別、機種別などでfallback）

    優先順位：
    1. 曜日×機種 の期待値
    2. 曜日の期待値
    3. 機種の期待値
    4. 全体の期待値

    Returns:
        {
            "expected_value": float,
            "source": str,  # "weekday_machine", "weekday", "machine", "overall"
            "sample_count": int,
            "confidence": float
        }
    """
    if target_date is None:
        target_date = date.today()

    # 今日の曜日
    day_of_week = target_date.weekday()
    lookback = target_date - timedelta(days=90)

    # 1. 曜日×機種の期待値
    sql_weekday_machine = """
    SELECT
        AVG(CAST(dr.diff AS FLOAT)) as avg_diff,
        COUNT(*) as sample_count
    FROM daily_results dr
    WHERE dr.store_id = :store_id
        AND dr.machine_id = :machine_id
        AND EXTRACT(DOW FROM dr.date) = :day_of_week
        AND dr.date < :target_date
        AND dr.date >= :lookback_start
    """

    result = db.execute(text(sql_weekday_machine), {
        "store_id": store_id,
        "machine_id": machine_id,
        "day_of_week": day_of_week,
        "target_date": target_date,
        "lookback_start": lookback,
    }).fetchone()

    if result and result[1] and result[1] >= MIN_SAMPLES_FOR_CONDITIONAL_EV:
        return {
            "expected_value": float(result[0]) if result[0] else 0,
            "source": "weekday_machine",
            "sample_count": int(result[1]),
            "confidence": min(100, int(result[1]) * 10),
        }

    # 2. 曜日の期待値
    sql_weekday = """
    SELECT
        AVG(CAST(dr.diff AS FLOAT)) as avg_diff,
        COUNT(*) as sample_count
    FROM daily_results dr
    JOIN machines m ON dr.machine_id = m.id
    WHERE dr.store_id = :store_id
        AND EXTRACT(DOW FROM dr.date) = :day_of_week
        AND m.type = :machine_type
        AND dr.date < :target_date
        AND dr.date >= :lookback_start
    """

    result = db.execute(text(sql_weekday), {
        "store_id": store_id,
        "day_of_week": day_of_week,
        "machine_type": machine_type,
        "target_date": target_date,
        "lookback_start": lookback,
    }).fetchone()

    if result and result[1] and result[1] >= MIN_SAMPLES_FOR_CONDITIONAL_EV:
        return {
            "expected_value": float(result[0]) if result[0] else 0,
            "source": "weekday",
            "sample_count": int(result[1]),
            "confidence": min(100, int(result[1]) * 5),
        }

    # 3. 機種の期待値
    sql_machine = """
    SELECT
        AVG(CAST(dr.diff AS FLOAT)) as avg_diff,
        COUNT(*) as sample_count
    FROM daily_results dr
    WHERE dr.store_id = :store_id
        AND dr.machine_id = :machine_id
        AND dr.date < :target_date
        AND dr.date >= :lookback_start
    """

    result = db.execute(text(sql_machine), {
        "store_id": store_id,
        "machine_id": machine_id,
        "target_date": target_date,
        "lookback_start": lookback,
    }).fetchone()

    if result and result[1]:
        return {
            "expected_value": float(result[0]) if result[0] else 0,
            "source": "machine",
            "sample_count": int(result[1]),
            "confidence": min(100, int(result[1]) * 3),
        }

    # 4. 全体の期待値（fallback）
    sql_overall = """
    SELECT
        AVG(CAST(dr.diff AS FLOAT)) as avg_diff,
        COUNT(*) as sample_count
    FROM daily_results dr
    WHERE dr.store_id = :store_id
        AND dr.date < :target_date
        AND dr.date >= :lookback_start
    """

    result = db.execute(text(sql_overall), {
        "store_id": store_id,
        "target_date": target_date,
        "lookback_start": lookback,
    }).fetchone()

    return {
        "expected_value": float(result[0]) if result and result[0] else 0,
        "source": "overall",
        "sample_count": int(result[1]) if result and result[1] else 0,
        "confidence": 10,
    }


def calculate_expected_value_by_machine(
    db: Session,
    store_id: int,
    machine_type: str = "S",
    target_date: date = None
) -> List[Dict]:
    """
    機種別の条件付き期待値を計算

    Args:
        db: DB セッション
        store_id: 店舗ID
        machine_type: 機種タイプ
        target_date: 計算対象日（None=本日）

    Returns:
        機種別期待値リスト（降順）
    """
    if target_date is None:
        target_date = date.today()

    try:
        # 対象店舗の全機種を取得
        sql = """
        SELECT DISTINCT m.id, m.name
        FROM machines m
        JOIN daily_results dr ON m.id = dr.machine_id
        WHERE dr.store_id = :store_id
            AND m.type = :machine_type
            AND dr.date < :target_date
        ORDER BY m.id
        """

        result = db.execute(text(sql), {
            "store_id": store_id,
            "machine_type": machine_type,
            "target_date": target_date,
        }).fetchall()

        expected_values = []

        for machine_id, machine_name in result:
            cond_ev = _calculate_conditional_expected_value(
                db, store_id, machine_id, machine_name, machine_type, target_date
            )

            expected_values.append({
                "machine_id": int(machine_id),
                "machine_name": machine_name,
                "expected_value": cond_ev["expected_value"],
                "sample_count": cond_ev["sample_count"],
                "source": cond_ev["source"],
                "confidence": cond_ev["confidence"],
                "stddev": 0,
                "play_count": cond_ev["sample_count"],
            })

        # 期待値降順でソート
        expected_values = sorted(
            expected_values,
            key=lambda x: x["expected_value"],
            reverse=True
        )

        logger.info(f"✅ Calculated conditional EV for {len(expected_values)} machines")
        return expected_values

    except Exception as e:
        logger.error(f"❌ Error calculating expected values: {e}")
        return []


def calculate_overall_expected_value(
    db: Session,
    store_id: int,
    machine_type: str = "S",
    target_date: date = None
) -> Dict:
    """
    店舗全体の期待値を計算

    Args:
        db: DB セッション
        store_id: 店舗ID
        machine_type: 機種タイプ
        target_date: 計算対象日

    Returns:
        期待値統計
    """
    if target_date is None:
        target_date = date.today()

    try:
        # 過去全期間のデータから期待値を計算
        sql = """
        SELECT
            CAST(dr.diff AS FLOAT) as diff,
            dr.date
        FROM daily_results dr
        JOIN machines m ON dr.machine_id = m.id
        WHERE dr.store_id = :store_id
            AND m.type = :machine_type
            AND dr.date < :target_date
        ORDER BY dr.date DESC
        """

        result = db.execute(text(sql), {
            "store_id": store_id,
            "machine_type": machine_type,
            "target_date": target_date,
        }).fetchall()

        if not result:
            return {
                "average_diff": 0,
                "stddev": 0,
                "min_diff": 0,
                "max_diff": 0,
                "total_plays": 0,
                "avg_per_machine": 0,
                "data_period_days": 0,
            }

        diffs = [r[0] for r in result if r[0] is not None]

        if not diffs:
            return {
                "average_diff": 0,
                "stddev": 0,
                "min_diff": 0,
                "max_diff": 0,
                "total_plays": 0,
                "avg_per_machine": 0,
                "data_period_days": 0,
            }

        avg_diff = float(np.mean(diffs))
        stddev = float(np.std(diffs)) if len(diffs) > 1 else 0.0
        min_diff = float(np.min(diffs))
        max_diff = float(np.max(diffs))
        total_plays = len(diffs)

        # データ期間を計算
        dates = [r[1] for r in result if r[1] is not None]
        data_period = (max(dates) - min(dates)).days if dates else 0

        return {
            "average_diff": avg_diff,
            "stddev": stddev,
            "min_diff": min_diff,
            "max_diff": max_diff,
            "total_plays": total_plays,
            "avg_per_machine": total_plays / max(1, total_plays),
            "data_period_days": data_period,
        }

    except Exception as e:
        logger.error(f"❌ Error calculating overall expected value: {e}")
        return {}
