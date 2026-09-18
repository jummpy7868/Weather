# 網頁版預報卡

`index.html` 是推播之外的「圖像化」版本，發布位置：
<https://claude.ai/artifact/EvdnK4Yx5WnzDQ8QkK7JKC>

目前 `REPORT` 是寫死的範例資料（2026-09-19），畫面上標示為「範例資料」。
要接上真實資料，把 `forecast.py --json` 的輸出轉成 `REPORT` 的格式即可：

| 卡片欄位 | 來源 |
| --- | --- |
| `cat` | `icon` 對應的分類，或 `segments` 裡佔比最長的 `category` |
| `tmin` / `tmax` | `temperature_min` / `temperature_max` |
| `line` | `text` 的第二行 |
| `slots[].wx` / `.pop` | `periods[].weather` / `.pop` |
| `slots[].t` | 目前 `--json` 未逐時輸出氣溫，需要時再補 |

圖上的虛線門檻與 `forecast.py` 的 `RAIN_POP_THRESHOLD` 是同一個值，改動時請一起改。
