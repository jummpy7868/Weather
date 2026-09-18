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
python3 forecast.py                              # default locations, tomorrow
python3 forecast.py 彰化縣/彰化市 --date 2026-09-20 --json
python3 forecast.py --fixture tests/fixtures/sample.json --date 2026-09-19   # offline run

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
4. **Rendering.** `describe_segments` writes the timeline sentence using only 3-hour
   grid phrases from `hour_phrase` (中午 12 點, 下午 3 點, 傍晚 6 點 …). Overnight
   (00–06) rain is mentioned separately so the sentence stays about the day.
   `render` adds temperature range, apparent-temperature note, and at most two tips.

`tests/fixtures/sample.json` is a hand-built payload in the CWA format covering
2026-09-19 for both default locations; `FixtureTests` pin the exact output strings, so
any wording change must update those expectations deliberately.

## Scheduling

The Routine "每日明天天氣預報 18:00" (cron `0 10 * * *` UTC, fresh cloud session, push
notification on completion) runs the prompt in `routine/PROMPT.md`. Editing that file
does not update the Routine; change it at claude.ai/code/routines or via `/schedule
update`, then mirror the change here. The Routine environment must allow
`opendata.cwa.gov.tw` and provide `CWA_API_KEY`.

## Conventions

- User-facing text is Traditional Chinese (zh-TW); code, identifiers, and commit
  messages are English.
- Never state finer time resolution than the 3-hour data supports.
- The script must fail loudly (non-zero exit, message on stderr) rather than emit a
  forecast it could not fetch; the Routine relies on that to avoid fabricating weather.
