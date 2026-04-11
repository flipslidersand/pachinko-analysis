"""ネットワークトラフィック監視スクリプト"""
import sys
sys.path.insert(0, '/home/dev-nodee/projects/pachinko-analysis/backend')

import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

# Selenium リモート接続
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

    # JavaScript で Fetch API をオーバーライド（ページロード前）
    js_code = """
    window.capturedRequests = [];
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
        const url = typeof args[0] === 'string' ? args[0] : args[0].url;
        window.capturedRequests.push({
            url: url,
            timestamp: new Date().toISOString()
        });
        console.log('FETCH:', url);
        return originalFetch.apply(this, args);
    };
    """

    print(f"📱 Loading {url}...")
    driver.get(url)

    # JavaScript 実行待ち
    time.sleep(5)

    # 現在のリクエスト一覧を取得
    print("\n🔍 Analyzing network requests...\n")

    # より直接的にネットワークトラフィックを確認
    # Selenium では直接的なネットワークキャプチャが難しいので、
    # Page から Network ログを取得する試み
    try:
        # ドライバーのログを確認
        logs = driver.get_log("performance")
        print(f"Performance logs: {len(logs)} entries\n")

        for log in logs:
            msg = log.get("message", "")
            if ".goraggio.com" in msg or "api" in msg:
                print(f"📊 {msg[:150]}")

    except Exception as e:
        print(f"⚠️ Could not get performance logs: {e}")

    # 別の方法：JavaScript でフェッチを監視
    print("\n\n--- Attempting to capture fetch calls ---\n")

    # JavaScript で Fetch API をオーバーライド
    js_code = """
    window.capturedRequests = [];
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
        window.capturedRequests.push({
            url: args[0],
            timestamp: new Date().toISOString()
        });
        return originalFetch.apply(this, args);
    };
    """

    driver.execute_script(js_code)

    # ページリロード
    driver.refresh()
    time.sleep(5)

    # キャプチャされたリクエスト取得
    captured = driver.execute_script("return window.capturedRequests || []")
    print(f"✅ Captured {len(captured)} fetch requests:\n")
    for req in captured:
        url = req.get("url", "")
        if url:
            print(f"  {url}")

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
