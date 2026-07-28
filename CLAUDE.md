# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A scraper/sync tool that pulls computer vision conference listings from VisionBib
(`http://conferences.visionbib.com/Iris-Conferences.html`) and pushes them into a Notion database. It
scrapes one `<table>` per conference (grouped under a per-year anchor — see Architecture below),
extracts fields (acronym, name, location, venue, dates, paper deadline, CFP link) via regex/BeautifulSoup,
and upserts each conference as a page in a Notion database keyed by a `UID` property (`ACRONYM-YEAR`,
e.g. `ICMI-2026`).

This is a git repository with a GitHub remote (`bae-ho/cvlab_conf`) and a scheduled GitHub Actions
workflow (see below) — check `git log` for recent history instead of relying on this file alone.

## Environment / running the code

- `requirements.txt` lists the deps: `requests`, `beautifulsoup4` (`bs4`), `html5lib`.
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
- **`NOTION_TOKEN` and `NOTION_DATABASE_ID` env vars are required** — `config.py` raises `RuntimeError`
  at import time if either is missing/empty. There is no hardcoded fallback (one used to exist and was
  removed after being treated as a leaked credential — don't reintroduce a hardcoded default).
- Run the scraper standalone (prints the first few parsed rows for 2026, no Notion calls):
  ```
  python visionbib_fetch.py
  ```
- Run the sync driver:
  ```
  python sync.py              # dry-run preview only (default), today through end of next year
  python sync.py --live       # actually create/update Notion pages
  python sync.py --no-push    # console output only, no Notion calls at all (no token needed... but
                               # config.py still requires the env vars to be *set*, even if unused here)
  ```
- There is no test suite and no lint/formatter config in this repo. `pyflakes` was used ad hoc to check
  for dead imports during cleanup but isn't wired in as a standing check.

## Configuration (`config.py`)

Reads `NOTION_TOKEN`, `NOTION_DATABASE_ID`, `NOTION_VERSION` from environment variables. The first two
have no default and raise `RuntimeError` if unset (see above); `NOTION_VERSION` defaults to
`"2022-06-28"`. Also builds the shared `requests.Session()` (`SESSION`, with a custom `Mozilla/5.0`-style
`User-Agent` — needed because at least one external CFP site 403s the default `python-requests` UA) and
the Notion request `HEADERS` used by `notion_client.py`.

## Architecture / data flow

```
visionbib_fetch.py  --iter_conference_rows(year)-->  dict per conference
        |
        v
   sync.py (run())  -- fetches per year, groups by month, filters to upcoming --
        |
        v
   notion_sync.py (push_to_notion())  -- maps dict -> Notion properties, upserts by UID --
        |
        v
   notion_client.py -- thin Notion API wrapper
```

- **`visionbib_fetch.py`**: The VisionBib page does **not** have a per-month table. The real structure:
  each year has an anchor table (`<a name="2026">`), and every conference for that year is its own
  separate `<table>` in a flat sequence immediately after it, up to the next year's anchor table (found
  via `_find_year_table_range()`). The month-by-month calendar tables (anchors like `#2026T`) are just a
  summary grid, not a source of per-conference detail. Within one conference's `<table>`,
  `_parse_conference_table()` reads `find_all("td")` **recursively in document order** (not by `<tr>` —
  the row nesting itself is unreliable) and relies on a fixed-position layout that held for every
  conference checked: `td[0]`="ACRONYM YEAR", `td[1]`=full name, `td[2]`=location, `td[3]`=venue (often
  the literal string `"Conference Venue"`, sometimes an actual venue name — never a link). `td[4:7]` =
  (dates, paper-deadline text, CFP-link cell) for the *main* conference entry. Conferences with attached
  workshops/extra deadlines repeat more `(dates, deadline, cfp)` triples after `td[6]` — these are
  intentionally **ignored** (only the first triple is parsed) to keep one row = one conference, matching
  the `UID` design; the full cell text is still kept per-item in `raw_blocks`. `iter_conference_rows(year)`
  fetches and parses one whole year per call; there is no `month` parameter — `sync.py` filters by month.
  When the main listing has no deadline, `_fallback_deadline_from_cfp()` tries fetching the CFP link and
  scraping a `"Paper submission: <date>"` line — but **only** when the link is same-domain
  (`conferences.visionbib.com`); external conference sites (arbitrary structure, some block scrapers) are
  deliberately not attempted.
- **`parsers/`** (`date_parser.py`, `deadline_parser.py`): regex helpers, the single source of truth for
  month names (`MONTH_NAMES`/`MONTHS` in `date_parser.py` — `deadline_parser.py` imports `MONTHS` from
  here rather than redefining it). `date_parser.py` also has `parse_date_range()`/`parse_single_date()`
  (free-text date → ISO, handles several date-range spellings the site uses) and `month_of()` (date text →
  month number, used for bucketing). `location_parser.py` and `text_utils.py` used to exist here but were
  unused dead code and were deleted — location doesn't need parsing since VisionBib already puts it in its
  own table cell.
- **`notion_client.py`**: thin wrapper around the Notion API (`notion_get_database`,
  `notion_get_title_property_name`, `notion_query_by_uid`, `notion_create_page`, `notion_update_page`,
  plus property-builder helpers `notion_title`/`notion_rich_text`/`notion_date`). No business logic here.
- **`notion_sync.py`**: maps a scraped conference dict to Notion properties (`build_notion_properties()`)
  and upserts by UID (`push_to_notion()`, query-then-create-or-update). The actual DB property names are
  Korean (`장소`, `데드라인`, `날짜`, `년도`, `링크`) mixed with English (`Acronym`, `UID`, `Source`) —
  matches whatever the live Notion database happens to use; the title property name is looked up
  dynamically via `notion_get_title_property_name()` rather than assumed. Title itself is set to
  `UID.replace("-", "")` (e.g. `"ICMI2026"`), not the full conference name. **Important behavior**: if the
  freshly-scraped `paper_deadline` is `None` but the existing Notion page already has a non-null 데드라인,
  `push_to_notion()` deliberately skips overwriting that field — this exists because some deadlines get
  filled in manually (e.g. found in a PDF on an external conference site) and a routine re-sync should
  never silently blank those back out.
- **`sync.py`**: thin entry point/orchestrator only — `run(year, years_ahead, months, limit_per_month,
  push, dry_run, only_upcoming)` fetches `iter_conference_rows` for `year` through `year + years_ahead`
  (default: this year + next year — VisionBib has very little data beyond that), buckets by
  `(year, month)`, filters out anything before today when `only_upcoming` (default `True`), prints each
  item, and calls `notion_sync.push_to_notion()` per item when `push=True`. CLI (`__main__`): `--live`
  actually writes to Notion, `--no-push` skips Notion entirely (console only); default is push=True with
  dry_run=True (preview only, no writes).

## GitHub Actions (`.github/workflows/sync.yml`)

Runs `python sync.py --live` daily at 00:00 UTC (plus manual `workflow_dispatch`), installing from
`requirements.txt` on `ubuntu-latest` / Python 3.12. `NOTION_TOKEN` and `NOTION_DATABASE_ID` are read from
repo Secrets (Settings → Secrets and variables → Actions) — **never hardcode them here or in `config.py`**.

## Known data-quality caveats (source site issues, not scraper bugs)

- Some paper-deadline dates on VisionBib are themselves malformed (e.g. one 2026 SMC entry read
  `wrDate('April 192, 2026')` — an invalid day, apparently "19" + "2026" mashed together; the actual date,
  confirmed from the conference's own CFP PDF, was April 19, 2026). The scraper correctly returns `None`
  rather than guessing at a broken date.
- Deadlines hosted only on external conference websites (not `conferences.visionbib.com`) are not
  auto-scraped (see `_fallback_deadline_from_cfp()` above) — if needed, fetch the CFP page manually and
  either eyeball it or (if a PDF) read it directly, then patch the Notion page's 데드라인 property once;
  `push_to_notion()`'s preserve-existing-value behavior means later automated re-syncs won't clobber it.
