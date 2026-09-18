# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A daily next-day weather forecast for Taiwan, rendered in Traditional Chinese and pushed
to the owner's phone at 18:00 Taiwan time by a Claude cloud Routine. Default locations
are 臺北市 and 新北市/三重區. Data comes from the Central Weather Administration (CWA)
Open Data 3-hourly township forecasts (dataset family F-D0047).

## Commands

Python 3.9+ standard library only; nothing to install.

```bash
export CWA_API_KEY=CWA-...                       # CWA open-data key, never committed
python3 forecast.py                              # default locations, tomorrow, compact
python3 forecast.py --style bar                  # compact plus an emoji timeline row
python3 forecast.py --style detail               # the long prose sentence
python3 forecast.py 彰化縣/彰化市 --date 2026-09-20 --json
python3 forecast.py --fixture tests/fixtures/sample.json --date 2026-09-19   # offline run

python3 forecast.py --json | python3 build_card.py -o build/card.html        # web card

python3 -m unittest discover -s tests -v                                     # all tests
python3 -m unittest tests.test_forecast.WordingTests -v                      # one class
python3 -m unittest tests.test_forecast.FixtureTests.test_taipei_narrative   # one test
```

The sandbox and the default Routine environment cannot reach `opendata.cwa.gov.tw`;
develop against the fixture and only verify live calls where that domain is allowed.

## Architecture

Everything lives in `forecast.py`, in four stages that are kept separate on purpose:

1. **Location → dataset.** `parse_location` accepts `縣市` or `縣市/鄉鎮區` (台 is
   normalized to 臺). A district uses that county's own dataset from `COUNTY_DATASETS`
   (queried with `LocationName=<district>`); a bare county uses the county-level dataset
   `F-D0047-089`. Dataset IDs are the 3-hourly ones; the weekly datasets are not used.
2. **Fetch and extract.** `fetch_dataset` calls the CWA REST API; `extract_day` reads the
   new-format payload (`records.Locations[].Location[].WeatherElement[]`, Chinese
   `ElementName`s such as 天氣現象 / 3小時降雨機率 / 溫度) and keeps only the slots that
   fall on the target date, as `Period` objects.
3. **Deterministic segmentation.** `segment_periods` merges consecutive 3-hour periods
   with the same coarse category (`rain` / `sunny` / `cloudy` / `overcast`). A period is
   rain if its weather phrase contains 雨 or PoP ≥ `RAIN_POP_THRESHOLD`. This is where
   "when the rain starts" is decided; the wording layer never infers it.
4. **Rendering, in three styles off the same segments.** `compact` (default, what the
   push carries) is two lines per location: a headline glyph from `ICONS`, the name and
   temperature range, then `compact_timing` — a 24-hour window like `12–18 時` plus one
   action tip. `bar` inserts `emoji_bar`, a six-slot strip with ticks at 06/12/18/24.
   `detail` is the original prose from `describe_segments`, which uses the spoken hour
   phrases in `hour_phrase`. `render_report` puts one shared date header above the
   compact styles; detail repeats the date per line because it reads as prose.
   Overnight (00–06) rain is reported separately in every style so the day's own
   description stays clean, and it never triggers the umbrella tip.

`tests/fixtures/sample.json` is a hand-built payload in the CWA format covering
2026-09-19 for both default locations; `FixtureTests` pin the exact output strings, so
any wording change must update those expectations deliberately.

## The web card

`card/template.html` is the page; `build_card.py` fills its three markers (`__TITLE__`,
`__ISSUED__`, `__REPORT__`) from `forecast.py --json` and writes a standalone file. The
split is deliberate: `forecast.py` decides what the weather is, `build_card.py` decides
how it looks. Picking the pictogram (including splitting thunder off rain), the English
subtitle, and the mono-wrapped numerals all live in the builder, so the forecast stays
free of presentation concerns.

The page draws three tracks per location on one shared 3-hour x axis: condition icons,
precipitation-probability bars against the same `RAIN_POP_THRESHOLD` dashed line the
script uses, and a temperature line. Colors are CSS tokens defined for light and dark;
the accent pair was checked with the dataviz palette validator, so changing `--rain`,
`--sun` or `--temp` means re-running it. Icons are inlined `<g>` markup rather than
`<symbol>`/`<use>`, which clipped at these sizes.

`build_card.py` refuses to write a page when every location failed, and shows a partial
failure as a chip on the page instead of quietly dropping the location.

## Scheduling

The Routine "每日明天天氣預報 18:00" (cron `0 10 * * *` UTC, fresh cloud session, push
notification on completion) runs the prompt in `routine/PROMPT.md`: fetch, build the
card, update the artifact at its fixed URL in place, then push the compact text plus
that link. The artifact URL must never change, so the prompt reads it before publishing
and passes it as `url`. Editing that file
does not update the Routine; change it at claude.ai/code/routines or via `/schedule
update`, then mirror the change here. The Routine environment must allow
`opendata.cwa.gov.tw` and provide `CWA_API_KEY`.

## Conventions

- User-facing text is Traditional Chinese (zh-TW); code, identifiers, and commit
  messages are English.
- Never state finer time resolution than the 3-hour data supports.
- The push is the constrained surface: keep `compact` to two lines per location and one
  tip. New information belongs in `bar` or `detail`, not in the push.
- The script must fail loudly (non-zero exit, message on stderr) rather than emit a
  forecast it could not fetch; the Routine relies on that to avoid fabricating weather.
