#!/usr/bin/env python3
"""Render the web forecast card from `forecast.py --json` output.

    python3 forecast.py --json > /tmp/forecast.json
    python3 build_card.py /tmp/forecast.json -o /tmp/card.html

Or pipe it straight through:

    python3 forecast.py --json | python3 build_card.py -o /tmp/card.html

The card's markup lives in `card/template.html`; this script only substitutes
the title, the issue line, and the `REPORT` array the page draws from.
Presentation decisions that the forecast itself has no opinion about — which
pictogram a period gets, which English subtitle a location carries — are made
here rather than in `forecast.py`.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
WEEKDAY_ZH = "一二三四五六日"
TEMPLATE = pathlib.Path(__file__).resolve().parent / "card" / "template.html"
DAY_START_HOUR = 6

# Subtitles for the locations that come up often. Anything else falls back to
# no subtitle rather than a transliteration this script would have to guess.
EN_NAMES = {
    "臺北市": "Taipei City",
    "新北市": "New Taipei City",
    "新北市三重區": "Sanchong, New Taipei",
    "基隆市": "Keelung City",
    "桃園市": "Taoyuan City",
    "臺中市": "Taichung City",
    "臺南市": "Tainan City",
    "高雄市": "Kaohsiung City",
    "彰化縣": "Changhua County",
    "彰化縣彰化市": "Changhua City",
    "宜蘭縣": "Yilan County",
    "花蓮縣": "Hualien County",
    "臺東縣": "Taitung County",
}


def slot_category(period: dict) -> str:
    """The pictogram category: the forecast's four, plus thunder split off rain."""
    category = period.get("category") or "cloudy"
    if category == "rain" and "雷" in (period.get("weather") or ""):
        return "thunder"
    return category


def headline_category(slots: list[dict]) -> str:
    """Rain wins the headline; otherwise the category that holds the most of the day."""
    day = [s for s in slots if s["h"] >= DAY_START_HOUR] or slots
    rain = [s for s in day if s["cat"] in ("rain", "thunder")]
    if rain:
        return "thunder" if any(s["cat"] == "thunder" for s in rain) else "rain"
    counts: dict[str, int] = {}
    for slot in day:
        counts[slot["cat"]] = counts.get(slot["cat"], 0) + 1
    return max(counts, key=lambda c: counts[c])


def fill_missing_temps(slots: list[dict], fallback: int | None) -> None:
    """Carry the nearest reading into any gap so the temperature line stays drawable."""
    known = [i for i, s in enumerate(slots) if s["t"] is not None]
    if not known:
        for slot in slots:
            slot["t"] = fallback if fallback is not None else 0
        return
    for i, slot in enumerate(slots):
        if slot["t"] is None:
            nearest = min(known, key=lambda k: abs(k - i))
            slot["t"] = slots[nearest]["t"]


def mark_numbers(text: str) -> str:
    """Escape, then set digit runs in the mono face so times and percentages line up."""
    escaped = html.escape(text, quote=False)
    return re.sub(r"\d+(?:[–-]\d+)?", lambda m: f'<span class="num">{m.group()}</span>', escaped)


def to_card(entry: dict) -> dict:
    slots = [
        {
            "h": p["hour"],
            "wx": p["weather"],
            "cat": slot_category(p),
            "pop": p["pop"] if p["pop"] is not None else 0,
            "t": p["t"],
        }
        for p in entry["periods"]
    ]
    slots.sort(key=lambda s: s["h"])
    fill_missing_temps(slots, entry.get("temperature_max"))

    name = entry["location"]
    temps = [s["t"] for s in slots]
    return {
        "name": name,
        "en": EN_NAMES.get(name, ""),
        "cat": headline_category(slots),
        "tmin": entry.get("temperature_min") if entry.get("temperature_min") is not None else min(temps),
        "tmax": entry.get("temperature_max") if entry.get("temperature_max") is not None else max(temps),
        "line": mark_numbers(entry.get("timing") or ""),
        "tip": entry.get("tip"),
        "slots": slots,
    }


def build(entries: list[dict], sample: bool = False, now: datetime | None = None) -> str:
    good = [e for e in entries if "error" not in e]
    if not good:
        raise SystemExit("錯誤：沒有任何地點成功取得預報，不產生卡片")

    now = now or datetime.now(TZ)
    day = date.fromisoformat(good[0]["date"])
    title = f'明天 {day.month}/{day.day}<span class="wd">（{WEEKDAY_ZH[day.weekday()]}）</span>'

    issued = f"<span>{now.month}/{now.day} {now:%H:%M} 發報</span>"
    if sample:
        issued += '<span class="sample">範例資料</span>'
    failed = [e["error"] for e in entries if "error" in e]
    for message in failed:
        issued += f'<span class="warn">{html.escape(message, quote=False)}</span>'

    report = json.dumps([to_card(e) for e in good], ensure_ascii=False, indent=2)
    page = TEMPLATE.read_text(encoding="utf-8")
    for marker, value in (("__TITLE__", title), ("__ISSUED__", issued), ("__REPORT__", report)):
        if marker not in page:
            raise SystemExit(f"錯誤：範本缺少 {marker}")
        page = page.replace(marker, value)
    return page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="用 forecast.py --json 的輸出產生網頁版預報卡")
    parser.add_argument("json_file", nargs="?", help="forecast.py --json 的輸出檔，省略則讀 stdin")
    parser.add_argument("-o", "--out", default="build/card.html", help="輸出的 HTML 路徑")
    parser.add_argument("--sample", action="store_true", help="在頁面上標示「範例資料」")
    args = parser.parse_args(argv)

    raw = pathlib.Path(args.json_file).read_text(encoding="utf-8") if args.json_file else sys.stdin.read()
    page = build(json.loads(raw), sample=args.sample)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
