"""DOM から直接データを抽出"""
import sys
sys.path.insert(0, '/home/dev-nodee/projects/pachinko-analysis/backend')

import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

    # ページ内のすべての要素を待機（最大30秒）
    print("⏳ Waiting for content to load...")
    wait = WebDriverWait(driver, 30)

    # さまざまな要素パターンを待機してみる
    selectors = [
        ("table", By.TAG_NAME),
        ("span", By.TAG_NAME),
        ("div[class*='machine']", By.CSS_SELECTOR),
        ("div[data-testid]", By.CSS_SELECTOR),
        (".row", By.CSS_SELECTOR),
        (".list", By.CSS_SELECTOR),
    ]

    found_elements = {}
    for name, by in selectors:
        try:
            elements = driver.find_elements(by, name)
            found_elements[name] = len(elements)
            if len(elements) > 0:
                print(f"✅ Found {len(elements)} elements: {name}")
        except:
            pass

    # ページソース取得
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # ページ内のすべてのテキストを抽出
    all_text = soup.get_text(separator="\n", strip=True)
    lines = [l for l in all_text.split("\n") if l.strip()]

    print(f"\n📄 Total lines: {len(lines)}")
    print("\n=== Content Sample (lines with numbers) ===")

    # 数字を含む行を表示（データはおそらく数字を含むはず）
    numeric_lines = [l for l in lines if any(c.isdigit() for c in l)]
    for line in numeric_lines[:20]:
        print(f"  {line[:80]}")

    # JavaScript コンソールで直接データを取得
    print("\n\n=== Trying JavaScript data extraction ===")

    js_results = driver.execute_script("""
    let data = [];

    // 数字を含むすべての span, div, td をチェック
    document.querySelectorAll('span, div, td').forEach(el => {
        let text = el.innerText || el.textContent;
        if (text && /\d+/.test(text) && text.length < 100) {
            data.push({
                tag: el.tagName,
                class: el.className,
                text: text.substring(0, 50)
            });
        }
    });

    return {
        total_elements: data.length,
        samples: data.slice(0, 20)
    };
    """)

    print(f"Elements found via JavaScript: {js_results['total_elements']}")
    print("\nSamples:")
    for item in js_results.get('samples', [])[:10]:
        print(f"  {item['tag']} ({item['class'][:30]}): {item['text']}")

    # HTML構造を表示
    print("\n\n=== HTML Structure ===")
    main_content = soup.find("main") or soup.find("div", id="root") or soup.find("body")
    if main_content:
        print(f"Main structure:")
        for child in main_content.children:
            if hasattr(child, 'name'):
                print(f"  <{child.name}> class={child.get('class')} id={child.get('id')}")

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
