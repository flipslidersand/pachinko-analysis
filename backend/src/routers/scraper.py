"""スクレイパー API ルーター"""
import logging
import os
import hashlib
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException, Depends
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
import time

from src.database.connection import get_db
from src.database import crud

logger = logging.getLogger(__name__)
router = APIRouter()

# Selenium リモート接続設定
SELENIUM_HOST = os.getenv("SELENIUM_HOST", "localhost")
SELENIUM_PORT = int(os.getenv("SELENIUM_PORT", 4444))
SELENIUM_URL = f"http://{SELENIUM_HOST}:{SELENIUM_PORT}"


@router.post("/scrape/all-machines")
async def scrape_all_machines(hall_id: str, machine_type: str = "S"):
    """すべての機種の営業成績をスクレイプ

    Args:
        hall_id: ホール ID（例：101101）
        machine_type: 機種タイプ（S=スロット, P=パチンコ）

    Returns:
        スクレイプ結果
    """
    driver = None
    try:
        # 机種名のマッピング
        type_name = "スロット" if machine_type == "S" else "パチンコ"

        logger.info(f"📱 Scraping {type_name} for hall {hall_id}")

        # Selenium リモート接続
        options = Options()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        driver = webdriver.Remote(
            command_executor=f"{SELENIUM_URL}/wd/hub",
            options=options
        )

        # all_list ページにアクセス
        url = f"https://daidata.goraggio.com/p-world-daidataonline/{hall_id}/all_list?ps={machine_type}"
        logger.info(f"🔗 Loading: {url}")
        driver.get(url)
        time.sleep(4)

        # HTML解析
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # テーブルを抽出
        tables = soup.find_all("table")
        if not tables:
            raise ValueError("No tables found in page")

        # ヘッダーを取得
        table = tables[0]
        rows = table.find_all("tr")

        # ヘッダー行（最初の行）
        header_cells = rows[0].find_all(["th", "td"])
        headers = [cell.get_text(strip=True) for cell in header_cells]

        # データ行
        machines = []
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) > 0:
                # セルデータを辞書に変換
                machine_data = {}
                for i, header in enumerate(headers):
                    if i < len(cells):
                        machine_data[header] = cells[i].get_text(strip=True)
                machines.append(machine_data)

        logger.info(f"✅ Scraped {len(machines)} machines")

        return {
            "status": "success",
            "hall_id": hall_id,
            "machine_type": type_name,
            "data_count": len(machines),
            "headers": headers,
            "machines": machines[:10],  # 最初の10台を返す
            "total": len(machines)
        }

    except Exception as e:
        logger.error(f"❌ Scraping error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if driver:
            driver.quit()
            logger.info("✅ WebDriver closed")


@router.post("/save-data-historical")
async def save_historical_data(
    hall_id: str,
    machine_type: str = "S",
    days_back: int = 7,
    db: Session = Depends(get_db)
):
    """過去データを取得して DB に保存

    Args:
        hall_id: ホール ID
        machine_type: 機種タイプ（S=スロット, P=パチンコ）
        days_back: 何日分遡るか（0=今日, 1=昨日, ..., 7=一週間前）
        db: DB セッション

    Returns:
        保存結果
    """
    driver = None
    try:
        type_name = "スロット" if machine_type == "S" else "パチンコ"
        logger.info(f"💾 Saving historical {type_name} data for hall {hall_id} ({days_back} days back)")

        # 店舗情報を取得
        store = crud.get_store_by_hall_id(db, hall_id)
        if not store:
            raise ValueError(f"Store not found: {hall_id}")

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
        time.sleep(4)

        # hist_num を変更してフォーム送信
        hist_input = driver.find_element(By.NAME, "hist_num")
        driver.execute_script(f"arguments[0].value = '{days_back}';", hist_input)

        form = driver.find_element(By.TAG_NAME, "form")
        driver.execute_script("arguments[0].submit();", form)
        time.sleep(4)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            raise ValueError("No tables found")

        table = tables[0]
        rows = table.find_all("tr")

        # データを DB に保存
        saved_count = 0
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 8:  # スロット：9列、パチンコ：8列
                continue

            try:
                # 基本データを抽出
                unit_number = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                machine_name = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                if not machine_name or not unit_number:
                    continue

                # 数値データを抽出
                try:
                    feature_count1 = int(cells[4].get_text(strip=True)) if len(cells) > 4 else 0
                except (ValueError, IndexError):
                    feature_count1 = 0

                try:
                    feature_count2 = int(cells[5].get_text(strip=True)) if len(cells) > 5 else 0
                except (ValueError, IndexError):
                    feature_count2 = 0

                # Start count は最後から2番目のセル
                try:
                    start_count = int(cells[-1].get_text(strip=True)) if len(cells) > 0 else 0
                except (ValueError, IndexError):
                    start_count = 0

                machine_id = crud.get_or_create_machine(db, machine_name, machine_type)

                # 特徴数の合計をスコアとして利用
                feature_score = (feature_count1 + feature_count2) * 10
                diff_value = feature_score - start_count

                # 過去日付を計算
                target_date = date.today() - timedelta(days=days_back)

                # 【新規】raw_machine_data に生データを保存
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
                    source_hash=source_hash
                )

                # 【既存】daily_results に保存（互換性維持）
                crud.insert_daily_result(
                    db,
                    store_id=store_id,
                    machine_id=machine_id,
                    result_date=target_date,
                    games_count=start_count,
                    medals_in=feature_score,
                    medals_out=0,
                    diff=diff_value
                )
                saved_count += 1

            except Exception as e:
                logger.warning(f"⚠️ Failed to save row: {e}")
                continue

        crud.insert_scrape_log(db, store_id, "success")

        logger.info(f"✅ Saved {saved_count} machines to DB")

        return {
            "status": "success",
            "store_id": store_id,
            "store_name": store_name,
            "machine_type": type_name,
            "days_back": days_back,
            "saved_count": saved_count
        }

    except Exception as e:
        logger.error(f"❌ Error saving data: {e}")
        if "store_id" in locals():
            crud.insert_scrape_log(db, store_id, "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if driver:
            driver.quit()


@router.post("/save-data")
async def save_scraped_data(
    hall_id: str,
    machine_type: str = "S",
    db: Session = Depends(get_db)
):
    """スクレイプしたデータを DB に保存

    Args:
        hall_id: ホール ID
        machine_type: 機種タイプ（S=スロット, P=パチンコ）
        db: DB セッション

    Returns:
        保存結果
    """
    driver = None
    try:
        type_name = "スロット" if machine_type == "S" else "パチンコ"
        logger.info(f"💾 Saving {type_name} data for hall {hall_id}")

        # 店舗情報を取得
        store = crud.get_store_by_hall_id(db, hall_id)
        if not store:
            raise ValueError(f"Store not found: {hall_id}")

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
        time.sleep(4)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            raise ValueError("No tables found")

        table = tables[0]
        rows = table.find_all("tr")

        # データを DB に保存
        saved_count = 0
        for row in rows[1:]:  # ヘッダー行をスキップ
            cells = row.find_all("td")
            if len(cells) < 8:  # スロット：9列、パチンコ：8列
                continue

            try:
                # 基本データを抽出
                unit_number = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                machine_name = cells[3].get_text(strip=True) if len(cells) > 3 else ""

                if not machine_name or not unit_number:
                    continue

                # 数値データを抽出
                try:
                    feature_count1 = int(cells[4].get_text(strip=True)) if len(cells) > 4 else 0
                except (ValueError, IndexError):
                    feature_count1 = 0

                try:
                    feature_count2 = int(cells[5].get_text(strip=True)) if len(cells) > 5 else 0
                except (ValueError, IndexError):
                    feature_count2 = 0

                # Start count は最後から2番目のセル
                try:
                    start_count = int(cells[-1].get_text(strip=True)) if len(cells) > 0 else 0
                except (ValueError, IndexError):
                    start_count = 0

                # 機種を取得または作成
                machine_id = crud.get_or_create_machine(db, machine_name, machine_type)

                # 特徴数の合計をスコアとして利用
                feature_score = (feature_count1 + feature_count2) * 10
                diff_value = feature_score - start_count

                # 【新規】raw_machine_data に生データを保存
                source_hash = hashlib.md5(
                    f"{store_id}_{unit_number}_{date.today()}".encode()
                ).hexdigest()

                crud.insert_raw_machine_data(
                    db,
                    store_id=store_id,
                    machine_type=machine_type,
                    unit_number=unit_number,
                    machine_name=machine_name,
                    target_date=date.today(),
                    total_games=start_count,
                    bonus_count=(feature_count1 + feature_count2),
                    payout=feature_score,
                    diff=diff_value,
                    source_url=url,
                    source_hash=source_hash
                )

                # 【既存】daily_results に保存（互換性維持）
                crud.insert_daily_result(
                    db,
                    store_id=store_id,
                    machine_id=machine_id,
                    result_date=date.today(),
                    games_count=start_count,
                    medals_in=feature_score,
                    medals_out=0,
                    diff=diff_value
                )
                saved_count += 1

            except Exception as e:
                logger.warning(f"⚠️ Failed to save row: {e}")
                continue

        # スクレイピングログを記録
        crud.insert_scrape_log(db, store_id, "success")

        logger.info(f"✅ Saved {saved_count} machines to DB")

        return {
            "status": "success",
            "store_id": store_id,
            "store_name": store_name,
            "machine_type": type_name,
            "saved_count": saved_count
        }

    except Exception as e:
        logger.error(f"❌ Error saving data: {e}")
        if "store_id" in locals():
            crud.insert_scrape_log(db, store_id, "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if driver:
            driver.quit()


@router.get("/test")
async def test_scraper():
    """スクレイパーのテスト"""
    return {
        "status": "ready",
        "selenium_url": SELENIUM_URL,
        "endpoints": [
            "POST /api/scraper/scrape/all-machines?hall_id=101101&machine_type=S",
            "POST /api/scraper/save-data?hall_id=101101&machine_type=S"
        ]
    }
