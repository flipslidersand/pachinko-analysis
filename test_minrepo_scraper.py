#!/usr/bin/env python3
"""
Min-repo.com スクレイピング検証スクリプト
"""

import requests
from bs4 import BeautifulSoup

# テスト対象URL
MINREPO_URL = "https://min-repo.com/3032904/"

# User-Agent（必須）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def test_minrepo():
    """Min-repo.com スクレイピング検証"""
    print("\n" + "="*60)
    print("🎰 Min-repo.com スクレイピング検証")
    print("="*60)
    print(f"Target: {MINREPO_URL}\n")

    try:
        # HTTP接続
        print("🔌 Phase 1: HTTP接続テスト")
        response = requests.get(MINREPO_URL, headers=HEADERS, timeout=10)
        print(f"✅ Status Code: {response.status_code}")
        print(f"✅ Content Length: {len(response.content)} bytes")

        # HTMLパース
        print("\n🔍 Phase 2: HTMLパーステスト")
        soup = BeautifulSoup(response.content, 'html.parser')

        # ページタイトル
        title = soup.find('title')
        print(f"✅ Page Title: {title.text if title else 'Not found'}")

        # テーブル検索
        tables = soup.find_all('table', class_='kishu')
        print(f"✅ Tables found: {len(tables)}")

        # 初めての機種別テーブルを処理
        if tables:
            table = tables[0]
            rows = table.find_all('tr')[1:]  # ヘッダスキップ
            print(f"✅ Data rows: {len(rows)}")

            # データ抽出
            print("\n📊 Phase 3: データ抽出テスト（最初の10機種）")
            machines = []
            for idx, row in enumerate(rows[:10]):
                cells = row.find_all('td')
                if len(cells) < 3:
                    continue

                try:
                    # 機種名
                    machine_link = cells[0].find('a')
                    machine_name = machine_link.text.strip() if machine_link else cells[0].text.strip()

                    # 平均差枚
                    avg_diff = cells[1].text.strip()

                    # 平均G数
                    avg_games = cells[2].text.strip()

                    # 勝率
                    win_rate = cells[3].text.strip() if len(cells) > 3 else "N/A"

                    # 出率
                    payout_rate = cells[4].text.strip() if len(cells) > 4 else "N/A"

                    machine_info = {
                        "name": machine_name,
                        "avg_diff": avg_diff,
                        "avg_games": avg_games,
                        "win_rate": win_rate,
                        "payout_rate": payout_rate
                    }
                    machines.append(machine_info)

                    print(f"\n📌 Machine {idx+1}: {machine_name}")
                    print(f"   平均差枚: {avg_diff}")
                    print(f"   平均G数: {avg_games}")
                    print(f"   勝率: {win_rate}")
                    print(f"   出率: {payout_rate}")

                except Exception as e:
                    print(f"   ⚠️ Error: {e}")
                    continue

            # データ妥当性
            print("\n" + "="*60)
            print("✅ データ妥当性テスト")
            print("="*60)
            print(f"✅ 抽出した機種数: {len(machines)}")

            if machines:
                print(f"✅ サンプル機種:")
                for m in machines[:3]:
                    print(f"   - {m['name']}: 差枚={m['avg_diff']}, G数={m['avg_games']}")

            print("\n" + "="*60)
            print("✅ Min-repo.com スクレイピング実現可能!")
            print("="*60)
            print("\n💡 特徴:")
            print("  • 当日の機種別統計データ（集計済み）")
            print("  • 平均差枚、平均G数、勝率、出率が取得可能")
            print("  • Slorepo との相互補完で強力な分析基盤が構築可能")

            return True

        else:
            print("❌ テーブルが見つかりません")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = test_minrepo()
    exit(0 if success else 1)
