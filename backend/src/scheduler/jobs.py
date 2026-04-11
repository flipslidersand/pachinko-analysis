"""定期実行ジョブ"""
import logging
from datetime import time, date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
import asyncio

from src.database.connection import SessionLocal
from src.database import crud
from src.analysis import slots

logger = logging.getLogger(__name__)

SELENIUM_HOST = os.getenv("SELENIUM_HOST", "localhost")
SELENIUM_PORT = int(os.getenv("SELENIUM_PORT", 4444))
SELENIUM_URL = f"http://{SELENIUM_HOST}:{SELENIUM_PORT}"


async def scrape_and_save_job(hall_id: str, machine_type: str = "S"):
    """スクレイプして DB に保存するジョブ"""
    driver = None
    db = SessionLocal()
    try:
        type_name = "スロット" if machine_type == "S" else "パチンコ"
        logger.info(f"🔄 Starting scheduled scrape: {type_name} for hall {hall_id}")

        # 店舗情報を取得
        store = crud.get_store_by_hall_id(db, hall_id)
        if not store:
            logger.error(f"❌ Store not found: {hall_id}")
            return

        store_id, store_name = store

        # Selenium でデータを取得
        options = Options()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        driver = webdriver.Remote(
            command_executor=f"{SELENIUM_URL}/wd/hub",
            options=options
        )

        url = f"https://daidata.goraggio.com/p-world-daidataonline/{hall_id}/all_list?ps={machine_type}"
        driver.get(url)
        await asyncio.sleep(4)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            raise ValueError("No tables found")

        table = tables[0]
        rows = table.find_all("tr")

        saved_count = 0
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            try:
                machine_name = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                if not machine_name:
                    continue

                machine_id = crud.get_or_create_machine(db, machine_name, machine_type)
                crud.insert_daily_result(
                    db,
                    store_id=store_id,
                    machine_id=machine_id,
                    result_date=__import__('datetime').date.today()
                )
                saved_count += 1

            except Exception as e:
                logger.debug(f"⚠️ Failed to save row: {e}")
                continue

        crud.insert_scrape_log(db, store_id, "success")
        logger.info(f"✅ Scheduled scrape completed: {saved_count} {type_name} machines saved")

    except Exception as e:
        logger.error(f"❌ Scheduled scrape failed: {e}")
        if "store_id" in locals():
            crud.insert_scrape_log(db, store_id, "error", str(e))

    finally:
        if driver:
            driver.quit()
        db.close()


async def aggregate_daily_stats_job():
    """raw_machine_data から daily_machine_stats へ日次集計するジョブ"""
    db = SessionLocal()
    try:
        logger.info("📊 Starting daily aggregation job")

        # 昨日のデータを集計（前日までを対象）
        target_date = date.today()

        sql = """
        INSERT INTO daily_machine_stats (
            store_id, machine_id, machine_type, target_date,
            games_count, diff, stddev, min_diff, max_diff, sample_count
        )
        SELECT
            rmd.store_id,
            m.id as machine_id,
            rmd.machine_type,
            rmd.target_date,
            ROUND(AVG(rmd.total_games))::INTEGER as games_count,
            ROUND(AVG(rmd.diff))::INTEGER as diff,
            ROUND(STDDEV(rmd.diff))::NUMERIC(10,2) as stddev,
            MIN(rmd.diff)::INTEGER as min_diff,
            MAX(rmd.diff)::INTEGER as max_diff,
            COUNT(*)::INTEGER as sample_count
        FROM raw_machine_data rmd
        LEFT JOIN machines m ON rmd.machine_name = m.name AND rmd.machine_type = m.type
        WHERE rmd.target_date < :target_date
            AND NOT EXISTS (
                SELECT 1 FROM daily_machine_stats dms
                WHERE dms.store_id = rmd.store_id
                    AND dms.machine_id = m.id
                    AND dms.target_date = rmd.target_date
            )
        GROUP BY rmd.store_id, m.id, rmd.machine_type, rmd.target_date
        """

        result = db.execute(text(sql), {"target_date": target_date})
        db.commit()

        logger.info(f"✅ Daily aggregation completed: {result.rowcount} rows inserted")

    except Exception as e:
        logger.error(f"❌ Daily aggregation failed: {e}")
        db.rollback()

    finally:
        db.close()


async def generate_ml_features_job():
    """daily_machine_stats から ml_features を生成するジョブ"""
    db = SessionLocal()
    try:
        logger.info("🔄 Starting ML features generation job")

        # 予測対象日（今日の次の日）より前のデータで特徴量を生成
        target_date = date.today()

        sql = """
        INSERT INTO ml_features (
            store_id, machine_id, machine_type, feature_date,
            prev_1d_diff, prev_2d_diff, prev_3d_diff,
            avg_3d_diff, avg_7d_diff, avg_30d_diff,
            stddev_3d, stddev_7d, stddev_30d,
            trend_up_days_7d, trend_down_days_7d, positive_ratio_7d,
            max_diff_30d, min_diff_30d, volatility_30d,
            total_games_1d, day_of_week, hit_label
        )
        WITH ranked_data AS (
            SELECT
                dms.store_id,
                dms.machine_id,
                dms.machine_type,
                dms.target_date,
                dms.diff,
                dms.games_count,
                ROW_NUMBER() OVER (
                    PARTITION BY dms.store_id, dms.machine_id
                    ORDER BY dms.target_date DESC
                ) as row_num
            FROM daily_machine_stats dms
            WHERE dms.target_date < :target_date
        )
        SELECT
            rd.store_id,
            rd.machine_id,
            rd.machine_type,
            rd.target_date,
            -- 前日、2日前、3日前の差枚
            MAX(CASE WHEN rn2.row_num = 1 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ) as prev_1d_diff,
            MAX(CASE WHEN rn2.row_num = 2 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ) as prev_2d_diff,
            MAX(CASE WHEN rn2.row_num = 3 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ) as prev_3d_diff,
            -- 移動平均
            ROUND(AVG(CASE WHEN rn2.row_num <= 3 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ))::NUMERIC(10,2) as avg_3d_diff,
            ROUND(AVG(CASE WHEN rn2.row_num <= 7 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ))::NUMERIC(10,2) as avg_7d_diff,
            ROUND(AVG(CASE WHEN rn2.row_num <= 30 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ))::NUMERIC(10,2) as avg_30d_diff,
            -- 標準偏差
            ROUND(STDDEV(CASE WHEN rn2.row_num <= 3 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ))::NUMERIC(10,2) as stddev_3d,
            ROUND(STDDEV(CASE WHEN rn2.row_num <= 7 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ))::NUMERIC(10,2) as stddev_7d,
            ROUND(STDDEV(CASE WHEN rn2.row_num <= 30 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ))::NUMERIC(10,2) as stddev_30d,
            -- トレンド（過去7日）
            COUNT(CASE WHEN rn2.row_num <= 7 AND rn2.diff > 0 THEN 1 END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            )::INTEGER as trend_up_days_7d,
            COUNT(CASE WHEN rn2.row_num <= 7 AND rn2.diff < 0 THEN 1 END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            )::INTEGER as trend_down_days_7d,
            ROUND(100.0 * COUNT(CASE WHEN rn2.row_num <= 7 AND rn2.diff > 0 THEN 1 END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ) / NULLIF(COUNT(rn2.diff) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            ), 0))::NUMERIC(5,2) as positive_ratio_7d,
            -- ボラティリティ（過去30日）
            MAX(CASE WHEN rn2.row_num <= 30 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            )::INTEGER as max_diff_30d,
            MIN(CASE WHEN rn2.row_num <= 30 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            )::INTEGER as min_diff_30d,
            ROUND(STDDEV(CASE WHEN rn2.row_num <= 30 THEN rn2.diff END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            ))::NUMERIC(10,2) as volatility_30d,
            -- ゲーム数
            MAX(CASE WHEN rn2.row_num = 1 THEN rn2.games_count END) OVER (
                PARTITION BY rd.store_id, rd.machine_id, rd.target_date
            )::INTEGER as total_games_1d,
            -- 曜日
            EXTRACT(DOW FROM rd.target_date)::INTEGER as day_of_week,
            -- ラベル
            CASE
                WHEN MAX(CASE WHEN rn2.row_num = 1 THEN rn2.diff END) OVER (
                    PARTITION BY rd.store_id, rd.machine_id, rd.target_date
                ) > 1000 THEN 1
                ELSE 0
            END::INTEGER as hit_label
        FROM ranked_data rd
        LEFT JOIN (
            SELECT
                dms.store_id,
                dms.machine_id,
                dms.target_date,
                dms.diff,
                dms.games_count,
                ROW_NUMBER() OVER (
                    PARTITION BY dms.store_id, dms.machine_id
                    ORDER BY dms.target_date DESC
                ) as row_num
            FROM daily_machine_stats dms
        ) rn2 ON rd.store_id = rn2.store_id
                AND rd.machine_id = rn2.machine_id
                AND rn2.row_num <= 30
        WHERE rd.row_num = 1
            AND NOT EXISTS (
                SELECT 1 FROM ml_features mlf
                WHERE mlf.store_id = rd.store_id
                    AND mlf.machine_id = rd.machine_id
                    AND mlf.feature_date = rd.target_date
            )
        GROUP BY rd.store_id, rd.machine_id, rd.machine_type, rd.target_date
        """

        result = db.execute(text(sql), {"target_date": target_date})
        db.commit()

        logger.info(f"✅ ML features generation completed: {result.rowcount} rows inserted")

    except Exception as e:
        logger.error(f"❌ ML features generation failed: {e}")
        db.rollback()

    finally:
        db.close()


async def run_daily_predictions_job():
    """全店舗のスロット当たり確率予測を実行してDBに保存するジョブ"""
    db = SessionLocal()
    try:
        logger.info("🔮 Starting daily predictions job")

        # 全アクティブ店舗を取得
        store_rows = db.execute(text(
            "SELECT id, name FROM stores WHERE is_active = TRUE"
        )).fetchall()

        total_saved = 0
        for store_row in store_rows:
            store_id = int(store_row[0])
            store_name = store_row[1]

            try:
                # スロット当たり確率予測（内部でinsert_slot_predictionを呼ぶ）
                predictions = slots.predict_hit_probability(db, store_id)
                total_saved += len(predictions)
                logger.info(f"✅ {store_name}: {len(predictions)} predictions saved")

            except Exception as e:
                logger.warning(f"⚠️ Failed to predict for {store_name}: {e}")
                continue

        logger.info(f"✅ Daily predictions completed: {total_saved} total saved")

    except Exception as e:
        logger.error(f"❌ Daily predictions job failed: {e}")

    finally:
        db.close()


def init_scheduler():
    """スケジューラーを初期化"""
    scheduler = AsyncIOScheduler()

    # 毎日 01:00 にスロット＋パチンコをまとめてスクレイプ（営業終了後）
    scheduler.add_job(
        scrape_and_save_job,
        CronTrigger(hour=1, minute=0),
        args=["101101", "S"],
        name="Scrape Slots Daily at 1AM",
        replace_existing=True
    )

    scheduler.add_job(
        scrape_and_save_job,
        CronTrigger(hour=1, minute=5),
        args=["101101", "P"],
        name="Scrape Pachinko Daily at 1:05AM",
        replace_existing=True
    )

    # 毎日 02:00 に daily_machine_stats を集計
    scheduler.add_job(
        aggregate_daily_stats_job,
        CronTrigger(hour=2, minute=0),
        name="Aggregate Daily Stats at 2AM",
        replace_existing=True
    )

    # 毎日 02:30 に ml_features を生成
    scheduler.add_job(
        generate_ml_features_job,
        CronTrigger(hour=2, minute=30),
        name="Generate ML Features at 2:30AM",
        replace_existing=True
    )

    # 毎日 03:00 に全店舗の予測を実行して保存
    scheduler.add_job(
        run_daily_predictions_job,
        CronTrigger(hour=3, minute=0),
        name="Run Daily Predictions at 3AM",
        replace_existing=True
    )

    logger.info("✅ Scheduler initialized with daily jobs (optimized for NUCBOX G3plus)")
    return scheduler
