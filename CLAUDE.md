# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A scraper/sync tool that pulls computer vision conference listings from VisionBib
(`http://conferences.visionbib.com/Iris-Conferences.html`) and is meant to push them into a Notion
database. It scrapes one `<table>` per conference (grouped under a per-year anchor — see Architecture
below), extracts fields (acronym, name, location, venue, dates, paper deadline, CFP link) via
regex/BeautifulSoup, and (eventually) upserts each conference as a page in a Notion database keyed by a
`UID` property.

This is not a git repository — there is no commit history to inspect for context.

## Environment / running the code

- `requirements.txt` lists the deps: `requests`, `beautifulsoup4` (`bs4`), `html5lib`, `pytz`.
  **`html5lib` is required, not optional** — the VisionBib page has malformed `<td>`/`<tr>` nesting
  (unclosed tags), and BeautifulSoup's default `html.parser` mis-nests the table cells as a result
  (cells end up nested inside each other instead of siblings). Only `html5lib` (which implements the
  real HTML5 parsing/error-recovery algorithm) produces the flat, correctly-ordered cell structure the
  scraper depends on; `lxml` was also tried and rejected because it silently drops the conference's
  deadline date (which lives inside a `<script>wrDate('...')</script>` call inside a `<td>` — `html5lib`
  includes script text when walking `td.stripped_strings`, `lxml` does not).
- The `.venv/` in this repo is a **Windows** virtualenv (Python 3.14, `Scripts/` + `.pyd` files) and is
  not usable on Linux. On this machine, use the active `notion` conda environment instead
  (`/home/cvlab/anaconda3/envs/notion`); install deps there with `pip install -r requirements.txt`.
- Run the scraper standalone (prints the first few parsed rows for 2026, no Notion calls):
  ```
  python visionbib_fetch.py
  ```
- Run the sync driver (currently just fetches + pretty-prints rows for a given year/months; see
  "In-progress state" below):
  ```
  python sync.py
  ```
- There is no test suite and no lint/formatter config in this repo.

## Configuration (`config.py`)

Reads `NOTION_TOKEN`, `NOTION_DATABASE_ID`, `NOTION_VERSION`, `MIN_YEAR`, `MAX_YEAR` from environment
variables, each with a hardcoded fallback default. **The fallback values for `NOTION_TOKEN` and
`NOTION_DATABASE_ID` are live-looking credentials committed in plaintext** — treat them as compromised,
prefer setting real values via env vars, and don't propagate the hardcoded fallbacks into new code.

`config.py` also builds the shared `requests.Session()` (`SESSION`) and Notion request `HEADERS` used
by `notion_client.py`, and defines `AOE_TZ` (Anywhere-on-Earth, UTC-12) for deadline comparisons.

## Architecture / data flow

```
visionbib_fetch.py  --iter_conference_rows(year)-->  dict per conference
        |
        v
   sync.py (run())  -- fetches once per year, groups by month, prints each dict --
        |
        v (not yet implemented)
   notion_client.py -- create/update Notion pages, keyed by UID
```

- **`visionbib_fetch.py`**: The VisionBib page does **not** have a per-month table — that assumption in
  earlier versions of this scraper was wrong and made every run fail with `RuntimeError`. The real
  structure: each year has an anchor table (`<a name="2026">`), and every conference for that year is its
  own separate `<table>` in a flat sequence immediately after it, up to the next year's anchor table
  (found via `_find_year_table_range()`). The month-by-month calendar tables (anchors like `#2026T`) are
  just a summary grid, not a source of per-conference detail. Within one conference's `<table>`,
  `_parse_conference_table()` reads `find_all("td")` **recursively in document order** (not by `<tr>` —
  the row nesting itself is unreliable) and relies on a fixed-position layout that held for every
  conference checked: `td[0]`="ACRONYM YEAR", `td[1]`=full name, `td[2]`=location, `td[3]`=venue (often
  the literal string `"Conference Venue"`, sometimes an actual venue name — never a link, so there's no
  `venue_url` to extract), then `td[4:7]`=(dates, paper-deadline text, CFP-link cell) for the *main*
  conference entry. Conferences with attached workshops/extra deadlines repeat more `(dates, deadline,
  cfp)` triples after `td[6]` — these are intentionally **ignored** (only the first triple is parsed) to
  keep one row = one conference, matching the `UID` design; the full cell text is still kept per-item in
  `raw_blocks` if that extra detail is ever needed. Date/deadline extraction now reuses the `parsers/`
  package (see below) instead of inline regex. `iter_conference_rows(year)` fetches and parses the whole
  year in one request; there is no `month` parameter anymore — `sync.py` filters by month itself.
- **`parsers/`** (`date_parser.py`, `deadline_parser.py`, `location_parser.py`, `text_utils.py`): regex
  helpers for extracting dates, deadlines, and locations from text. `visionbib_fetch.py` now imports
  `extract_conference_date` and `extract_deadline_date_from_cells` from this package (previously unused).
  `location_parser.py` and `text_utils.py` are still not imported anywhere.
- **`notion_client.py`**: thin wrapper around the Notion API (`notion_get_database`,
  `notion_query_by_uid`, `notion_create_page`, `notion_update_page`, plus property-builder helpers
  `notion_title`/`notion_rich_text`/`notion_date`). **Not currently called from `sync.py`** — the
  create/update-by-UID sync loop still needs to be wired up.
- **`sync.py`**: entry point (`run(year, months, limit_per_month)`); fetches `iter_conference_rows(year)`
  once, buckets items by month using each item's `dates` text (`_month_of()`, first matched month name
  wins — a conference spanning two months like "September 28, 2026-October 1, 2026" is bucketed under
  September), then prints results per requested month for inspection/debugging. The `__main__` block is
  hardcoded to a small test run (`year=2026, months=[10], limit_per_month=10`) with the full-year run
  commented out.

## In-progress state (read before extending)

The Notion-push half of the pipeline is not wired in yet: `sync.py` doesn't call anything in
`notion_client.py`. If asked to "finish the sync," the missing piece is connecting `sync.py`'s loop to
`notion_client.py` (using `UID` — likely the acronym + year/date — to query-then-create-or-update pages).

Known data-quality caveat inherited from the source site: some paper-deadline dates on VisionBib are
themselves malformed (e.g. one 2026 entry literally reads `wrDate('April 192, 2026')` — an invalid day),
so `paper_deadline` will correctly come back `None` for those rather than a wrong date; this is a source
data bug, not a scraper bug.
