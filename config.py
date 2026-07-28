import os
import requests

# =========================
# Config
# =========================
VISIONBIB_URL = "http://conferences.visionbib.com/Iris-Conferences.html"

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "").strip()
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2022-06-28").strip()

if not NOTION_TOKEN or not NOTION_DATABASE_ID:
    raise RuntimeError(
        "NOTION_TOKEN / NOTION_DATABASE_ID 환경변수가 설정되어 있지 않습니다. "
        "예전에 여기 하드코딩되어 있던 값은 유출된 것으로 간주하고 제거했으니, "
        "Notion에서 integration 토큰을 재발급받아 환경변수로 넘겨주세요."
    )

NOTION_API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
    "User-Agent": "visionbib-notion-sync/3.0",
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (visionbib-notion-sync/3.0)"})
