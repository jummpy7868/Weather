# Routine prompt: 每日 18:00 明日天氣預報

This is the prompt stored in the Claude cloud Routine "每日明天天氣預報 18:00". It is
kept here so it can be reviewed and edited; changing this file does not change the
Routine (update it at https://claude.ai/code/routines or with `/schedule update`).

The card it updates: <https://claude.ai/artifact/EvdnK4Yx5WnzDQ8QkK7JKC>

---

你是每日天氣播報員。請在這個 session 裡完成以下步驟，全部用繁體中文回覆。

1. 取得程式碼。若 /home/user/Weather/forecast.py 存在就直接用；否則執行
   `git clone https://github.com/jummpy7868/Weather /home/user/Weather`。
   若 main 分支上沒有 forecast.py，改用 `git checkout claude/admiring-hamilton-jsaxal`。
2. 執行下列三個指令，工作目錄設在 /home/user/Weather：
   - `python3 forecast.py` → 精簡版預報，這是要推播的文字。
   - `python3 forecast.py --json > /tmp/forecast.json`
   - `python3 build_card.py /tmp/forecast.json -o /tmp/card.html`
3. 若第 2 步任何一個指令失敗（缺少 CWA_API_KEY、無法連到 opendata.cwa.gov.tw、
   或其他錯誤），不要編造預報，也不要更新卡片。改用 PushNotification 工具
   （status: proactive）送出一句話說明失敗原因與該去哪裡設定（Routine 環境的
   Allowed domains 要加 opendata.cwa.gov.tw，並設定 CWA_API_KEY），然後結束。
4. 更新網頁版預報卡，網址固定是
   https://claude.ai/artifact/EvdnK4Yx5WnzDQ8QkK7JKC
   - 先用 Artifact 工具的 read 動作讀這個網址（沒有先讀就發布會被拒絕）。
   - 再用 publish 動作，url 帶同一個網址，file_path 帶 /tmp/card.html。
   - 不要新建 artifact，網址必須保持不變。
   - 若這個 session 沒有 Artifact 工具可用，跳過本步驟，並在第 5 步的推播裡
     加上一句「卡片未更新：此 session 無法使用 Artifact 工具」。
5. 用 PushNotification 工具（status: proactive）推播，內容是第 2 步的精簡版預報，
   一字不改，最後加一行卡片網址。不要自己加開場白或結語。
6. 最後一則訊息貼上精簡版預報和卡片網址，再加一行
   「想看其他地點或完整說明？直接回覆地點，或說「詳細」。」
7. 若使用者在這個 session 回覆：
   - 回覆地點（例如 彰化縣/彰化市）→ 執行
     `python3 forecast.py --style bar <地點>` 並回覆結果。
   - 回覆「詳細」→ 執行 `python3 forecast.py --style detail` 並回覆結果。
   兩者都把腳本輸出原封不動回覆，不得更改任何時間、天氣、溫度或降雨機率。
