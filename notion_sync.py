# notion_sync.py
# VisionBib에서 뽑은 conference dict를 Notion 페이지 속성으로 매핑하고 upsert하는 로직.
from parsers.date_parser import parse_date_range, parse_single_date
from notion_client import (
    notion_query_by_uid,
    notion_create_page,
    notion_update_page,
    notion_title,
    notion_rich_text,
    notion_date,
)


def make_uid(item):
    return f"{item['acronym']}-{item['year']}"


def build_notion_properties(item, title_prop):
    start, end = parse_date_range(item.get("dates"))
    deadline = parse_single_date(item.get("paper_deadline"))

    return {
        # "22nd International Conference..." 같은 정식명 대신 "CVPR2026" 형태로.
        title_prop: notion_title(make_uid(item).replace("-", "")),
        "Acronym": notion_rich_text(item.get("acronym")),
        "장소": notion_rich_text(item.get("location")),
        "UID": notion_rich_text(make_uid(item)),
        "년도": {"number": int(item["year"])},
        "날짜": notion_date(start, end),
        "데드라인": notion_date(deadline),
        "Source": {"url": item.get("source_url")},
        "링크": {"url": item.get("cfp_url")},
    }


def push_to_notion(item, title_prop, dry_run=True):
    uid = make_uid(item)
    properties = build_notion_properties(item, title_prop)
    existing = notion_query_by_uid(uid)

    if existing and properties["데드라인"]["date"] is None:
        prev_deadline = existing[0]["properties"].get("데드라인", {}).get("date")
        if prev_deadline:
            # 스크래핑으로 못 찾은 마감일(None)로, 이미 수동/이전에 채워둔 값을
            # 지워버리지 않도록 보존. (예: 외부 CFP 사이트 PDF 보고 수동 입력한 값)
            del properties["데드라인"]

    if dry_run:
        action = "update" if existing else "create"
        print(f"[dry-run] would {action} UID={uid}: {properties}")
        return

    if existing:
        notion_update_page(existing[0]["id"], properties)
        print(f"[updated] {uid}")
    else:
        notion_create_page(properties)
        print(f"[created] {uid}")
