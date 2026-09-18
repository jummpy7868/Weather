# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

The repository is a fresh scaffold: it contains only `README.md` ("# Weather") and no
source code, build system, tests, or CI. There are no commands to run yet.

## Intended purpose

The owner wants a daily weather-forecast assistant that runs through the Claude mobile
app: every evening (target 18:00 Taiwan time) Claude prompts for a location, then
replies with a plain-language forecast for the next day in Traditional Chinese, for
example "明天 9/19 彰化白天晴天，中午 12 點後開始下雷陣雨，下午 4 點後停雨".

Design notes gathered so far live in the session history, not in this repo. When code is
added, update this file with:

- the language/runtime and how to install dependencies
- how to run the forecast fetcher locally and how to run a single test
- which weather data source is used (Taiwan CWA Open Data is the leading candidate) and
  where the API key is expected to come from (environment variable, never committed)
- how the daily schedule is triggered (Claude Routine, GitHub Actions cron, or similar)

## Conventions

- User-facing text is Traditional Chinese (zh-TW); code, identifiers, and commit
  messages are English.
- Forecast wording should describe the day as a timeline (morning / from HH:00 / until
  HH:00) rather than dumping raw hourly numbers.
