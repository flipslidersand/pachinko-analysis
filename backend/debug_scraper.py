"""スクレイパーのデバッグスクリプト"""
import sys
sys.path.insert(0, '/home/dev-nodee/projects/pachinko-analysis/backend')

import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import json

# Selenium リモート接続
url = "https://daidata.goraggio.com/p-world-daidataonline/101101"

options = Options()
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

try:
    driver = webdriver.Remote(
        command_executor="http://localhost:4444/wd/hub",
        options=options
    )

    print(f"📱 Loading {url}...")
    driver.get(url)
    time.sleep(5)

    # ページソース取得
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # table タグを探す
    tables = soup.find_all("table")
    print(f"\n📊 Found {len(tables)} tables")

    if tables:
        print("\n=== First table sample ===")
        first_table = tables[0]
        rows = first_table.find_all("tr")[:5]
        for row in rows:
            cells = row.find_all("td")
            print([cell.get_text(strip=True)[:30] for cell in cells[:5]])

    # API コール履歴を確認（ブラウザログ）
    logs = driver.get_log("browser")
    print(f"\n🔍 Browser logs: {len(logs)} entries")
    for log in logs[:5]:
        print(f"  {log['level']}: {log['message'][:100]}")

    # ページ全体を表示（先頭1000文字）
    page_source = driver.page_source
    print(f"\n📄 Page source length: {len(page_source)}")

    # body タグのコンテンツを確認
    body = soup.find("body")
    if body:
        # テキストコンテンツを確認
        text_content = body.get_text(strip=True)
        print(f"\n📝 Body text length: {len(text_content)}")
        print(f"📝 Body text sample: {text_content[:200]}")

    # div id="root" 等を探す
    root = soup.find("div", id="root")
    if root:
        print(f"\n✅ Found root div: {len(root.contents)} children")

    # その他の div を確認
    all_divs = soup.find_all("div")[:10]
    print(f"\n🔍 First 10 divs:")
    for i, div in enumerate(all_divs):
        print(f"  {i}: class={div.get('class')}, id={div.get('id')}, content_len={len(div.get_text())}")

    driver.quit()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
