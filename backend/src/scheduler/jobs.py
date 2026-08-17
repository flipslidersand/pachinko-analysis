"""定期実行ジョブ"""
import logging
import hashlib
from datetime import time, date, timedelta
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

        # スケジュール実行では「直前に確定した営業日 = 前日」を対象にする。
        # aggregate は target_date < CURRENT_DATE を集計するため、前日を書けば
        # 同夜のうちに aggregate → predict まで一気通貫で流れる（#11 問題B の方針）。
        target_date = date.today() - timedelta(days=1)

        saved_count = 0
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 8:  # スロット：9列、パチンコ：8列
                continue

            try:
                # routers/scraper.py の save-data と同じ解析ロジック
                unit_number = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                machine_name = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                if not machine_name or not unit_number:
                    continue

                try:
                    feature_count1 = int(cells[4].get_text(strip=True)) if len(cells) > 4 else 0
                except (ValueError, IndexError):
                    feature_count1 = 0
                try:
                    feature_count2 = int(cells[5].get_text(strip=True)) if len(cells) > 5 else 0
                except (ValueError, IndexError):
                    feature_count2 = 0
                try:
                    start_count = int(cells[-1].get_text(strip=True)) if len(cells) > 0 else 0
                except (ValueError, IndexError):
                    start_count = 0

                machine_id = crud.get_or_create_machine(db, machine_name, machine_type)
                feature_score = (feature_count1 + feature_count2) * 10
                diff_value = feature_score - start_count

                # 生データ蓄積（aggregate が読む正の入力）
                source_hash = hashlib.md5(
                    f"{store_id}_{unit_number}_{target_date}".encode()
                ).hexdigest()
                crud.insert_raw_machine_data(
                    db,
                    store_id=store_id,
                    machine_type=machine_type,
                    unit_number=unit_number,
                    machine_name=machine_name,
                    target_date=target_date,
                    total_games=start_count,
                    bonus_count=(feature_count1 + feature_count2),
                    payout=feature_score,
                    diff=diff_value,
                    source_url=url,
                    source_hash=source_hash,
                )

                # 互換性維持
                crud.insert_daily_result(
                    db,
                    store_id=store_id,
                    machine_id=machine_id,
                    result_date=target_date,
                    games_count=start_count,
                    medals_in=feature_score,
                    medals_out=0,
                    diff=diff_value,
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
                # 予測対象日は「集計済みの最新日（＝直近スクレイプ済み日）」。
                # 当日(date.today())は aggregate が除外しており stats 行が無いため、
                # 固定で today を渡すと常に "No features" で 0 件になる（#11 問題B）。
                latest_date = db.execute(
                    text(
                        "SELECT MAX(target_date) FROM daily_machine_stats WHERE store_id = :sid"
                    ),
                    {"sid": store_id},
                ).scalar()

                if latest_date is None:
                    logger.warning(f"⚠️ No aggregated stats for {store_name}, skip")
                    continue

                # スロット当たり確率予測（内部でinsert_slot_predictionを呼ぶ）
                predictions = slots.predict_hit_probability(
                    db, store_id, prediction_date=latest_date
                )
                total_saved += len(predictions)
                logger.info(
                    f"✅ {store_name}: {len(predictions)} predictions saved "
                    f"(prediction_date={latest_date})"
                )

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

    # 毎日 03:00 に全店舗の予測を実行して保存
    scheduler.add_job(
        run_daily_predictions_job,
        CronTrigger(hour=3, minute=0),
        name="Run Daily Predictions at 3AM",
        replace_existing=True
    )

    logger.info("✅ Scheduler initialized with daily jobs (optimized for NUCBOX G3plus)")
    return scheduler
