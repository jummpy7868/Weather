# Weather

每天晚上 18:00（台灣時間）用 Claude 推播「明天一整天」的天氣預報到手機，預設地點是臺北市與新北市三重區。

輸出範例：

```
明天 9/19（六）臺北市：早上 6 點到中午 12 點晴時多雲，中午 12 點起午後短暫雷陣雨（降雨機率 70%），傍晚 6 點前結束，之後轉多雲。氣溫 25 到 33 度，體感最高 37 度。建議帶傘、注意防曬與補水。
明天 9/19（六）新北市三重區：凌晨有雨，整天多雲。氣溫 25 到 32 度。
```

## 運作方式

1. `forecast.py` 向中央氣象署開放資料平台抓「鄉鎮天氣預報（逐 3 小時）」。
2. 用固定規則把明天切成連續的天氣時段（晴 / 多雲 / 陰 / 雨），「幾點開始下雨」由資料決定，不靠猜。
3. 依模板組成一段繁體中文，時間只用 3 小時格線（早上 6 點、中午 12 點、下午 3 點、傍晚 6 點…），不說出資料沒有的精度。
4. Claude 雲端 Routine 每天 18:00 執行腳本，把結果推播到手機，並留在同一個對話讓你追問其他地點。

## 設定

### 1. 申請氣象署授權碼（免費）

到 <https://opendata.cwa.gov.tw/> 註冊會員，在「會員資訊」取得授權碼（格式 `CWA-xxxxxxxx-...`）。

### 2. 本機執行

```bash
export CWA_API_KEY=CWA-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
python3 forecast.py                          # 預設：臺北市、新北市/三重區
python3 forecast.py 彰化縣/彰化市 臺中市       # 指定地點，「縣市」或「縣市/鄉鎮區」
python3 forecast.py --date 2026-09-20 臺北市  # 指定日期（預設 tomorrow）
python3 forecast.py --json                   # 輸出 JSON（含時段與原始 3 小時資料）
```

只需要 Python 3.9 以上，沒有第三方套件。

### 3. Routine 環境（讓雲端排程能連到氣象署）

Routine 在 Anthropic 的雲端環境執行，預設網路只允許常見套件來源，**連不到氣象署 API**。到 <https://claude.ai/code/routines> 開啟該 Routine 的環境設定：

- Network access 改成 **Custom**，Allowed domains 加入 `opendata.cwa.gov.tw`（勾選同時保留預設清單）。
- 加入 API credential 或環境變數 `CWA_API_KEY`，值為你的授權碼。

Routine 使用的提示詞存在 `routine/PROMPT.md`。

## 測試

```bash
python3 -m unittest discover -s tests -v          # 全部
python3 -m unittest tests.test_forecast.WordingTests -v   # 單一類別
python3 -m unittest tests.test_forecast.FixtureTests.test_taipei_narrative   # 單一測試
python3 forecast.py --fixture tests/fixtures/sample.json --date 2026-09-19   # 離線試跑
```

`tests/fixtures/sample.json` 是依氣象署新版 JSON 格式手工製作的樣本，涵蓋 2026-09-19。
