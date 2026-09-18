#!/usr/bin/env python3
"""Next-day weather forecast in Traditional Chinese from Taiwan CWA Open Data.

Fetches the 3-hourly township forecast (dataset family F-D0047) from the
Central Weather Administration, splits the target day into weather periods
with deterministic rules, and renders a short Chinese narrative such as:

    明天 9/19（五）臺北市：早上 6 點到中午 12 點晴，中午 12 點起午後短暫雷陣雨
    （降雨機率 70%），傍晚 6 點前結束，之後轉多雲。氣溫 26 到 33 度。建議帶傘。

Only the Python standard library is used.

Usage:
    CWA_API_KEY=CWA-xxxx python3 forecast.py                 # default locations
    CWA_API_KEY=CWA-xxxx python3 forecast.py 彰化縣/彰化市    # county/district
    CWA_API_KEY=CWA-xxxx python3 forecast.py --date 2026-09-20 臺北市
    python3 forecast.py --fixture tests/fixtures/sample.json 臺北市  # offline
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
API_BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/"
API_KEY_ENV = "CWA_API_KEY"

DEFAULT_LOCATIONS = ["臺北市", "新北市/三重區"]

# A period counts as rain when the weather phrase mentions rain, or when the
# 3-hour probability of precipitation reaches this value even without it.
RAIN_POP_THRESHOLD = 60

# Hours of the target day covered by the main narrative. Overnight rain
# (00:00-06:00) is mentioned separately so the sentence stays about the day.
DAY_START_HOUR = 6

# 3-hourly township forecasts: one dataset per county. Dataset 089 holds the
# same data aggregated per county, used when no district is given.
COUNTY_DATASETS = {
    "宜蘭縣": "F-D0047-001",
    "桃園市": "F-D0047-005",
    "新竹縣": "F-D0047-009",
    "苗栗縣": "F-D0047-013",
    "彰化縣": "F-D0047-017",
    "南投縣": "F-D0047-021",
    "雲林縣": "F-D0047-025",
    "嘉義縣": "F-D0047-029",
    "屏東縣": "F-D0047-033",
    "臺東縣": "F-D0047-037",
    "花蓮縣": "F-D0047-041",
    "澎湖縣": "F-D0047-045",
    "基隆市": "F-D0047-049",
    "新竹市": "F-D0047-053",
    "嘉義市": "F-D0047-057",
    "臺北市": "F-D0047-061",
    "高雄市": "F-D0047-065",
    "新北市": "F-D0047-069",
    "臺中市": "F-D0047-073",
    "臺南市": "F-D0047-077",
    "連江縣": "F-D0047-081",
    "金門縣": "F-D0047-085",
}
COUNTY_LEVEL_DATASET = "F-D0047-089"

WEEKDAY_ZH = "一二三四五六日"

# One glyph per weather category, used for the headline and the timeline strip.
ICONS = {
    "thunder": "⛈️",
    "rain": "🌧️",
    "sunny": "☀️",
    "cloudy": "⛅",
    "overcast": "☁️",
}


# --------------------------------------------------------------------------
# Location handling
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Location:
    county: str
    district: str | None = None

    @property
    def display_name(self) -> str:
        return self.county + (self.district or "")

    @property
    def dataset(self) -> str:
        return COUNTY_LEVEL_DATASET if self.district is None else COUNTY_DATASETS[self.county]

    @property
    def query_name(self) -> str:
        return self.district or self.county


def normalize_name(name: str) -> str:
    """Map the common 台 spelling to the official 臺 and trim whitespace."""
    return name.strip().replace("台", "臺")


def parse_location(spec: str) -> Location:
    """Parse "臺北市" or "新北市/三重區" (also accepts 台 spelling and full-width /)."""
    spec = normalize_name(spec).replace("／", "/")
    parts = [p for p in spec.split("/") if p]
    if not parts or len(parts) > 2:
        raise ValueError(f"地點格式錯誤：{spec!r}，請用「縣市」或「縣市/鄉鎮區」")
    county = parts[0]
    if county not in COUNTY_DATASETS:
        raise ValueError(f"不認識的縣市：{county}，可用：{'、'.join(COUNTY_DATASETS)}")
    district = parts[1] if len(parts) == 2 else None
    return Location(county, district)


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def build_url(location: Location, api_key: str) -> str:
    query = urllib.parse.urlencode(
        {"Authorization": api_key, "LocationName": location.query_name, "format": "JSON"}
    )
    return f"{API_BASE}{location.dataset}?{query}"


def fetch_dataset(location: Location, api_key: str, timeout: int = 30) -> dict:
    url = build_url(location, api_key)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"氣象署 API 回應 HTTP {err.code}（{location.display_name}）") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"無法連線到氣象署 API：{err.reason}") from err
    if str(payload.get("success")).lower() != "true":
        raise RuntimeError(f"氣象署 API 回傳失敗：{json.dumps(payload, ensure_ascii=False)[:300]}")
    return payload


# --------------------------------------------------------------------------
# Parsing the CWA payload
# --------------------------------------------------------------------------


@dataclass
class Period:
    """One 3-hour forecast slot."""

    start: datetime
    end: datetime
    weather: str
    pop: int | None
    temp: int | None = None

    @property
    def is_rain(self) -> bool:
        return "雨" in self.weather or (self.pop is not None and self.pop >= RAIN_POP_THRESHOLD)

    @property
    def category(self) -> str:
        if self.is_rain:
            return "rain"
        if self.weather.startswith("晴"):
            return "sunny"
        if self.weather.startswith("陰"):
            return "overcast"
        return "cloudy"

    @property
    def icon(self) -> str:
        if self.is_rain and "雷" in self.weather:
            return ICONS["thunder"]
        return ICONS[self.category]


@dataclass
class DayForecast:
    location_name: str
    day: date
    periods: list[Period]
    temperatures: list[int] = field(default_factory=list)
    apparent: list[int] = field(default_factory=list)
    official_descriptions: list[str] = field(default_factory=list)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(TZ)


def _find_location(payload: dict, location: Location) -> dict:
    locations = payload.get("records", {}).get("Locations") or []
    wanted = location.query_name
    for group in locations:
        for entry in group.get("Location", []):
            if normalize_name(entry.get("LocationName", "")) == wanted:
                return entry
    raise RuntimeError(f"氣象署資料裡找不到「{location.display_name}」，請確認鄉鎮區名稱")


def _elements_by_name(entry: dict) -> dict[str, list[dict]]:
    return {el["ElementName"]: el.get("Time", []) for el in entry.get("WeatherElement", [])}


def _value(slot: dict, key: str) -> str | None:
    for item in slot.get("ElementValue", []):
        if key in item:
            return item[key]
    return None


def _to_int(text: str | None) -> int | None:
    if text is None:
        return None
    text = text.strip()
    if not text or text == "-":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def extract_day(payload: dict, location: Location, day: date) -> DayForecast:
    entry = _find_location(payload, location)
    elements = _elements_by_name(entry)

    pop_by_start: dict[datetime, int | None] = {}
    for slot in elements.get("3小時降雨機率", []):
        pop_by_start[_parse_time(slot["StartTime"])] = _to_int(_value(slot, "ProbabilityOfPrecipitation"))

    # 溫度 is published as instantaneous readings on the same 3-hour grid, so each
    # weather period can carry the reading at its start.
    temp_by_time: dict[datetime, int | None] = {}
    for slot in elements.get("溫度", []):
        temp_by_time[_parse_time(slot["DataTime"])] = _to_int(_value(slot, "Temperature"))

    periods: list[Period] = []
    for slot in elements.get("天氣現象", []):
        start = _parse_time(slot["StartTime"])
        end = _parse_time(slot["EndTime"])
        if start.date() != day:
            continue
        periods.append(Period(start, end, _value(slot, "Weather") or "",
                              pop_by_start.get(start), temp_by_time.get(start)))
    periods.sort(key=lambda p: p.start)
    if not periods:
        raise RuntimeError(f"資料裡沒有 {day.isoformat()} 的預報（{location.display_name}）")

    def instantaneous(name: str, key: str) -> list[int]:
        values = []
        for slot in elements.get(name, []):
            when = _parse_time(slot["DataTime"])
            if when.date() == day:
                value = _to_int(_value(slot, key))
                if value is not None:
                    values.append(value)
        return values

    descriptions = [
        _value(slot, "WeatherDescription") or ""
        for slot in elements.get("天氣預報綜合描述", [])
        if _parse_time(slot["StartTime"]).date() == day
    ]

    return DayForecast(
        location_name=location.display_name,
        day=day,
        periods=periods,
        temperatures=instantaneous("溫度", "Temperature"),
        apparent=instantaneous("體感溫度", "ApparentTemperature"),
        official_descriptions=descriptions,
    )


# --------------------------------------------------------------------------
# Segmentation: deterministic, so "when it starts raining" comes from data
# --------------------------------------------------------------------------


@dataclass
class Segment:
    start_hour: int
    end_hour: int  # 24 means end of day
    category: str
    label: str
    max_pop: int | None


_BASE_PREFIX = re.compile(r"^(晴|多雲|陰)(時(晴|多雲|陰))?")


def rain_label(weather: str) -> str:
    """'多雲午後短暫雷陣雨' -> '午後短暫雷陣雨'; '陰有雨' -> '有雨'."""
    stripped = _BASE_PREFIX.sub("", weather)
    return stripped or "有雨"


def _label_for(period: Period) -> str:
    if period.category == "rain":
        return rain_label(period.weather) if "雨" in period.weather else "可能有雨"
    return period.weather


def segment_periods(periods: list[Period]) -> list[Segment]:
    segments: list[Segment] = []
    for period in periods:
        start_hour = period.start.hour
        end_hour = 24 if period.end.date() > period.start.date() else period.end.hour
        label = _label_for(period)
        if segments and segments[-1].category == period.category and segments[-1].end_hour == start_hour:
            current = segments[-1]
            current.end_hour = end_hour
            if period.pop is not None and (current.max_pop is None or period.pop > current.max_pop):
                current.max_pop = period.pop
                if period.category == "rain":
                    current.label = label  # describe rain by its wettest slot
            continue
        segments.append(Segment(start_hour, end_hour, period.category, label, period.pop))
    return segments


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def hour_phrase(hour: int) -> str:
    if hour >= 24:
        return "午夜"
    if hour < 6:
        return f"凌晨 {hour} 點"
    if hour < 9:
        return f"早上 {hour} 點"
    if hour < 12:
        return f"上午 {hour} 點"
    if hour == 12:
        return "中午 12 點"
    if hour < 18:
        return f"下午 {hour - 12} 點"
    if hour < 21:
        return f"傍晚 {hour - 12} 點"
    return f"晚上 {hour - 12} 點"


def _pop_note(segment: Segment) -> str:
    return f"（降雨機率 {segment.max_pop}%）" if segment.max_pop is not None else ""


def describe_segments(segments: list[Segment]) -> str:
    """Turn the day's segments into one timeline sentence (without the final 。)."""
    night = [s for s in segments if s.end_hour <= DAY_START_HOUR]
    day = [s for s in segments if s.end_hour > DAY_START_HOUR]

    parts: list[str] = []
    if any(s.category == "rain" for s in night):
        parts.append("凌晨有雨")

    if not day:
        return "、".join(parts) if parts else "無資料"

    if len(day) == 1:
        only = day[0]
        text = f"整天{only.label}"
        if only.category == "rain":
            text += _pop_note(only)
        parts.append(text)
        return "，".join(parts)

    first = day[0]
    start = max(first.start_hour, DAY_START_HOUR)
    parts.append(f"{hour_phrase(start)}到{hour_phrase(first.end_hour)}{first.label}")

    for index, segment in enumerate(day[1:], start=1):
        is_last = index == len(day) - 1
        if segment.category == "rain":
            text = f"{hour_phrase(segment.start_hour)}起{segment.label}{_pop_note(segment)}"
            if not is_last:
                text += f"，{hour_phrase(segment.end_hour)}前結束"
            parts.append(text)
        else:
            prev_was_rain = day[index - 1].category == "rain"
            if prev_was_rain:
                parts.append(f"之後轉{segment.label}")
            else:
                parts.append(f"{hour_phrase(segment.start_hour)}後轉{segment.label}")
    return "，".join(parts)


def advice(forecast: DayForecast, segments: list[Segment]) -> list[str]:
    """At most two short tips, most useful first. Overnight-only rain does not count."""
    tips: list[str] = []
    if any(s.category == "rain" and s.end_hour > DAY_START_HOUR for s in segments):
        tips.append("帶傘")
    temps = forecast.temperatures
    if temps:
        if min(temps) <= 14:
            tips.append("注意保暖")
        elif max(temps) >= 33:
            tips.append("注意防曬與補水")
        elif max(temps) - min(temps) >= 8:
            tips.append("早晚溫差大帶件外套")
    return tips[:2]


def render_detail(forecast: DayForecast) -> str:
    """Full prose sentence. Used when the reader asked for detail, not for the push."""
    segments = segment_periods(forecast.periods)
    day = forecast.day
    header = f"明天 {day.month}/{day.day}（{WEEKDAY_ZH[day.weekday()]}）{forecast.location_name}："
    sentences = [describe_segments(segments)]

    temps = forecast.temperatures
    if temps:
        temp_text = f"氣溫 {min(temps)} 到 {max(temps)} 度"
        if forecast.apparent and max(forecast.apparent) - max(temps) >= 3:
            temp_text += f"，體感最高 {max(forecast.apparent)} 度"
        sentences.append(temp_text)

    tips = advice(forecast, segments)
    if tips:
        sentences.append("建議" + "、".join(tips))

    return header + "。".join(sentences) + "。"


# -- compact styles, built for a push notification ---------------------------


_TIME_PREFIX = re.compile(r"^(午後|晚上|清晨|白天|夜晚|入夜後)")


def day_segments(segments: list[Segment]) -> list[Segment]:
    return [s for s in segments if s.end_hour > DAY_START_HOUR]


def headline_icon(forecast: DayForecast) -> str:
    """One glyph for the whole day: rain wins, otherwise the longest stretch."""
    day = [p for p in forecast.periods if p.start.hour >= DAY_START_HOUR] or forecast.periods
    rain = [p for p in day if p.is_rain]
    if rain:
        return ICONS["thunder"] if any("雷" in p.weather for p in rain) else ICONS["rain"]
    longest = max(day_segments(segment_periods(day)) or segment_periods(day),
                  key=lambda s: s.end_hour - s.start_hour)
    return ICONS[longest.category]


def compact_timing(segments: list[Segment]) -> str:
    """The day in one short line, using a 24-hour clock so it scans fast."""
    parts: list[str] = []
    if any(s.category == "rain" and s.end_hour <= DAY_START_HOUR for s in segments):
        parts.append("凌晨有雨")

    day = day_segments(segments)
    rains = [s for s in day if s.category == "rain"]
    if rains:
        for segment in rains:
            start = max(segment.start_hour, DAY_START_HOUR)
            window = f"{start:02d} 時起" if segment.end_hour >= 24 else f"{start:02d}–{segment.end_hour:02d} 時"
            # The window already says when, so drop any time-of-day prefix from the label.
            label = _TIME_PREFIX.sub("", segment.label) or segment.label
            text = f"{window} {label}"
            if segment.max_pop is not None:
                text += f" {segment.max_pop}%"
            parts.append(text)
    elif len(day) == 1:
        parts.append(f"整天{day[0].label}")
    elif day:
        labels: list[str] = []
        for segment in day:
            if not labels or labels[-1] != segment.label:
                labels.append(segment.label)
        parts.append("轉".join(labels))

    return "、".join(parts) if parts else "無資料"


def emoji_bar(periods: list[Period]) -> str:
    """A mini timeline: hour ticks with one glyph per 3-hour slot between them."""
    by_hour = {p.start.hour: p.icon for p in periods}
    marks = [f"{tick:02d} " + "".join(by_hour.get(h, "·") for h in (tick, tick + 3))
             for tick in (6, 12, 18)]
    return " ".join(marks) + " 24"


def render_compact(forecast: DayForecast, bar: bool = False) -> str:
    segments = segment_periods(forecast.periods)
    temps = forecast.temperatures
    temp = f" {min(temps)}–{max(temps)}°" if temps else ""
    lines = [f"{headline_icon(forecast)} {forecast.location_name}{temp}"]
    if bar:
        lines.append(emoji_bar(forecast.periods))
    detail = compact_timing(segments)
    tips = advice(forecast, segments)
    if tips:
        detail += " · " + tips[0]  # one action only; the push has to stay glanceable
    lines.append(detail)
    return "\n".join(lines)


def render_report(forecasts: list[DayForecast], style: str = "compact") -> str:
    """Render one or more locations as the message that gets pushed."""
    if style == "detail":
        return "\n".join(render_detail(f) for f in forecasts)
    day = forecasts[0].day
    header = f"明天 {day.month}/{day.day}（{WEEKDAY_ZH[day.weekday()]}）"
    blocks = [render_compact(f, bar=(style == "bar")) for f in forecasts]
    return header + "\n\n" + "\n\n".join(blocks)


def to_json(forecast: DayForecast) -> dict:
    return {
        "location": forecast.location_name,
        "date": forecast.day.isoformat(),
        "icon": headline_icon(forecast),
        "text": render_compact(forecast),
        "detail": render_detail(forecast),
        "timing": compact_timing(segment_periods(forecast.periods)),
        "tip": (advice(forecast, segment_periods(forecast.periods)) or [None])[0],
        "segments": [
            {
                "start_hour": s.start_hour,
                "end_hour": s.end_hour,
                "category": s.category,
                "label": s.label,
                "max_pop": s.max_pop,
            }
            for s in segment_periods(forecast.periods)
        ],
        "periods": [
            {
                "start": p.start.isoformat(),
                "end": p.end.isoformat(),
                "hour": p.start.hour,
                "weather": p.weather,
                "category": p.category,
                "pop": p.pop,
                "t": p.temp,
            }
            for p in forecast.periods
        ],
        "temperature_min": min(forecast.temperatures) if forecast.temperatures else None,
        "temperature_max": max(forecast.temperatures) if forecast.temperatures else None,
        "official_descriptions": forecast.official_descriptions,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def resolve_date(text: str | None) -> date:
    today = datetime.now(TZ).date()
    if text in (None, "", "tomorrow"):
        return today + timedelta(days=1)
    if text == "today":
        return today
    return date.fromisoformat(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="中央氣象署明日天氣預報（繁體中文）")
    parser.add_argument("locations", nargs="*", help="縣市 或 縣市/鄉鎮區，例如 臺北市 新北市/三重區")
    parser.add_argument("--date", default="tomorrow", help="tomorrow（預設）、today 或 YYYY-MM-DD")
    parser.add_argument(
        "--style",
        choices=["compact", "bar", "detail"],
        default="compact",
        help="compact（預設，推播用）、bar（加上時間軸圖示）、detail（完整敘述）",
    )
    parser.add_argument("--json", action="store_true", help="輸出 JSON 而非純文字")
    parser.add_argument("--fixture", help="用本機 JSON 檔取代 API（測試用）")
    args = parser.parse_args(argv)

    try:
        locations = [parse_location(s) for s in (args.locations or DEFAULT_LOCATIONS)]
        day = resolve_date(args.date)
    except ValueError as err:
        print(f"錯誤：{err}", file=sys.stderr)
        return 2

    api_key = os.environ.get(API_KEY_ENV, "")
    if not args.fixture and not api_key:
        print(f"錯誤：缺少環境變數 {API_KEY_ENV}（中央氣象署開放資料授權碼）", file=sys.stderr)
        return 2

    forecasts: list[DayForecast] = []
    failures: list[str] = []
    exit_code = 0
    for location in locations:
        try:
            if args.fixture:
                with open(args.fixture, encoding="utf-8") as handle:
                    payload = json.load(handle)
            else:
                payload = fetch_dataset(location, api_key)
            forecasts.append(extract_day(payload, location, day))
        except (RuntimeError, KeyError, ValueError) as err:
            exit_code = 1
            failures.append(f"{location.display_name}：取得預報失敗，{err}")

    if args.json:
        results = [to_json(f) for f in forecasts]
        results += [{"error": message} for message in failures]
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if forecasts:
            print(render_report(forecasts, args.style))
        for message in failures:
            print(message, file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
