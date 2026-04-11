"""パチンコ分析モジュール（統計ベース）"""
import logging
import math
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Optional

from src.analysis import expected_value

logger = logging.getLogger(__name__)

# 曜日名マッピング
DOW_NAMES = {
    0: "日曜日",
    1: "月曜日",
    2: "火曜日",
    3: "水曜日",
    4: "木曜日",
    5: "金曜日",
    6: "土曜日",
}


def get_weekday_trends(
    db: Session,
    store_id: int,
    lookback_days: int = 90,
    target_date: Optional[date] = None
) -> List[Dict]:
    """曜日ごとの平均差枚・勝率を集計

    Args:
        db: DB セッション
        store_id: 店舗ID
        lookback_days: 参照期間（日数）
        target_date: 参照基準日（未指定で今日）

    Returns:
        曜日ごとの統計リスト
        [{"day_of_week": 0, "day_name": "日曜日", "avg_diff": float, ...}, ...]
    """
    if target_date is None:
        target_date = date.today()

    try:
        from_date = target_date - timedelta(days=lookback_days)

        sql = """
        SELECT
            EXTRACT(DOW FROM dr.result_date)::INTEGER as day_of_week,
            COUNT(*) as sample_count,
            AVG(dr.diff)::NUMERIC(10,2) as avg_diff,
            STDDEV(dr.diff)::NUMERIC(10,2) as stddev,
            SUM(CASE WHEN dr.diff > 0 THEN 1 ELSE 0 END) * 100.0 /
                NULLIF(COUNT(*), 0)::NUMERIC(5,2) as win_rate
        FROM daily_results dr
        WHERE dr.store_id = :store_id
            AND dr.machine_type = 'P'
            AND dr.result_date >= :from_date
            AND dr.result_date <= :target_date
        GROUP BY EXTRACT(DOW FROM dr.result_date)
        ORDER BY EXTRACT(DOW FROM dr.result_date)
        """

        rows = db.execute(
            text(sql),
            {
                "store_id": store_id,
                "from_date": from_date,
                "target_date": target_date,
            }
        ).fetchall()

        result = []
        for row in rows:
            dow = int(row[0])
            result.append({
                "day_of_week": dow,
                "day_name": DOW_NAMES.get(dow, ""),
                "avg_diff": float(row[2]) if row[2] is not None else 0.0,
                "stddev": float(row[3]) if row[3] is not None else 0.0,
                "win_rate": float(row[4]) if row[4] is not None else 0.0,
                "sample_count": int(row[1]),
            })

        logger.info(f"📊 Weekday trends calculated: {len(result)} days")
        return result

    except Exception as e:
        logger.error(f"❌ Error calculating weekday trends: {e}")
        return []


def get_machine_ranking(
    db: Session,
    store_id: int,
    top_n: int = 20,
    lookback_days: int = 90,
    target_date: Optional[date] = None
) -> List[Dict]:
    """機種別の期待値と95%信頼区間を計算

    Args:
        db: DB セッション
        store_id: 店舗ID
        top_n: 返却台数
        lookback_days: 参照期間
        target_date: 参照基準日

    Returns:
        期待値でソートされたランキング
        [{"machine_id": int, "machine_name": str, "expected_value": float,
          "ci_lower": float, "ci_upper": float, "win_rate": float, ...}, ...]
    """
    if target_date is None:
        target_date = date.today()

    try:
        from_date = target_date - timedelta(days=lookback_days)

        sql = """
        SELECT
            m.id as machine_id,
            m.name as machine_name,
            COUNT(*) as sample_count,
            AVG(dr.diff)::NUMERIC(10,2) as avg_diff,
            STDDEV(dr.diff)::NUMERIC(10,2) as stddev,
            SUM(CASE WHEN dr.diff > 0 THEN 1 ELSE 0 END) * 100.0 /
                NULLIF(COUNT(*), 0)::NUMERIC(5,2) as win_rate
        FROM daily_results dr
        LEFT JOIN machines m ON dr.machine_id = m.id
        WHERE dr.store_id = :store_id
            AND dr.machine_type = 'P'
            AND dr.result_date >= :from_date
            AND dr.result_date <= :target_date
        GROUP BY m.id, m.name
        ORDER BY avg_diff DESC
        LIMIT :top_n
        """

        rows = db.execute(
            text(sql),
            {
                "store_id": store_id,
                "from_date": from_date,
                "target_date": target_date,
                "top_n": top_n,
            }
        ).fetchall()

        result = []
        for row in rows:
            machine_id = int(row[0])
            machine_name = row[1] or "不明"
            sample_count = int(row[2])
            avg_diff = float(row[3]) if row[3] is not None else 0.0
            stddev = float(row[4]) if row[4] is not None else 0.0
            win_rate = float(row[5]) if row[5] is not None else 0.0

            # 95%信頼区間: avg ± 1.96 * stddev / sqrt(n)
            if sample_count > 0 and stddev > 0:
                margin_of_error = 1.96 * stddev / math.sqrt(sample_count)
            else:
                margin_of_error = 0.0

            ci_lower = avg_diff - margin_of_error
            ci_upper = avg_diff + margin_of_error

            result.append({
                "machine_id": machine_id,
                "machine_name": machine_name,
                "expected_value": avg_diff,
                "ci_lower": round(ci_lower, 2),
                "ci_upper": round(ci_upper, 2),
                "win_rate": win_rate,
                "sample_count": sample_count,
                "stddev": stddev,
            })

        logger.info(f"🎯 Machine ranking calculated: {len(result)} machines")
        return result

    except Exception as e:
        logger.error(f"❌ Error calculating machine ranking: {e}")
        return []


def get_dashboard(
    db: Session,
    store_id: int,
    target_date: Optional[date] = None
) -> Dict:
    """パチンコ分析ダッシュボード用統合データ

    Args:
        db: DB セッション
        store_id: 店舗ID
        target_date: 参照基準日

    Returns:
        ダッシュボード用JSON
    """
    try:
        if target_date is None:
            target_date = date.today()

        return {
            "status": "success",
            "store_id": store_id,
            "machine_type": "パチンコ",
            "overall_expected_value": expected_value.calculate_overall_expected_value(
                db, store_id, "P", target_date
            ),
            "machine_ranking": get_machine_ranking(db, store_id, top_n=20),
            "weekday_trends": get_weekday_trends(db, store_id),
        }

    except Exception as e:
        logger.error(f"❌ Error getting pachinko dashboard: {e}")
        return {
            "status": "error",
            "store_id": store_id,
            "message": str(e),
            "machine_ranking": [],
            "weekday_trends": [],
        }
