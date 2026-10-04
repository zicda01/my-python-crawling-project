"""나스닥 PC 목록 한 페이지를 읽는 학습용 크롤링 테스트.

실행: uv run crawl_test.py
코드 상단 RUN_MODE만 바꿔 capture → sample → live 순서로 실험한다.
capture는 HTML·응답 정보를 samples에 저장하고, sample은 웹 요청 없이
그 파일을 파싱한다. live는 새 응답을 메모리에서 파싱하며 HTML을 저장하지 않는다.

출력은 터미널과 output의 JSON이다. 광고·설문·공지는 제외하며,
본문·댓글·다음 페이지·DB·예약 실행은 이번 코드의 범위에 포함하지 않는다.
실제 요청 전 수집 정책을 확인한다. 기본 모드는 반복 학습용 sample이다.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag


# __file__ 기준 경로는 Mac·Windows 및 다른 작업 디렉터리에서도 동일하게 동작한다.
PROJECT_DIR = Path(__file__).resolve().parent
BASE_URL = "https://gall.dcinside.com/mgallery/board/lists/?id=nasdaq&page=1"
TIMEOUT_SECONDS = 15
RUN_MODE = "sample"  # capture: 확보 / sample: 로컬 파싱 / live: 새 응답 파싱
SAMPLE_PATH = PROJECT_DIR / "samples" / "nasdaq_list.html"
META_PATH = PROJECT_DIR / "samples" / "nasdaq_list.meta.json"
OUTPUT_DIR = PROJECT_DIR / "output"


def utc_now() -> str:
    """현재 시각을 시간대가 포함된 UTC ISO 8601 문자열로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


def fetch_html(url: str) -> tuple[str, dict]:
    """URL을 한 번 요청해 HTML 문자열과 응답 정보를 반환한다.

    타임아웃·HTTP 오류는 requests 예외, 리다이렉트·비HTML 응답은
    ValueError로 전달한다. 자동 재시도나 다른 페이지로의 전환은 하지 않는다.
    """
    # 자동 이동을 끄면 로그인·다른 사이트에 도착한 결과를 정상 목록으로 오인하지 않는다.
    with requests.get(
        url,
        timeout=TIMEOUT_SECONDS,
        allow_redirects=False,
        headers={"User-Agent": "NasdaqLearningCrawler/0.1"},
    ) as response:
        print(f"HTTP 상태: {response.status_code}")
        response.raise_for_status()  # 4xx·5xx를 빈 게시글 목록으로 처리하지 않는다.
        if 300 <= response.status_code < 400:
            raise ValueError("예상 밖 리다이렉트: 다른 주소를 자동 방문하지 않습니다.")
        content_type = response.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError(f"HTML이 아닌 응답입니다: {content_type!r}")

        # 실제 확보한 PC 응답에는 charset=UTF-8이 명시되어 있었다.
        # 명시적 charset이 없다면 requests의 추정값을 사용하되 메타데이터에 남긴다.
        if "charset=" not in content_type.lower():
            response.encoding = response.apparent_encoding or "utf-8"
        encoding = response.encoding or "utf-8"
        # strict 디코딩은 잘못된 인코딩을 대체 문자로 조용히 숨기지 않는다.
        html = response.content.decode(encoding)
        metadata = {
            "source_mode": "http",
            "request_url": url,
            "final_url": response.url,
            "collected_at": utc_now(),
            "status_code": response.status_code,
            "content_type": content_type,
            "response_encoding": encoding,
            "saved_encoding": "utf-8",
        }
        return html, metadata


def save_sample(html: str, metadata: dict) -> None:
    """HTML과 확보 정보를 저장한다. 기존 두 파일은 시각을 붙여 보존한다.

    여기서 저장했다고 정상 목록이라는 뜻은 아니다. 목록 확인은 parse_list의 역할이다.
    파일 생성·읽기 실패는 OSError로 호출자에게 전달한다.
    """
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for path in (SAMPLE_PATH, META_PATH):
        if path.exists():
            archived = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
            path.rename(archived)
    SAMPLE_PATH.write_text(html, encoding="utf-8")
    META_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"샘플 저장: {SAMPLE_PATH}")


def load_sample() -> tuple[str, dict]:
    """UTF-8 샘플과 메타데이터를 읽는다. 누락 시 웹 요청하지 않고 실패한다."""
    if not SAMPLE_PATH.is_file() or not META_PATH.is_file():
        raise FileNotFoundError(
            "HTML 또는 메타데이터가 없습니다. RUN_MODE를 'capture'로 바꿔 "
            "확보한 뒤 'sample'로 되돌리세요."
        )
    html = SAMPLE_PATH.read_text(encoding="utf-8")
    metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("샘플 메타데이터는 JSON 객체여야 합니다.")
    if metadata.get("request_url") != BASE_URL or not metadata.get("collected_at"):
        raise ValueError("샘플의 요청 URL 또는 확보 시각을 확인하세요.")
    if metadata.get("saved_encoding") != "utf-8":
        raise ValueError("샘플은 UTF-8 저장 파일이어야 합니다.")
    return html, metadata


def cell_text(row: Tag, selector: str) -> str | None:
    """행의 특정 칸 텍스트를 반환한다. 칸이 없거나 비어 있으면 None이다."""
    cell = row.select_one(selector)
    if cell is None:
        return None
    text = cell.get_text(" ", strip=True)
    return text or None


def optional_number(text: str | None, label: str, warnings: list) -> int | None:
    """쉼표가 있는 숫자를 정수로 변환한다. 잘못된 값은 0 대신 None과 경고를 남긴다."""
    if text is not None:
        normalized = text.replace(",", "")
        if normalized.isascii() and normalized.isdecimal():
            return int(normalized)
    warnings.append(f"{label}: 숫자가 없거나 형식이 잘못되었습니다 ({text!r}).")
    return None


def parse_post_row(row: Tag, base_url: str, warnings: list) -> dict:
    """일반 게시글 행을 dict로 변환한다. 필수 ID·제목·URL 오류는 ValueError다."""
    number = cell_text(row, "td.gall_num")
    if not number or not number.isascii() or not number.isdecimal() or int(number) <= 0:
        raise ValueError("양의 정수 게시글 번호가 없습니다.")
    post_id = int(number)

    # 실제 HTML에서 제목과 [댓글 수]는 같은 칸의 별도 a 요소였다.
    # reply_numbox를 제외해 댓글 링크의 텍스트가 제목에 섞이지 않게 한다.
    link = row.select_one("td.gall_tit a[href]:not(.reply_numbox)")
    if link is None:
        raise ValueError("제목 링크가 없습니다.")
    href = link.get("href")
    if not isinstance(href, str):
        raise ValueError("제목 링크의 href가 잘못되었습니다.")
    absolute_url = urljoin(base_url, href)
    parts = urlsplit(absolute_url)
    query = parse_qs(parts.query)
    if (
        parts.scheme != "https"
        or parts.netloc != "gall.dcinside.com"
        or parts.path != "/mgallery/board/view/"
        or query.get("id") != ["nasdaq"]
        or query.get("no") != [str(post_id)]
    ):
        raise ValueError("제목 URL이 같은 나스닥 게시글을 가리키지 않습니다.")

    # em.icon_img와 img는 글 아이콘이다. 선택한 링크만 수정하며 다른 칸은 읽지 않는다.
    for decoration in link.select("em.icon_img, img, .reply_num"):
        decoration.decompose()
    # strip=True는 인라인 요소 앞의 공백까지 제거할 수 있다. 먼저 연결한 뒤 공백을 정리한다.
    title = " ".join(link.get_text("", strip=False).split())
    if not title:
        raise ValueError("제목이 비어 있습니다.")
    date = cell_text(row, "td.gall_date")
    if date is None:
        warnings.append(f"글 {post_id}: 목록 작성일이 없습니다.")
    return {
        "post_id": post_id,
        "title": title,
        "url": absolute_url,
        "category": cell_text(row, "td.gall_subject"),
        # 목록 표시값은 '17:43'일 수 있다. 전체 작성 일시를 추측하지 않는다.
        "published_at_raw": date,
        "views": optional_number(cell_text(row, "td.gall_count"), f"글 {post_id} 조회수", warnings),
        "recommendations": optional_number(
            cell_text(row, "td.gall_recommend"), f"글 {post_id} 추천수", warnings
        ),
    }


def parse_list(html: str, base_url: str) -> dict:
    """HTML 문자열에서 게시글·제외·오류 통계를 반환한다. 네트워크·파일 접근은 없다.

    목록 영역이 없거나 일반 행을 하나도 정상 추출하지 못하면 실패한다.
    명시적인 빈 목록 HTML은 아직 관찰하지 않았으므로 0건 성공을 추측하지 않는다.
    """
    soup = BeautifulSoup(html, "html.parser")
    # 2026-10-04 실제 응답: table.gall_list > tbody > tr.ub-content 구조를 관찰했다.
    table = soup.select_one("table.gall_list")
    if table is None:
        raise ValueError("게시글 목록을 찾지 못했습니다. 차단 화면·HTML 구조를 확인하세요.")
    rows = table.select("tbody > tr.ub-content")
    if not rows:
        raise ValueError("관찰한 구조의 목록 행이 없습니다. 정상 0건으로 처리하지 않습니다.")
    posts = []
    warnings = []
    seen_ids = set()
    excluded = 0
    duplicate = 0
    errors = 0

    for position, row in enumerate(rows, start=1):
        category = cell_text(row, "td.gall_subject") or ""
        # 실제 광고·설문의 말머리는 AD·설문, 공지는 숫자 번호와 icon_notice를 가졌다.
        if (
            category.upper() in {"AD", "광고", "설문"}
            or "공지" in category
            or row.get("data-type") == "icon_notice"
            or row.select_one(".icon_ad, .icon_n_survey, .icon_notice") is not None
        ):
            excluded += 1
            continue
        try:
            post = parse_post_row(row, base_url, warnings)
        except ValueError as exc:
            errors += 1
            warnings.append(f"목록 {position}번째 행 파싱 실패: {exc}")
            continue
        if post["post_id"] in seen_ids:
            duplicate += 1
            warnings.append(f"글 {post['post_id']}: 중복 행을 제외했습니다.")
            continue
        seen_ids.add(post["post_id"])
        posts.append(post)

    if not posts:
        raise ValueError(f"정상 추출 글이 없습니다 (제외 {excluded}, 오류 {errors}).")
    return {
        "posts": posts,
        "count": len(posts),
        "excluded_count": excluded,
        "duplicate_count": duplicate,
        "parse_error_count": errors,
        "warnings": warnings,
        "status": "partial" if errors else "success",
    }


def save_result(result: dict) -> Path:
    """추출 결과를 UTF-8 JSON으로 저장하고 경로를 반환한다. 저장 오류는 OSError다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = OUTPUT_DIR / f"nasdaq_list_{stamp}.json"
    # ensure_ascii=False는 한글을 유니코드 이스케이프 대신 읽을 수 있는 문자로 저장한다.
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    """입력 모드에 따라 실행한다. 성공 0, 요청·파싱·파일 오류 1을 반환한다."""
    try:
        if RUN_MODE == "capture":
            html, metadata = fetch_html(BASE_URL)
            # 먼저 저장하면 HTTP 200 차단 화면도 로컬에서 원인을 관찰할 수 있다.
            save_sample(html, metadata)
            parsed = parse_list(html, BASE_URL)
            print(f"목록 확인: 일반 글 {parsed['count']}개. RUN_MODE='sample'로 바꿔 학습하세요.")
            return 0
        if RUN_MODE == "sample":
            html, metadata = load_sample()
        elif RUN_MODE == "live":
            html, metadata = fetch_html(BASE_URL)
        else:
            raise ValueError("RUN_MODE는 capture, sample, live 중 하나여야 합니다.")

        parsed = parse_list(html, BASE_URL)
        result = {
            "site": "dcinside",
            "gallery_id": "nasdaq",
            "source_url": metadata["request_url"],
            "final_url": metadata.get("final_url"),
            "page": 1,
            "view": "pc",
            "source_mode": RUN_MODE,
            "sample_origin": metadata.get("source_mode") if RUN_MODE == "sample" else None,
            "collected_at": metadata["collected_at"],
            "parsed_at": utc_now(),
            **parsed,
        }
        print(f"모드: {RUN_MODE} / 확보 시각: {result['collected_at']}")
        print(
            f"수집 {parsed['count']}개 / 제외 {parsed['excluded_count']}개 / "
            f"중복 {parsed['duplicate_count']}개 / 오류 {parsed['parse_error_count']}개"
        )
        for post in parsed["posts"]:
            print(f"{post['post_id']} | {post['title']}")
        for warning in parsed["warnings"]:
            print(f"경고: {warning}")
        path = save_result(result)
        print(f"결과 저장: {path}")
        return 0
    except requests.RequestException as exc:
        print(f"요청 실패: {exc}", file=sys.stderr)
    except (OSError, UnicodeError) as exc:
        print(f"파일·인코딩 실패: {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"입력·응답·파싱 실패: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    # 함수 import만으로 요청이 실행되지 않게 한다. 테스트에서도 함수를 따로 호출할 수 있다.
    raise SystemExit(main())
