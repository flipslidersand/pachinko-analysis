"""Selenium ベースのスクレイパー基底クラス"""
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import os

logger = logging.getLogger(__name__)


class BaseScraper:
    """Selenium ベースの基底スクレイパー"""

    def __init__(self, headless=True, timeout=30):
        """
        Args:
            headless (bool): ヘッドレスモードで実行するか
            timeout (int): 要素待機のタイムアウト（秒）
        """
        self.headless = headless
        self.timeout = timeout
        self.driver = None

    def _initialize_driver(self):
        """Selenium WebDriver を初期化"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("✅ WebDriver initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize WebDriver: {e}")
            raise

    def _wait_for_element(self, by, value):
        """要素が表示されるまで待機"""
        try:
            element = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by, value))
            )
            logger.debug(f"✅ Element found: {value}")
            return element
        except TimeoutException:
            logger.error(f"⏱️ Timeout waiting for element: {value}")
            raise

    def fetch_page(self, url):
        """ページを取得"""
        try:
            self.driver.get(url)
            logger.info(f"✅ Page loaded: {url}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to load page {url}: {e}")
            return False

    def get_page_source(self):
        """ページソース取得"""
        return self.driver.page_source

    def close(self):
        """ブラウザを閉じる"""
        if self.driver:
            self.driver.quit()
            logger.info("✅ WebDriver closed")

    def __enter__(self):
        """コンテキストマネージャー対応"""
        self._initialize_driver()
        return self

    def __exit__(self, *args):
        """コンテキストマネージャー対応"""
        self.close()
