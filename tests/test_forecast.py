import json
import os
import subprocess
import sys
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forecast  # noqa: E402
from forecast import (  # noqa: E402
    TZ,
    Location,
    Period,
    compact_timing,
    describe_segments,
    emoji_bar,
    extract_day,
    hour_phrase,
    parse_location,
    rain_label,
    render_compact,
    render_detail,
    render_report,
    segment_periods,
)

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sample.json")
DAY = date(2026, 9, 19)


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)


def period(day, start_hour, weather, pop=None):
    start = datetime(day.year, day.month, day.day, start_hour, tzinfo=TZ)
    return Period(start, start + timedelta(hours=3), weather, pop)


class LocationTests(unittest.TestCase):
    def test_county_only_uses_county_level_dataset(self):
        loc = parse_location("台北市")
        self.assertEqual(loc, Location("臺北市", None))
        self.assertEqual(loc.dataset, "F-D0047-089")
        self.assertEqual(loc.query_name, "臺北市")

    def test_district_uses_county_dataset(self):
        loc = parse_location("新北市/三重區")
        self.assertEqual(loc.dataset, "F-D0047-069")
        self.assertEqual(loc.query_name, "三重區")
        self.assertEqual(loc.display_name, "新北市三重區")

    def test_unknown_county_rejected(self):
        with self.assertRaises(ValueError):
            parse_location("火星市")

    def test_build_url_includes_key_and_location(self):
        url = forecast.build_url(parse_location("彰化縣/彰化市"), "CWA-TEST")
        self.assertIn("F-D0047-017", url)
        self.assertIn("Authorization=CWA-TEST", url)
        self.assertIn("LocationName=%E5%BD%B0%E5%8C%96%E5%B8%82", url)


class SegmentationTests(unittest.TestCase):
    def test_rain_by_weather_phrase(self):
        self.assertTrue(period(DAY, 12, "多雲午後短暫雷陣雨", 30).is_rain)
        self.assertEqual(period(DAY, 12, "多雲午後短暫雷陣雨", 30).category, "rain")

    def test_rain_by_high_pop_without_phrase(self):
        self.assertTrue(period(DAY, 12, "多雲", 60).is_rain)
        self.assertFalse(period(DAY, 12, "多雲", 59).is_rain)

    def test_categories(self):
        self.assertEqual(period(DAY, 6, "晴時多雲", 10).category, "sunny")
        self.assertEqual(period(DAY, 6, "多雲時晴", 10).category, "cloudy")
        self.assertEqual(period(DAY, 6, "陰時多雲", 10).category, "overcast")

    def test_rain_label_strips_base_phrase(self):
        self.assertEqual(rain_label("多雲午後短暫雷陣雨"), "午後短暫雷陣雨")
        self.assertEqual(rain_label("陰有雨"), "有雨")
        self.assertEqual(rain_label("晴時多雲短暫陣雨"), "短暫陣雨")

    def test_consecutive_same_category_merge_and_keep_wettest_label(self):
        periods = [
            period(DAY, 6, "晴", 10),
            period(DAY, 9, "晴時多雲", 10),
            period(DAY, 12, "多雲短暫陣雨", 50),
            period(DAY, 15, "多雲午後短暫雷陣雨", 80),
            period(DAY, 18, "多雲", 20),
            period(DAY, 21, "多雲", 20),
        ]
        segments = segment_periods(periods)
        self.assertEqual([(s.start_hour, s.end_hour, s.category) for s in segments],
                         [(6, 12, "sunny"), (12, 18, "rain"), (18, 24, "cloudy")])
        self.assertEqual(segments[1].label, "午後短暫雷陣雨")
        self.assertEqual(segments[1].max_pop, 80)


class WordingTests(unittest.TestCase):
    def test_hour_phrases(self):
        self.assertEqual(hour_phrase(0), "凌晨 0 點")
        self.assertEqual(hour_phrase(6), "早上 6 點")
        self.assertEqual(hour_phrase(9), "上午 9 點")
        self.assertEqual(hour_phrase(12), "中午 12 點")
        self.assertEqual(hour_phrase(15), "下午 3 點")
        self.assertEqual(hour_phrase(18), "傍晚 6 點")
        self.assertEqual(hour_phrase(21), "晚上 9 點")
        self.assertEqual(hour_phrase(24), "午夜")

    def test_all_day_single_segment(self):
        segments = segment_periods([period(DAY, h, "晴", 10) for h in range(0, 24, 3)])
        self.assertEqual(describe_segments(segments), "整天晴")

    def test_overnight_rain_is_mentioned_separately(self):
        periods = [period(DAY, 0, "陰短暫雨", 60), period(DAY, 3, "陰", 30)]
        periods += [period(DAY, h, "多雲", 20) for h in range(6, 24, 3)]
        self.assertEqual(describe_segments(segment_periods(periods)), "凌晨有雨，整天多雲")

    def test_rain_ending_before_last_segment(self):
        periods = [period(DAY, h, "多雲", 10) for h in range(0, 12, 3)]
        periods += [period(DAY, 12, "多雲午後短暫雷陣雨", 70), period(DAY, 15, "多雲午後短暫雷陣雨", 60)]
        periods += [period(DAY, h, "多雲", 20) for h in range(18, 24, 3)]
        self.assertEqual(
            describe_segments(segment_periods(periods)),
            "早上 6 點到中午 12 點多雲，中午 12 點起午後短暫雷陣雨（降雨機率 70%），傍晚 6 點前結束，之後轉多雲",
        )

    def test_rain_until_end_of_day_has_no_end_clause(self):
        periods = [period(DAY, h, "晴", 10) for h in range(0, 15, 3)]
        periods += [period(DAY, h, "陰短暫雨", 70) for h in range(15, 24, 3)]
        self.assertEqual(
            describe_segments(segment_periods(periods)),
            "早上 6 點到下午 3 點晴，下午 3 點起短暫雨（降雨機率 70%）",
        )


class CompactTests(unittest.TestCase):
    def test_rain_window_uses_24h_clock_and_drops_time_prefix(self):
        segments = segment_periods(
            [period(DAY, h, "多雲", 10) for h in range(0, 12, 3)]
            + [period(DAY, 12, "多雲午後短暫雷陣雨", 70), period(DAY, 15, "多雲午後短暫雷陣雨", 60)]
            + [period(DAY, h, "多雲", 20) for h in range(18, 24, 3)]
        )
        self.assertEqual(compact_timing(segments), "12–18 時 短暫雷陣雨 70%")

    def test_rain_to_end_of_day_uses_open_window(self):
        segments = segment_periods(
            [period(DAY, h, "晴", 10) for h in range(0, 15, 3)]
            + [period(DAY, h, "陰短暫雨", 70) for h in range(15, 24, 3)]
        )
        self.assertEqual(compact_timing(segments), "15 時起 短暫雨 70%")

    def test_dry_day_collapses_to_one_phrase(self):
        segments = segment_periods([period(DAY, h, "晴", 10) for h in range(0, 24, 3)])
        self.assertEqual(compact_timing(segments), "整天晴")

    def test_dry_day_with_change_uses_turn_phrase(self):
        segments = segment_periods(
            [period(DAY, h, "晴", 10) for h in range(0, 12, 3)]
            + [period(DAY, h, "多雲", 20) for h in range(12, 24, 3)]
        )
        self.assertEqual(compact_timing(segments), "晴轉多雲")

    def test_emoji_bar_has_three_ticks(self):
        periods = [period(DAY, h, "晴", 10) for h in range(0, 12, 3)]
        periods += [period(DAY, h, "多雲午後短暫雷陣雨", 70) for h in range(12, 18, 3)]
        periods += [period(DAY, h, "多雲", 20) for h in range(18, 24, 3)]
        self.assertEqual(emoji_bar(periods), "06 ☀️☀️ 12 ⛈️⛈️ 18 ⛅⛅ 24")


class FixtureTests(unittest.TestCase):
    def test_taipei_compact(self):
        day = extract_day(load_fixture(), parse_location("臺北市"), DAY)
        self.assertEqual(
            render_compact(day),
            "⛈️ 臺北市 25–33°\n12–18 時 短暫雷陣雨 70% · 帶傘",
        )

    def test_taipei_detail_keeps_prose(self):
        day = extract_day(load_fixture(), parse_location("臺北市"), DAY)
        self.assertEqual(
            render_detail(day),
            "明天 9/19（六）臺北市：早上 6 點到中午 12 點晴時多雲，中午 12 點起午後短暫雷陣雨（降雨機率 70%），"
            "傍晚 6 點前結束，之後轉多雲。氣溫 25 到 33 度，體感最高 37 度。建議帶傘、注意防曬與補水。",
        )

    def test_sanchong_overnight_rain_no_umbrella_tip(self):
        day = extract_day(load_fixture(), parse_location("新北市/三重區"), DAY)
        self.assertEqual(render_compact(day), "⛅ 新北市三重區 25–32°\n凌晨有雨、整天多雲")

    def test_report_has_one_shared_header(self):
        days = [
            extract_day(load_fixture(), parse_location("臺北市"), DAY),
            extract_day(load_fixture(), parse_location("新北市/三重區"), DAY),
        ]
        report = render_report(days)
        self.assertTrue(report.startswith("明天 9/19（六）\n\n"))
        self.assertEqual(report.count("明天"), 1)

    def test_missing_day_raises(self):
        with self.assertRaises(RuntimeError):
            extract_day(load_fixture(), parse_location("臺北市"), date(2026, 10, 1))

    def test_unknown_location_raises(self):
        with self.assertRaises(RuntimeError):
            extract_day(load_fixture(), parse_location("新北市/板橋區"), DAY)


class CliTests(unittest.TestCase):
    SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "forecast.py")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, self.SCRIPT, *args], capture_output=True, text=True)

    def test_default_style_is_compact(self):
        result = self.run_cli("--fixture", FIXTURE, "--date", "2026-09-19")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [line for line in result.stdout.strip().splitlines() if line]
        self.assertEqual(lines[0], "明天 9/19（六）")
        self.assertEqual(lines[1], "⛈️ 臺北市 25–33°")
        self.assertEqual(lines[3], "⛅ 新北市三重區 25–32°")

    def test_bar_style_adds_the_timeline_row(self):
        result = self.run_cli("--fixture", FIXTURE, "--date", "2026-09-19", "--style", "bar")
        self.assertIn("06 ☀️☀️ 12 ⛈️⛈️ 18 ⛅⛅ 24", result.stdout)

    def test_detail_style_keeps_prose(self):
        result = self.run_cli("--fixture", FIXTURE, "--date", "2026-09-19", "--style", "detail")
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("明天 9/19（六）臺北市："))

    def test_json_output(self):
        result = self.run_cli("--fixture", FIXTURE, "--date", "2026-09-19", "--json", "臺北市")
        data = json.loads(result.stdout)
        self.assertEqual(data[0]["location"], "臺北市")
        self.assertEqual(data[0]["icon"], "⛈️")
        self.assertIn("detail", data[0])
        self.assertEqual(data[0]["segments"][2]["category"], "rain")

    def test_missing_api_key_is_a_clear_error(self):
        env = {k: v for k, v in os.environ.items() if k != "CWA_API_KEY"}
        result = subprocess.run([sys.executable, self.SCRIPT], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("CWA_API_KEY", result.stderr)


if __name__ == "__main__":
    unittest.main()
