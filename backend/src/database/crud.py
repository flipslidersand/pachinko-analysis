"""CRUD オペレーション"""
import logging
from datetime import date
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def insert_store(db: Session, name: str, hall_id: str, url: str = None, region: str = None):
    """店舗を DB に挿入"""
    sql = """
    INSERT INTO stores (name, hall_id, url, region, is_active)
    VALUES (:name, :hall_id, :url, :region, TRUE)
    ON CONFLICT DO NOTHING
    """
    db.execute(text(sql), {
        "name": name,
        "hall_id": hall_id,
        "url": url,
        "region": region
    })
    db.commit()
    logger.info(f"✅ Store inserted: {name}")


def insert_machine(db: Session, name: str, type: str, maker: str = None):
    """機種を DB に挿入"""
    sql = """
    INSERT INTO machines (name, type, maker)
    VALUES (:name, :type, :maker)
    ON CONFLICT DO NOTHING
    """
    db.execute(text(sql), {
        "name": name,
        "type": type,
        "maker": maker
    })
    db.commit()
    logger.info(f"✅ Machine inserted: {name}")


def insert_daily_result(db: Session, store_id: int, machine_id: int,
                       result_date: date, games_count: int = None,
                       medals_in: int = None, medals_out: int = None, diff: int = None):
    """日次営業成績を DB に挿入"""
    sql = """
    INSERT INTO daily_results (store_id, machine_id, date, games_count, medals_in, medals_out, diff)
    VALUES (:store_id, :machine_id, :date, :games_count, :medals_in, :medals_out, :diff)
    ON CONFLICT (store_id, machine_id, date) DO UPDATE SET
        games_count = :games_count,
        medals_in = :medals_in,
        medals_out = :medals_out,
        diff = :diff,
        collected_at = NOW()
    """
    db.execute(text(sql), {
        "store_id": store_id,
        "machine_id": machine_id,
        "date": result_date,
        "games_count": games_count,
        "medals_in": medals_in,
        "medals_out": medals_out,
        "diff": diff
    })
    db.commit()


def get_store_by_hall_id(db: Session, hall_id: str):
    """ホール ID から店舗を取得"""
    sql = "SELECT id, name FROM stores WHERE hall_id = :hall_id"
    result = db.execute(text(sql), {"hall_id": hall_id}).fetchone()
    return result


def get_or_create_machine(db: Session, name: str, machine_type: str):
    """機種を取得または作成"""
    sql = "SELECT id FROM machines WHERE name = :name AND type = :type"
    result = db.execute(text(sql), {"name": name, "type": machine_type}).fetchone()

    if result:
        return result[0]

    # 存在しない場合は作成
    insert_sql = """
    INSERT INTO machines (name, type)
    VALUES (:name, :type)
    RETURNING id
    """
    result = db.execute(text(insert_sql), {"name": name, "type": machine_type})
    db.commit()
    return result.scalar()


def insert_scrape_log(db: Session, store_id: int, status: str, error_message: str = None):
    """スクレイピングログを記録"""
    sql = """
    INSERT INTO scrape_logs (store_id, status, error_message)
    VALUES (:store_id, :status, :error_message)
    """
    db.execute(text(sql), {
        "store_id": store_id,
        "status": status,
        "error_message": error_message
    })
    db.commit()
    logger.info(f"✅ Scrape log recorded: {status}")


# Phase 1 新規テーブル用CRUD

def insert_raw_machine_data(
    db: Session,
    store_id: int,
    machine_type: str,
    unit_number: str,
    machine_name: str,
    target_date: date,
    total_games: int = None,
    bonus_count: int = None,
    payout: int = None,
    diff: int = None,
    source_url: str = None,
    source_hash: str = None
) -> bool:
    """スクレイピング生データを保存"""
    try:
        sql = """
        INSERT INTO raw_machine_data (
            store_id, machine_type, unit_number, machine_name, target_date,
            total_games, bonus_count, payout, diff, source_url, source_hash
        ) VALUES (
            :store_id, :machine_type, :unit_number, :machine_name, :target_date,
            :total_games, :bonus_count, :payout, :diff, :source_url, :source_hash
        ) ON CONFLICT DO NOTHING
        """
        db.execute(text(sql), {
            "store_id": store_id,
            "machine_type": machine_type,
            "unit_number": unit_number,
            "machine_name": machine_name,
            "target_date": target_date,
            "total_games": total_games,
            "bonus_count": bonus_count,
            "payout": payout,
            "diff": diff,
            "source_url": source_url,
            "source_hash": source_hash,
        })
        db.commit()
        return True
    except Exception as e:
        logger.error(f"❌ Error inserting raw machine data: {e}")
        db.rollback()
        return False


def insert_daily_machine_stats(
    db: Session,
    store_id: int,
    machine_id: int,
    machine_type: str,
    target_date: date,
    games_count: int = None,
    diff: int = None,
    stddev: float = None,
    min_diff: int = None,
    max_diff: int = None,
    sample_count: int = None
) -> bool:
    """日次集計済みデータを保存"""
    try:
        sql = """
        INSERT INTO daily_machine_stats (
            store_id, machine_id, machine_type, target_date,
            games_count, diff, stddev, min_diff, max_diff, sample_count
        ) VALUES (
            :store_id, :machine_id, :machine_type, :target_date,
            :games_count, :diff, :stddev, :min_diff, :max_diff, :sample_count
        ) ON CONFLICT (store_id, machine_id, target_date) DO UPDATE SET
            games_count = :games_count,
            diff = :diff,
            stddev = :stddev,
            min_diff = :min_diff,
            max_diff = :max_diff,
            sample_count = :sample_count
        """
        db.execute(text(sql), {
            "store_id": store_id,
            "machine_id": machine_id,
            "machine_type": machine_type,
            "target_date": target_date,
            "games_count": games_count,
            "diff": diff,
            "stddev": stddev,
            "min_diff": min_diff,
            "max_diff": max_diff,
            "sample_count": sample_count,
        })
        db.commit()
        return True
    except Exception as e:
        logger.error(f"❌ Error inserting daily machine stats: {e}")
        db.rollback()
        return False


def insert_slot_prediction(
    db: Session,
    store_id: int,
    machine_id: int,
    prediction_date: date,
    model_version: str,
    hit_probability: float,
    expected_value: float = None,
    confidence_score: float = None
) -> bool:
    """スロット予測結果を保存"""
    try:
        sql = """
        INSERT INTO slot_predictions (
            store_id, machine_id, prediction_date, model_version,
            hit_probability, expected_value, confidence_score
        ) VALUES (
            :store_id, :machine_id, :prediction_date, :model_version,
            :hit_probability, :expected_value, :confidence_score
        ) ON CONFLICT (store_id, machine_id, prediction_date, model_version) DO UPDATE SET
            hit_probability = :hit_probability,
            expected_value = :expected_value,
            confidence_score = :confidence_score
        """
        db.execute(text(sql), {
            "store_id": store_id,
            "machine_id": machine_id,
            "prediction_date": prediction_date,
            "model_version": model_version,
            "hit_probability": hit_probability,
            "expected_value": expected_value,
            "confidence_score": confidence_score,
        })
        db.commit()
        return True
    except Exception as e:
        logger.error(f"❌ Error inserting slot prediction: {e}")
        db.rollback()
        return False


def insert_prediction_result(
    db: Session,
    prediction_id: int,
    actual_diff: int,
    actual_label: int,
    was_correct: bool
) -> bool:
    """予測検証結果を保存"""
    try:
        sql = """
        INSERT INTO prediction_results (
            prediction_id, actual_diff, actual_label, was_correct, verified_at
        ) VALUES (
            :prediction_id, :actual_diff, :actual_label, :was_correct, NOW()
        )
        """
        db.execute(text(sql), {
            "prediction_id": prediction_id,
            "actual_diff": actual_diff,
            "actual_label": actual_label,
            "was_correct": was_correct,
        })
        db.commit()
        return True
    except Exception as e:
        logger.error(f"❌ Error inserting prediction result: {e}")
        db.rollback()
        return False
