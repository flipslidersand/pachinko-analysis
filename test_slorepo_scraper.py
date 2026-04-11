#!/usr/bin/env python3
"""
Slorepo.com スクレイピング検証スクリプト
- 接続テスト
- HTML パース確認
- データ抽出成功確認
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json

# テスト対象URL
SLOREPO_URL = "https://www.slorepo.com/hole/73757065722d636f6e636f726465e5b882e9878ecode/20260410/matsubi/?history=30&kishu=heikin"

# User-Agent（必須）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


def test_connection():
    """HTTP接続テスト"""
    print("\n" + "="*60)
    print("🔌 Phase 1: HTTP接続テスト")
    print("="*60)

    try:
        response = requests.get(SLOREPO_URL, headers=HEADERS, timeout=10)
        print(f"✅ Status Code: {response.status_code}")
        print(f"✅ Content-Type: {response.headers.get('Content-Type', 'Unknown')}")
        print(f"✅ Content Length: {len(response.content)} bytes")
        return response.content
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None


def test_html_parsing(html_content):
    """HTMLパース テスト"""
    print("\n" + "="*60)
    print("🔍 Phase 2: HTMLパーステスト")
    print("="*60)

    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # ページタイトル確認
        title = soup.find('title')
        print(f"✅ Page Title: {title.text if title else 'Not found'}")

        # テーブル確認
        table = soup.find('table', class_='table2')
        if table:
            print(f"✅ Table found (class='table2')")
        else:
            print(f"❌ Table not found")
            return None

        # ヘッダ行確認
        header_cells = table.find_all('th')
        print(f"✅ Header columns: {len(header_cells)}")
        print(f"   - Column 1: {header_cells[0].text.strip()}")
        print(f"   - Column 2: {header_cells[1].text.strip()}")
        print(f"   - Column 3: {header_cells[2].text.strip()} (First date)")

        # データ行取得
        rows = table.find_all('tr')[1:]  # ヘッダスキップ
        print(f"✅ Data rows: {len(rows)}")

        return soup, table, rows

    except Exception as e:
        print(f"❌ Parsing failed: {e}")
        return None


def test_data_extraction(soup, table, rows):
    """データ抽出テスト"""
    print("\n" + "="*60)
    print("📊 Phase 3: データ抽出テスト")
    print("="*60)

    try:
        extracted_machines = []

        for idx, row in enumerate(rows[:5]):  # 最初の5機種をサンプル
            try:
                cells = row.find_all('td')
                if len(cells) < 3:
                    continue

                # 機種名取得
                machine_link = cells[0].find('a')
                machine_name = machine_link.text.strip() if machine_link else cells[0].text.strip()

                # 台数取得
                num_machines = cells[1].text.strip()

                # 日次データ抽出（最新日 = 最初のデータカラム）
                daily_data = []
                for col_idx in range(2, min(7, len(cells))):  # 最初の5日間
                    # <td><font color=red><strong>-200</strong></font></td> のような構造
                    cell_content = cells[col_idx].text.strip()
                    # 最初の数値のみ抽出（スペース前）
                    first_number = cell_content.split()[0] if cell_content else None
                    try:
                        diff_value = int(first_number)
                        daily_data.append(diff_value)
                    except (ValueError, TypeError):
                        daily_data.append(None)

                machine_info = {
                    "name": machine_name,
                    "num_machines": num_machines,
                    "recent_diffs": daily_data
                }
                extracted_machines.append(machine_info)

                print(f"\n📌 Machine {idx+1}: {machine_name}")
                print(f"   台数: {num_machines}")
                print(f"   過去5日の差枚: {daily_data}")

            except Exception as e:
                print(f"   ⚠️ Error parsing row: {e}")
                continue

        return extracted_machines

    except Exception as e:
        print(f"❌ Data extraction failed: {e}")
        return None


def test_data_validity(machines):
    """データ妥当性テスト"""
    print("\n" + "="*60)
    print("✅ Phase 4: データ妥当性テスト")
    print("="*60)

    if not machines:
        print("❌ No machines to validate")
        return False

    try:
        # サンプル統計
        all_diffs = []
        for machine in machines:
            for diff in machine["recent_diffs"]:
                if diff is not None:
                    all_diffs.append(diff)

        if all_diffs:
            print(f"✅ Total data points: {len(all_diffs)}")
            print(f"✅ Diff range: {min(all_diffs)} to {max(all_diffs)}")
            print(f"✅ Average diff: {sum(all_diffs) / len(all_diffs):.1f}")
            print(f"✅ Sample values: {all_diffs[:10]}")
            return True
        else:
            print("❌ No valid numeric data found")
            return False

    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False


def main():
    print("\n" + "="*60)
    print("🎰 Slorepo.com スクレイピング検証")
    print("="*60)
    print(f"Target: {SLOREPO_URL}\n")

    # Phase 1: 接続
    html_content = test_connection()
    if not html_content:
        return False

    # Phase 2: パース
    result = test_html_parsing(html_content)
    if not result:
        return False
    soup, table, rows = result

    # Phase 3: 抽出
    machines = test_data_extraction(soup, table, rows)
    if not machines:
        return False

    # Phase 4: 妥当性
    is_valid = test_data_validity(machines)

    # 最終結果
    print("\n" + "="*60)
    if is_valid:
        print("✅ スクレイピング実現可能!")
        print("="*60)
        print(f"✅ 抽出した機種数: {len(machines)}")
        print(f"✅ HTMLパース: 成功")
        print(f"✅ データ形式: 正常")
        print("\n次ステップ:")
        print("  1. ホール ID の自動取得方法を確認")
        print("  2. 本格的なスクレイパー実装 (src/scrapers/slorepo_scraper.py)")
        print("  3. 既存パイプラインへの統合")
        return True
    else:
        print("❌ スクレイピング実現困難")
        print("="*60)
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
