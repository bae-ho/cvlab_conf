# notion_client.py
from config import SESSION, NOTION_API, NOTION_DATABASE_ID, HEADERS

def _req_ok(resp, msg: str):
    if not resp.ok:
        raise RuntimeError(f"{msg}\nstatus={resp.status_code}\nbody={resp.text}")

def notion_get_database():
    r = SESSION.get(f"{NOTION_API}/databases/{NOTION_DATABASE_ID}", headers=HEADERS, timeout=30)
    _req_ok(r, "Notion DB get failed")
    return r.json()

def notion_get_title_property_name() -> str:
    db = notion_get_database()
    for name, info in db.get("properties", {}).items():
        if info.get("type") == "title":
            return name
    raise RuntimeError("DB에서 title 타입 프로퍼티를 찾지 못했습니다.")

def notion_query_by_uid(uid: str):
    payload = {"filter": {"property": "UID", "rich_text": {"equals": uid}}, "page_size": 1}
    r = SESSION.post(f"{NOTION_API}/databases/{NOTION_DATABASE_ID}/query", headers=HEADERS, json=payload, timeout=30)
    _req_ok(r, "Notion query failed")
    return r.json().get("results", [])

def notion_create_page(properties: dict):
    payload = {"parent": {"database_id": NOTION_DATABASE_ID}, "properties": properties}
    r = SESSION.post(f"{NOTION_API}/pages", headers=HEADERS, json=payload, timeout=30)
    _req_ok(r, "Notion create failed")
    return r.json()

def notion_update_page(page_id: str, properties: dict):
    payload = {"properties": properties}
    r = SESSION.patch(f"{NOTION_API}/pages/{page_id}", headers=HEADERS, json=payload, timeout=30)
    _req_ok(r, "Notion update failed")
    return r.json()

def notion_title(value: str):
    return {"title": [{"text": {"content": value}}]}

def notion_rich_text(value: str | None):
    if not value:
        return {"rich_text": []}
    return {"rich_text": [{"text": {"content": value}}]}

def notion_date(start_iso: str | None, end_iso: str | None = None):
    if not start_iso:
        return {"date": None}
    obj = {"start": start_iso}
    if end_iso:
        obj["end"] = end_iso
    return {"date": obj}
