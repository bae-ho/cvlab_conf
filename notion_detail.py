# notion_detail.py
# 컨퍼런스 페이지 본문에 들어가는 "상세 정보" 섹션(블록)을 만들고 동기화하는 로직.
#
# 본문 전체를 덮어쓰면 사람이 페이지에 적어둔 메모까지 날아가므로, 스크립트가 관리하는
# 영역을 콜아웃 블록 하나로 한정한다. 콜아웃 텍스트가 _MARKER로 시작하는 블록만 찾아서
# 그 안의 children만 교체하고, 콜아웃 바깥 내용은 절대 건드리지 않는다.
# 콜아웃 텍스트 끝에 내용 해시를 적어두고, 해시가 같으면(사이트 내용 변화 없음) API 호출을
# 생략한다 — 매 동기화마다 모든 페이지의 블록을 지웠다 다시 쓰지 않기 위함.
import hashlib
import json

from parsers.date_parser import parse_date_range, parse_single_date
from notion_client import (
    notion_list_children,
    notion_append_children,
    notion_update_block,
    notion_delete_block,
)

_MARKER = "VisionBib 자동 동기화 정보"
_PLACEHOLDER_VENUE = "Conference Venue"
_MAX_TEXT = 2000  # Notion rich_text 한 조각 최대 길이


def _text(content, url=None, bold=False, color=None):
    content = (content or "")[:_MAX_TEXT]
    rt = {"type": "text", "text": {"content": content}}
    if url:
        rt["text"]["link"] = {"url": url}
    annotations = {}
    if bold:
        annotations["bold"] = True
    if color:
        annotations["color"] = color
    if annotations:
        rt["annotations"] = annotations
    return rt


def _date_mention(start, end=None):
    date = {"start": start}
    if end:
        date["end"] = end
    return {"type": "mention", "mention": {"type": "date", "date": date}}


def _date_rich(raw_text, range_=False):
    """날짜 텍스트를 파싱되면 Notion 날짜 멘션으로, 안 되면 원문 텍스트로."""
    if not raw_text:
        return [_text("미정", color="gray")]
    if range_:
        start, end = parse_date_range(raw_text)
    else:
        start, end = parse_single_date(raw_text), None
    if start:
        return [_date_mention(start, end)]
    return [_text(raw_text)]


def _heading(text):
    return {"type": "heading_3", "heading_3": {"rich_text": [_text(text)]}}


def _bullet(label, rich):
    return {"type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [_text(f"{label}: ", bold=True)] + rich}}


def _paragraph(rich):
    return {"type": "paragraph", "paragraph": {"rich_text": rich}}


def _table(header, rows):
    def row(cells):
        return {"type": "table_row", "table_row": {"cells": cells}}
    return {
        "type": "table",
        "table": {
            "table_width": len(header),
            "has_column_header": True,
            "has_row_header": False,
            "children": [row([[_text(h, bold=True)] for h in header])] + [row(r) for r in rows],
        },
    }


def build_detail_blocks(item):
    blocks = [_heading("📌 기본 정보")]
    blocks.append(_bullet("정식 명칭", [_text(item.get("name") or "-")]))
    blocks.append(_bullet("약어", [_text(f"{item['acronym']} {item['year']}")]))
    blocks.append(_bullet("개최 기간", _date_rich(item.get("dates"), range_=True)))
    blocks.append(_bullet("장소", [_text(item.get("location") or "-")]))
    venue = item.get("venue")
    if venue and venue != _PLACEHOLDER_VENUE:
        blocks.append(_bullet("행사장", [_text(venue)]))

    blocks.append(_heading("⏰ 메인 논문 마감"))
    deadline_rich = _date_rich(item.get("paper_deadline"))
    if item.get("deadline_note"):
        deadline_rich.append(_text(f"  ({item['deadline_note']})", color="gray"))
    blocks.append(_bullet("Paper deadline", deadline_rich))

    blocks.append(_heading("🔗 링크"))
    links = [
        ("공식 홈페이지", item.get("homepage_url")),
        ("Call for Papers", item.get("cfp_url") if item.get("cfp_url") and "Nocall" not in item["cfp_url"] else None),
        ("VisionBib 원문", item.get("source_url")),
    ]
    for label, url in links:
        blocks.append(_bullet(label, [_text(url, url=url)] if url else [_text("없음", color="gray")]))

    sub_events = item.get("sub_events") or []
    blocks.append(_heading(f"🧩 워크샵 · 챌린지 · 추가 마감 ({len(sub_events)})"))
    if not sub_events:
        blocks.append(_paragraph([_text("VisionBib에 등록된 추가 일정이 없습니다.", color="gray")]))
    else:
        rows = []
        for ev in sub_events:
            deadline_cell = []
            if ev.get("deadline_label"):
                deadline_cell.append(_text(f"{ev['deadline_label']}: ", color="gray"))
            deadline_cell += _date_rich(ev.get("deadline"))
            rows.append([
                [_text(ev.get("dates") or "-")],
                [_text(ev["title"], url=ev.get("url"))],
                deadline_cell,
                [_text(ev["deadline_note"])] if ev.get("deadline_note") else [],
                [_text(ev.get("cfp_label") or "CFP", url=ev["cfp_url"])] if ev.get("cfp_url") else [],
            ])
        blocks.append(_table(["날짜", "이름", "마감", "비고", "CFP"], rows))
    return blocks


def _callout_text(content_hash):
    return [
        _text(_MARKER, bold=True),
        _text(" — 이 박스 안 내용은 동기화 때마다 새로 덮어써집니다. 메모는 박스 바깥에 적어주세요. ",
              color="gray"),
        _text(f"[{content_hash}]", color="gray"),
    ]


def _content_hash(blocks):
    return hashlib.sha1(json.dumps(blocks, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]


def _find_managed_callout(page_id):
    for block in notion_list_children(page_id):
        if block.get("type") != "callout":
            continue
        plain = "".join(rt.get("plain_text", "") for rt in block["callout"].get("rich_text", []))
        if plain.startswith(_MARKER):
            return block, plain
    return None, None


def sync_detail_section(page_id, item, dry_run=True):
    blocks = build_detail_blocks(item)
    content_hash = _content_hash(blocks)

    if dry_run:
        print(f"[dry-run] detail section: {len(blocks)} blocks, "
              f"{len(item.get('sub_events') or [])} sub-events, hash={content_hash}")
        return

    callout, plain = _find_managed_callout(page_id) if page_id else (None, None)
    if callout and f"[{content_hash}]" in plain:
        return  # 변경 없음

    if callout is None:
        callout = notion_append_children(page_id, [{
            "type": "callout",
            "callout": {"rich_text": _callout_text(content_hash), "icon": {"type": "emoji", "emoji": "📋"},
                        "color": "gray_background"},
        }])[0]
    else:
        for child in notion_list_children(callout["id"]):
            notion_delete_block(child["id"])
        notion_update_block(callout["id"], {"callout": {"rich_text": _callout_text(content_hash)}})

    notion_append_children(callout["id"], blocks)
    print(f"[detail] {item['acronym']}-{item['year']} 상세 섹션 갱신 ({content_hash})")
