"""ページに表示されているデータを直接抽出"""
import sys
import os; sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup

url = "https://daidata.goraggio.com/p-world-daidataonline/101101"

options = Options()
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

driver = None
try:
    print("🔗 Connecting to Selenium...")
    driver = webdriver.Remote(
        command_executor="http://localhost:4444/wd/hub",
        options=options
    )

    print(f"📱 Loading {url}...")
    driver.get(url)

    # ページが完全にロードされるまで待機
    print("⏳ Waiting for full page load (10秒)...")
    time.sleep(10)

    # ページソース取得
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

    print(f"✅ Page loaded. Source length: {len(html)} bytes\n")

    # すべてのテキストを抽出（改行で区切る）
    all_text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in all_text.split("\n") if l.strip()]

    print(f"📄 Total lines: {len(lines)}\n")

    # ホール情報を検索
    print("=== 🏠 ホール情報 ===")
    for i, line in enumerate(lines):
        if "SUPER" in line or "市野" in line or "concorde" in line.lower():
            print(f"Line {i}: {line}")

    print("\n=== 🎰 スロット/パチンコ情報 ===")
    for i, line in enumerate(lines):
        if "スロット" in line or "パチンコ" in line or "台" in line:
            print(f"Line {i}: {line}")

    print("\n=== 📊 数字データ ===")
    # 数字を含む行を表示
    numeric_lines = [(i, l) for i, l in enumerate(lines) if any(c.isdigit() for c in l)]
    for i, line in numeric_lines[:30]:
        print(f"Line {i}: {line}")

    # 特定の構造を探す
    print("\n=== 🔍 HTML構造分析 ===")

    # div や table などの主要要素を確認
    divs = soup.find_all("div", limit=50)
    tables = soup.find_all("table")

    print(f"div 要素: {len(divs)}")
    print(f"table 要素: {len(tables)}")

    # データを含むかもしれない div を検索
    print("\n=== divのテキストコンテンツ（100文字以上） ===")
    for i, div in enumerate(divs[:20]):
        text = div.get_text(strip=True)
        if len(text) > 50 and any(c.isdigit() for c in text):
            print(f"Div {i}: {text[:100]}")

    # iframe をチェック
    iframes = soup.find_all("iframe")
    print(f"\n=== iframe ({len(iframes)}個) ===")
    for i, iframe in enumerate(iframes):
        print(f"iframe {i}: src={iframe.get('src')}, id={iframe.get('id')}")

    # スクリーンショットを取得してみる
    print("\n📸 Taking screenshot...")
    driver.save_screenshot("/tmp/pworld_screenshot.png")
    print("✅ Screenshot saved to /tmp/pworld_screenshot.png")

    driver.quit()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    if driver:
        try:
            driver.quit()
        except:
            pass
