# parsers/date_parser.py
import re
from datetime import date

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTHS = "|".join(MONTH_NAMES)
_MONTH_NUM = {name: i + 1 for i, name in enumerate(MONTH_NAMES)}

DATE_RE = re.compile(rf"({MONTHS})\s+\d{{1,2}}(-\d{{1,2}})?,\s+\d{{4}}")

def extract_conference_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    return match.group(0)


# 날짜 범위 형식 3가지를 순서대로 시도:
#  A) "September 28, 2026-October 1, 2026" (월이 다르고 연도가 각각 표기됨)
#  B) "August 31-September 3, 2026"        (월이 다르고 연도는 끝에 한 번)
#  C) "October 6-8, 2026"                  (같은 달 안에서의 day-day)
#  D) "April 13, 2026"                     (단일 날짜, 예: 마감일)
_RANGE_A = re.compile(
    rf"^({MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})-({MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})$"
)
_RANGE_B = re.compile(
    rf"^({MONTHS})\s+(\d{{1,2}})-({MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})$"
)
_RANGE_C = re.compile(
    rf"^({MONTHS})\s+(\d{{1,2}})-(\d{{1,2}}),\s+(\d{{4}})$"
)
_SINGLE = re.compile(
    rf"^({MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})$"
)
# CFP 상세페이지(예: ".../ivcnz-11-26-call.html")에서 흔한 "7 September 2026" 형식.
_SINGLE_DMY = re.compile(
    rf"^(\d{{1,2}})\s+({MONTHS})\s+(\d{{4}})$"
)


def _iso(year: str | int, month: str, day: str | int) -> str:
    return date(int(year), _MONTH_NUM[month], int(day)).isoformat()


def parse_date_range(text: str | None) -> tuple[str | None, str | None]:
    """자유 텍스트 날짜 표현을 (start_iso, end_iso)로 변환. end_iso는 범위가
    아니면 None. 매칭 실패 시 (None, None)."""
    if not text:
        return None, None

    candidate = text.strip()

    # 셀 텍스트 그대로가 날짜 표현 전체인 경우(보통 그렇다) 먼저 온전히 매칭 시도.
    # DATE_RE로 먼저 잘라버리면 "August 31-September 3, 2026" 같은 월이 걸친
    # 범위에서 앞부분("August 31-")이 통째로 날아가 버리므로 순서가 중요하다.
    if m := _RANGE_A.match(candidate):
        m1, d1, y1, m2, d2, y2 = m.groups()
        return _iso(y1, m1, d1), _iso(y2, m2, d2)

    if m := _RANGE_B.match(candidate):
        m1, d1, m2, d2, y = m.groups()
        return _iso(y, m1, d1), _iso(y, m2, d2)

    if m := _RANGE_C.match(candidate):
        mo, d1, d2, y = m.groups()
        return _iso(y, mo, d1), _iso(y, mo, d2)

    if m := _SINGLE.match(candidate):
        mo, d, y = m.groups()
        return _iso(y, mo, d), None

    if m := _SINGLE_DMY.match(candidate):
        d, mo, y = m.groups()
        return _iso(y, mo, d), None

    # 앞뒤에 다른 문구가 섞인 지저분한 텍스트라면, 날짜 하나만이라도 뽑아서 재시도.
    m = DATE_RE.search(candidate)
    if m and m.group(0) != candidate:
        return parse_date_range(m.group(0))

    return None, None


def parse_single_date(text: str | None) -> str | None:
    """"April 13, 2026" 같은 단일 날짜 텍스트를 ISO 날짜 문자열로 변환."""
    start, _ = parse_date_range(text)
    return start