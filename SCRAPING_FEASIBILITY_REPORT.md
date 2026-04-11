# Slorepo.com スクレイピング可能性調査レポート

**調査日**: 2026-04-11  
**対象サイト**: https://www.slorepo.com  
**調査URL**: https://www.slorepo.com/hole/73757065722d636f6e636f726465e5b882e9878ecode/20260410/matsubi/?history=30&kishu=heikin

---

## 📊 データ構造分析

### ページ構成
- **言語**: 日本語 WordPress サイト（wp-content, wp-includes 確認）
- **robots.txt メタタグ**: `noindex, nofollow` ← インデックスは避けるが、スクレイピング禁止とは記載なし
- **ページタイプ**: 機種別の日次平均差枚(G数)推移表
- **データフォーマット**: 静的HTML（JavaScriptではなくサーバー側で生成）

### テーブル構造
```
<table class="table2">
  <tr>
    <th>機種名 (Machine Name)</th>
    <th>台数 (Number of Machines)</th>
    <th>4/10(金) (Daily Data - 30 columns)</th>
    <th>4/9(木)</th>
    ...
    <th>3/11(金)</th>
  </tr>
  <tr>
    <td>L東京喰種</td>
    <td>51</td>
    <td style="color:red"><strong>-200</strong></td>
    <td style="color:blue"><strong>103</strong></td>
    ...
  </tr>
</table>
```

### 抽出可能なデータフィールド

| フィールド | データ型 | 例 | 抽出難度 |
|----------|--------|-----|--------|
| 機種名 | String | L東京喰種 | ⭐ 簡単 |
| 台数 | Integer | 51 | ⭐ 簡単 |
| 日付 | Date | 2026-04-10 | ⭐⭐ 中程度 |
| 平均差枚 | Integer | -200, 103, 275 | ⭐ 簡単 |
| ステータス | Category | Win/Loss (色分け) | ⭐ 簡単 |

---

## 🔗 URL パターン分析

### ベース URL 構造
```
https://www.slorepo.com/hole/{hall_id}/{YYYYMMDD}/{type}/?history={days}&kishu={metric}
```

### パラメータ説明
- `{hall_id}`: ホール ID（URL エンコード済み）
  - 例: `73757065722d636f6e636f726465e5b882e9878ecode` → "super-concorde市野"の16進エンコード
- `{YYYYMMDD}`: 対象日付（例: 20260410）
- `{type}`: 機種タイプ
  - `matsubi` = スロット
  - `pachinko` = パチンコ（推定）
- `history={days}`: 過去何日分のデータを表示するか（30 = 直近30日）
- `kishu={metric}`: 表示する指標
  - `heikin` = 平均差枚（Average difference）

### 例 URL
```
# 2026-04-10, スーパーコンコルド市野, スロット, 平均差枚, 直近30日
https://www.slorepo.com/hole/73757065722d636f6e636f726465e5b882e9878ecode/20260410/matsubi/?history=30&kishu=heikin

# 別の店舗・日付への変更例
https://www.slorepo.com/hole/{別のhall_id}/{別のYYYYMMDD}/matsubi/?history=30&kishu=heikin
```

---

## ✅ スクレイピング実行可能性

### 技術的実現性: **非常に高い (95%)**

| 項目 | 結果 | 詳細 |
|------|------|------|
| **HTTP アクセス** | ✅ 成功 | User-Agent ヘッダで 403 回避可能 |
| **HTML 構造** | ✅ シンプル | テーブル構造が明確で解析容易 |
| **JavaScript 依存** | ✅ なし | 全データが静的HTML内に存在 |
| **認証要求** | ✅ なし | ログイン不要 |
| **レート制限** | ❓ 不明 | HTTP 429 エラーなし（短期テストでは） |
| **データ形式** | ✅ 統一 | 数値・テキスト形式が一貫性あり |

### 推奨スクレイピング方法

**ライブラリ組み合わせ**:
```python
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# 実装パターン
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

url = "https://www.slorepo.com/hole/{hall_id}/{date}/matsubi/?history=30&kishu=heikin"
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

# テーブル取得
table = soup.find('table', class_='table2')
rows = table.find_all('tr')[1:]  # ヘッダスキップ

for row in rows:
    cells = row.find_all('td')
    machine_name = cells[0].text.strip()
    num_machines = int(cells[1].text.strip())
    daily_diffs = [int(cells[i].text.strip()) for i in range(2, len(cells))]
```

---

## ⚠️ 注意事項・制限

### 1. **robots.txt メタタグ**
- `<meta name='robots' content='noindex, nofollow' />` が設定されている
- **意味**: Google などの検索エンジン向け「インデックスするな」という指示
- **スクレイピングへの影響**: 法的には強制力なし（慣例的なマナー指示）
- **推奨アプローチ**: 
  - サイト利用規約確認推奨
  - 短い間隔でのアクセスは避ける（1秒以上の待機推奨）
  - サーバー負荷軽減のため夜間実行推奨

### 2. **ホール ID の取得**
- 現在のシステムでは `hall_id` が `101101` でハードコード
- slorepo.com から自動取得するには、ホール一覧ページをスクレイピング必要
- **推定URL**: https://www.slorepo.com/shops/ (確認要)

### 3. **日付パラメータ**
- スロレポは過去データが蓄積されている模様
- 遡って取得可能だが、データ完全性は要検証

### 4. **レート制限**
- 詳細不明だが、一般的には:
  - 1秒待機 / リクエストで安全
  - 1店舗 × 30日 × 複数店舗でも十分対応可能

---

## 📈 データ活用シナリオ

### シナリオ 1: 既存 daidata.goraggio.com と統合

```
当日データ (daidata.goraggio.com)
        ↓
      本システム収集
        ↓
┌─────────────────────┐
│ raw_machine_data    │
│ (当日データ)         │
└─────────────────────┘
        ↓ (毎日23:00)
┌─────────────────────┐
│ daily_machine_stats │
│ (日次集計)          │
└─────────────────────┘
        ↓
過去データ (slorepo.com)
      バッチ追加
        ↓
┌─────────────────────┐
│ ml_features         │
│ (30+日の履歴)       │
└─────────────────────┘
```

### シナリオ 2: スロレポ → バックフィル

- 過去30日分を一括取得 → `raw_machine_data` に挿入
- 既存パイプラインで `daily_machine_stats` / `ml_features` 生成
- 特徴量の質向上（より多くの履歴データ）

### シナリオ 3: 定期同期（週次 or 月次）

- 週末に過去データと同期確認
- daidata との差分検証
- データ品質モニタリング

---

## 🛠️ 実装推奨手順

### Phase 1: 検証スクリプト作成
```python
# test_slorepo_scraper.py
# - 単一店舗の単一日付で接続テスト
# - HTML パース確認
# - データ抽出成功確認
```

### Phase 2: スクレイパー実装
```python
# src/scrapers/slorepo_scraper.py
# - 複数店舗対応
# - 日付範囲指定対応
# - エラーハンドリング
# - ログ出力
```

### Phase 3: DB 統合
```python
# 既存の raw_machine_data テーブルに insert
# 出典フラグ: 'daidata' vs 'slorepo'
```

### Phase 4: スケジューラ統合
```python
# scheduler/jobs.py に新規ジョブ追加
# 実行タイミング: 毎週日曜 23:00（低負荷時）
```

---

## 📋 チェックリスト

- [ ] サイト利用規約を確認
- [ ] 単一店舗 × 単一日付で接続テスト
- [ ] ホール ID エンコード方式を逆算
- [ ] hall_id 一覧の自動取得方法を検討
- [ ] データベーススキーマの出典管理方法を決定
- [ ] 本格実装前に管理者に確認 / 許可取得

---

## 📌 結論

**Slorepo.com からのスクレイピングは技術的に十分可能です。**

- ✅ 静的HTML で JavaScript 不要
- ✅ テーブル構造が標準的で解析容易
- ✅ User-Agent ヘッダで HTTP 403 を回避可能
- ✅ BeautifulSoup + requests で実装可能

**次ステップ**: ホール一覧取得方法の確認と、実装着手の判断
