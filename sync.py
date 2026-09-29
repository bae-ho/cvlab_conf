# sync.py
from collections import defaultdict
from datetime import date

from visionbib_fetch import iter_conference_rows
from parsers.date_parser import parse_date_range, month_of
from notion_client import notion_get_title_property_name
from notion_sync import push_to_notion, archive_past_conferences


def run(year=None, years_ahead=1, months=None, limit_per_month=None, push=False, dry_run=True, only_upcoming=True):
    # year를 안 주면 오늘 기준 연도. years_ahead=1이면 올해+내년까지 커버
    # (사이트 자체가 그 다음 해부터는 데이터가 거의 없어서 더 늘려봐야 의미 없음).
    # only_upcoming=True면 오늘보다 이전 날짜인 컨퍼런스는 건너뛴다.
    if year is None:
        year = date.today().year
    today_iso = date.today().isoformat()
    years = [year + i for i in range(years_ahead + 1)]

    # 사이트 구조상 연도 전체가 한 번의 요청/파싱으로 나오므로, 연도별로 fetch는
    # 한 번만 하고 월별 필터링은 여기서 dates 텍스트 기준으로 수행한다.
    by_year_month = defaultdict(list)
    for y in years:
        for item in iter_conference_rows(year=y):
            start, _ = parse_date_range(item.get("dates"))
            if only_upcoming and start and start < today_iso:
                continue
            by_year_month[(y, month_of(item.get("dates")))].append(item)

    target_months = months if months is not None else range(1, 13)
    title_prop = notion_get_title_property_name() if push else None

    total = 0
    for y in years:
        for m in target_months:
            print("\n" + "#" * 80)
            print(f"# {y}-{m:02d}")
            print("#" * 80)

            count = 0
            for item in by_year_month.get((y, m), []):
                print("=" * 60)
                print("ACR:", item.get("acronym"))
                print("NAME:", item.get("name"))
                print("LOC:", item.get("location"))
                print("VENUE:", item.get("venue"))
                print("DATES:", item.get("dates"))
                print("PAPER_DEADLINE:", item.get("paper_deadline"))
                print("CFP_URL:", item.get("cfp_url"))
                print("HOMEPAGE_URL:", item.get("homepage_url"))

                if push:
                    push_to_notion(item, title_prop, dry_run=dry_run)

                count += 1
                total += 1

                if limit_per_month is not None and count >= limit_per_month:
                    break

            print(f"[month done] {y}-{m:02d} => {count} items")

    # 이미 끝난 컨퍼런스 페이지는 Notion에서 삭제(휴지통 이동).
    if push and only_upcoming:
        archive_past_conferences(today_iso, dry_run=dry_run)

    print(f"\n[all done] total items: {total}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VisionBib -> Notion 동기화 (오늘~내년 말)")
    parser.add_argument("--live", action="store_true", help="실제로 Notion에 반영 (기본은 dry-run 미리보기만)")
    parser.add_argument("--no-push", action="store_true", help="Notion 호출 없이 콘솔 출력만")
    args = parser.parse_args()

    run(push=not args.no_push, dry_run=not args.live)
