import json
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from build_card import (  # noqa: E402
    build,
    fill_missing_temps,
    headline_category,
    mark_numbers,
    slot_category,
    to_card,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "sample.json")


def forecast_json():
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "forecast.py"),
         "--fixture", FIXTURE, "--date", "2026-09-19", "--json"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def slot(h, cat, t=25, pop=10):
    return {"h": h, "wx": "", "cat": cat, "pop": pop, "t": t}


class CategoryTests(unittest.TestCase):
    def test_thunder_is_split_off_rain(self):
        self.assertEqual(slot_category({"category": "rain", "weather": "多雲午後短暫雷陣雨"}), "thunder")
        self.assertEqual(slot_category({"category": "rain", "weather": "陰短暫雨"}), "rain")

    def test_non_rain_categories_pass_through(self):
        self.assertEqual(slot_category({"category": "overcast", "weather": "陰"}), "overcast")
        self.assertEqual(slot_category({"category": None, "weather": ""}), "cloudy")

    def test_headline_prefers_thunder_over_rain(self):
        slots = [slot(h, "cloudy") for h in range(0, 12, 3)]
        slots += [slot(12, "rain"), slot(15, "thunder"), slot(18, "cloudy"), slot(21, "cloudy")]
        self.assertEqual(headline_category(slots), "thunder")

    def test_headline_uses_rain_when_no_thunder(self):
        slots = [slot(h, "cloudy") for h in range(0, 12, 3)]
        slots += [slot(12, "rain"), slot(15, "cloudy"), slot(18, "cloudy"), slot(21, "cloudy")]
        self.assertEqual(headline_category(slots), "rain")

    def test_overnight_rain_does_not_take_the_headline(self):
        slots = [slot(0, "rain"), slot(3, "overcast")]
        slots += [slot(h, "cloudy") for h in range(6, 24, 3)]
        self.assertEqual(headline_category(slots), "cloudy")

    def test_dry_day_takes_the_longest_category(self):
        slots = [slot(h, "cloudy") for h in range(0, 12, 3)]
        slots += [slot(h, "sunny") for h in range(12, 24, 3)]
        self.assertEqual(headline_category(slots), "sunny")


class TemperatureTests(unittest.TestCase):
    def test_gaps_take_the_nearest_reading(self):
        slots = [slot(0, "cloudy", t=None), slot(3, "cloudy", t=26), slot(6, "cloudy", t=None)]
        fill_missing_temps(slots, 30)
        self.assertEqual([s["t"] for s in slots], [26, 26, 26])

    def test_all_missing_falls_back(self):
        slots = [slot(h, "cloudy", t=None) for h in (0, 3)]
        fill_missing_temps(slots, 31)
        self.assertEqual([s["t"] for s in slots], [31, 31])


class MarkupTests(unittest.TestCase):
    def test_numbers_get_the_mono_span(self):
        self.assertEqual(mark_numbers("12–18 時 70%"),
                         '<span class="num">12–18</span> 時 <span class="num">70</span>%')

    def test_text_is_escaped_before_wrapping(self):
        self.assertIn("&lt;b&gt;", mark_numbers("<b>3 時"))
        self.assertNotIn("<b>", mark_numbers("<b>3 時"))


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.entries = forecast_json()

    def test_page_has_no_placeholders_left(self):
        page = build(self.entries, sample=True)
        for marker in ("__TITLE__", "__ISSUED__", "__REPORT__"):
            self.assertNotIn(marker, page)

    def test_report_is_valid_json_with_both_locations(self):
        page = build(self.entries)
        raw = re.search(r"const REPORT = (\[[\s\S]*?\n\]);", page).group(1)
        report = json.loads(raw)
        self.assertEqual([r["name"] for r in report], ["臺北市", "新北市三重區"])
        self.assertEqual(report[0]["cat"], "thunder")
        self.assertEqual(report[0]["tmax"], 33)
        self.assertEqual(len(report[0]["slots"]), 8)
        self.assertTrue(all(s["t"] is not None for s in report[0]["slots"]))
        self.assertEqual(report[0]["tip"], "帶傘")
        self.assertIsNone(report[1]["tip"])

    def test_title_names_the_forecast_day_not_today(self):
        self.assertIn("明天 9/19", build(self.entries))

    def test_sample_badge_only_when_asked(self):
        self.assertIn("範例資料", build(self.entries, sample=True))
        self.assertNotIn("範例資料", build(self.entries))

    def test_partial_failure_is_shown_not_hidden(self):
        page = build(self.entries + [{"error": "彰化縣：取得預報失敗，連線逾時"}])
        self.assertIn("連線逾時", page)
        self.assertIn('class="warn"', page)

    def test_total_failure_refuses_to_build(self):
        with self.assertRaises(SystemExit):
            build([{"error": "全部失敗"}])

    def test_card_keeps_the_scripts_own_timing_line(self):
        card = to_card(self.entries[0])
        self.assertIn("短暫雷陣雨", card["line"])
        self.assertIn('<span class="num">12–18</span>', card["line"])


if __name__ == "__main__":
    unittest.main()
