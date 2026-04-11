"""P-WORLD スクレイパー（Selenium + iframe対応）"""
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class PWorldScraper(BaseScraper):
    """P-WORLD からパチスロ営業データを取得"""

    def scrape_hall_data(self, url):
        """ホール出玉データを取得

        Args:
            url (str): P-WORLD のホール URL

        Returns:
            dict: スクレイプしたデータ
        """
        try:
            # ページ読み込み
            self.fetch_page(url)
            time.sleep(3)  # JavaScript 実行待ち

            # iframe ソース取得（iframe の src を取得してダイレクトアクセス）
            try:
                iframe = self.driver.find_element(By.CSS_SELECTOR, "iframe.dedamaFrame")
                iframe_src = iframe.get_attribute("src")
                logger.info(f"📱 iframe src found: {iframe_src}")

                # iframe ページに直接アクセス
                self.fetch_page(iframe_src)
                time.sleep(3)

                # HTML解析
                soup = BeautifulSoup(self.driver.page_source, "html.parser")

                # データ抽出（具体的な構造は実際のサイトに合わせて調整）
                data = self._parse_machine_data(soup)
                return {
                    "status": "success",
                    "scraped_at": datetime.now().isoformat(),
                    "data": data
                }

            except Exception as e:
                logger.error(f"⚠️ iframe processing error: {e}")
                # iframe がない場合は直接ページをパース
                soup = BeautifulSoup(self.driver.page_source, "html.parser")
                data = self._parse_machine_data(soup)
                return {
                    "status": "partial",
                    "scraped_at": datetime.now().isoformat(),
                    "data": data
                }

        except Exception as e:
            logger.error(f"❌ Scraping failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "scraped_at": datetime.now().isoformat()
            }

    def _parse_machine_data(self, soup):
        """HTMLから機種データをパース

        Args:
            soup (BeautifulSoup): パースされたHTML

        Returns:
            list: 機種データのリスト
        """
        machines = []

        # 実際のサイト構造に合わせて抽出
        # 以下は例; 実際のサイトを確認して修正が必要
        try:
            rows = soup.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 3:
                    try:
                        machine_name = cells[0].get_text(strip=True)
                        games_count = int(cells[1].get_text(strip=True).replace(",", ""))
                        medals_out = int(cells[2].get_text(strip=True).replace(",", ""))

                        machines.append({
                            "name": machine_name,
                            "games_count": games_count,
                            "medals_out": medals_out
                        })
                    except (ValueError, IndexError) as e:
                        logger.debug(f"⚠️ Failed to parse row: {e}")
                        continue

            logger.info(f"✅ Extracted {len(machines)} machines")
            return machines

        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return []
