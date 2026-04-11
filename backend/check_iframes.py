"""iframe のコンテンツを確認"""
import sys
sys.path.insert(0, '/home/dev-nodee/projects/pachinko-analysis/backend')

import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
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

    time.sleep(5)

    # iframe を取得
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"📦 Found {len(iframes)} iframes\n")

    for i, iframe in enumerate(iframes):
        src = iframe.get_attribute("src")
        print(f"=== iframe {i} ===")
        print(f"src: {src}")

        # iframe に切り替え
        try:
            driver.switch_to.frame(iframe)
            iframe_html = driver.page_source
            iframe_soup = BeautifulSoup(iframe_html, "html.parser")

            # テキストを抽出
            text = iframe_soup.get_text(strip=True)

            print(f"Content length: {len(text)}")
            print(f"Content sample: {text[:200]}")

            # デフォルトフレームに戻す
            driver.switch_to.default_content()
            print()

        except Exception as e:
            print(f"❌ Could not access iframe: {e}\n")
            driver.switch_to.default_content()

    # ページ全体の構造を確認
    print("\n=== Main page structure ===")
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # すべての <a> タグを確認
    links = soup.find_all("a", limit=30)
    print(f"Links found: {len(links)}")
    for link in links[:10]:
        href = link.get("href", "")
        text = link.get_text(strip=True)
        if "台" in text or href:
            print(f"  {text}: {href}")

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
