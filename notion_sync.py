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
        "링크": {"url": item.get("homepage_url")},
    }


# 스크래핑 결과가 비어있어도(None) 이미 Notion에 채워져 있는 값은 지우지 않고
# 보존할 프로퍼티들. {프로퍼티 이름: 값이 들어있는 내부 키}.
# (예: SMC 데드라인을 CFP PDF 보고 수동 입력, MIPR 링크를 웹검색으로 수동 입력 —
# 소스 사이트 쪽 데이터가 깨져있어(wrDate 오타, href="None.html") 자동으로는 못
# 채우는 값들이 재동기화 때마다 빈 값으로 덮어써지지 않게 함.)
_PRESERVE_IF_MISSING = {
    "데드라인": "date",
    "링크": "url",
}


def push_to_notion(item, title_prop, dry_run=True):
    uid = make_uid(item)
    properties = build_notion_properties(item, title_prop)
    existing = notion_query_by_uid(uid)

    if existing:
        existing_props = existing[0]["properties"]
        for prop_name, value_key in _PRESERVE_IF_MISSING.items():
            if properties[prop_name].get(value_key) is not None:
                continue
            prev_value = existing_props.get(prop_name, {}).get(value_key)
            if prev_value:
                del properties[prop_name]

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
