# visionbib_fetch.py
import re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from config import SESSION, VISIONBIB_URL
from parsers.date_parser import DATE_RE, MONTHS as MONTH_ALT
from parsers.deadline_parser import extract_deadline_date_from_cells

# 사이트 구조: <a name="2026">2026</a> 앵커가 달린 table 뒤로 그 해의 컨퍼런스가
# 하나씩 별도 <table>로 쭉 나열됨 (월별 table은 존재하지 않음 — 캘린더 그리드
# table(#2026T 등)은 요약용이고 실제 상세 정보가 아님).
YEAR_ANCHOR_RE = re.compile(r"^\d{4}$")

# "ICMI 2026" -> ("ICMI", "2026"), "IEEE ISC2 2026" -> ("IEEE ISC2", "2026")
ACRONYM_YEAR_RE = re.compile(r"^(.*\S)\s+(\d{4})$")


def _cell_text(td):
    return " ".join(td.stripped_strings).strip()


_CFP_DEADLINE_LINE_RE = re.compile(r"Paper submission[:\s]*([^\n<]+)", re.I)
# CFP 상세페이지는 "7 September 2026"(D Month YYYY) 순서를 흔히 씀.
_DMY_DATE_RE = re.compile(rf"\d{{1,2}}\s+(?:{MONTH_ALT})\s+\d{{4}}")
_VISIONBIB_HOST = urlparse(VISIONBIB_URL).netloc


def _fallback_deadline_from_cfp(cfp_url):
    """메인 목록 page에 마감일이 없을 때, 같은 도메인(conferences.visionbib.com)
    CFP 상세페이지를 열어 "Paper submission: <date>" 줄에서 재시도. 외부 사이트는
    포맷이 제각각이라 시도하지 않고 None.

    다른 conference의 paper_deadline과 동일하게 "raw 날짜 텍스트"를 반환한다
    (ISO로 미리 변환하지 않음) — 호출부에서 항상 parse_single_date()로 한 번만
    변환하는 계약을 지키기 위함."""
    if not cfp_url or "Nocall" in cfp_url:
        return None
    if urlparse(cfp_url).netloc != _VISIONBIB_HOST:
        return None

    try:
        resp = SESSION.get(cfp_url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    m = _CFP_DEADLINE_LINE_RE.search(resp.text)
    if not m:
        return None
    line = m.group(1)

    date_m = _DMY_DATE_RE.search(line) or DATE_RE.search(line)
    return date_m.group(0) if date_m else None


def _find_year_table_range(tables, year: int):
    """연도 앵커 table의 인덱스를 찾아, 그 다음 연도 앵커 table 전까지의
    (start, end) 범위를 반환. 못 찾으면 None."""
    markers = []
    for idx, t in enumerate(tables):
        for a in t.find_all("a", attrs={"name": True}):
            if YEAR_ANCHOR_RE.match(a["name"]):
                markers.append((idx, a["name"]))
                break

    year_str = str(year)
    for i, (idx, name) in enumerate(markers):
        if name == year_str:
            start = idx + 1
            end = markers[i + 1][0] if i + 1 < len(markers) else len(tables)
            return start, end
    return None


def _parse_conference_table(t):
    tds = t.find_all("td")
    if len(tds) < 4:
        return None

    header = [_cell_text(td) for td in tds[:4]]
    acr_year_text, name, location, venue = header

    m = ACRONYM_YEAR_RE.match(acr_year_text)
    if not m:
        return None
    acronym, year = m.group(1), m.group(2)

    anchor_a = tds[0].find("a", attrs={"name": True})
    source_url = urljoin(VISIONBIB_URL, "#" + anchor_a["name"]) if anchor_a else VISIONBIB_URL

    # 컨퍼런스 약어 옆 <a>가 name(내부 앵커)뿐 아니라 href로 그 컨퍼런스 자체 홈페이지도
    # 갖고 있는 경우가 대부분. 가끔 "None.html" 같은 깨진 값이 있어 걸러낸다.
    homepage_url = None
    if anchor_a and anchor_a.get("href"):
        href = anchor_a["href"].strip()
        if href and "None" not in href:
            homepage_url = urljoin(VISIONBIB_URL, href)

    dates = None
    paper_deadline = None
    cfp_url = None

    if len(tds) >= 7:
        dates = _cell_text(tds[4]) or None

        deadline_text = _cell_text(tds[5])
        paper_deadline = extract_deadline_date_from_cells([deadline_text])

        cfp_a = tds[6].find("a", href=True)
        # CFP 링크가 "2026/icmi-10-26-call.html" 같은 상대경로라 절대 URL로 변환.
        cfp_url = urljoin(VISIONBIB_URL, cfp_a["href"].strip()) if cfp_a else None

        if paper_deadline is None:
            paper_deadline = _fallback_deadline_from_cfp(cfp_url)

    return {
        "acronym": acronym,
        "year": year,
        "name": name or None,
        "location": location or None,
        "venue": venue or None,
        "dates": dates,
        "paper_deadline": paper_deadline,
        "cfp_url": cfp_url,
        "homepage_url": homepage_url,
        "source_url": source_url,
        "raw_blocks": [_cell_text(td) for td in tds],
    }


def iter_conference_rows(year: int = 2026):
    resp = SESSION.get(VISIONBIB_URL, timeout=20)
    resp.raise_for_status()
    # 사이트 HTML이 <td>/<tr>를 제대로 안 닫는 깨진 마크업이라 html.parser로는
    # 테이블이 엉뚱하게 중첩됨 — html5lib(HTML5 파싱 알고리즘)이 필요.
    soup = BeautifulSoup(resp.text, "html5lib")

    tables = soup.find_all("table")
    rng = _find_year_table_range(tables, year)
    if rng is None:
        raise RuntimeError(f"{year}년 섹션을 찾을 수 없음")
    start, end = rng

    for t in tables[start:end]:
        item = _parse_conference_table(t)
        if item is not None:
            yield item


if __name__ == "__main__":
    for i, item in enumerate(iter_conference_rows(year=2026)):
        print("=" * 60)
        print("ACR:", item["acronym"])
        print("NAME:", item["name"])
        print("LOC:", item["location"])
        print("VENUE:", item["venue"])
        print("DATES:", item["dates"])
        print("DEADLINE:", item["paper_deadline"])
        print("CFP_URL:", item["cfp_url"])
        if i >= 5:
            break
