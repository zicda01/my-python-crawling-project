"""네트워크 없이 합성 HTML·임시 파일로 크롤러의 의미 있는 동작을 검증한다.

실행: uv run python -m unittest discover -s tests -v
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

import crawl_test as crawler


FIXTURE = Path(__file__).parent / "fixtures" / "nasdaq_list.html"


class CrawlTest(unittest.TestCase):
    """공유할 수 있는 합성 입력을 사용하며 실제 사이트에 요청하지 않는다."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_filter_title_and_numeric_fields(self):
        result = crawler.parse_list(self.html, crawler.BASE_URL)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["excluded_count"], 3)
        first = result["posts"][0]
        self.assertEqual(first["title"], "합성 제목 하나")
        self.assertEqual(first["views"], 1234)
        self.assertEqual(first["recommendations"], 0)
        self.assertEqual(first["published_at_raw"], "17:43")
        self.assertTrue(first["url"].startswith("https://gall.dcinside.com/"))
        self.assertIsNone(result["posts"][1]["views"])
        self.assertIsNone(result["posts"][1]["recommendations"])
        self.assertEqual(len(result["warnings"]), 2)

    def test_duplicate_and_broken_rows_are_distinct(self):
        duplicate = '''<tr class="ub-content"><td class="gall_num">101</td>
          <td class="gall_tit"><a href="/mgallery/board/view/?id=nasdaq&amp;no=101">중복</a></td></tr>'''
        broken = '<tr class="ub-content"><td class="gall_num">103</td></tr>'
        html = self.html.replace("</tbody>", duplicate + broken + "</tbody>")
        result = crawler.parse_list(html, crawler.BASE_URL)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(result["parse_error_count"], 1)
        self.assertEqual(result["status"], "partial")

    def test_foreign_gallery_links_are_not_posts(self):
        html = self.html.replace("id=nasdaq", "id=other")
        with self.assertRaises(ValueError):
            crawler.parse_list(html, crawler.BASE_URL)

    def test_blocked_and_empty_pages_fail(self):
        for html in ("<html>접근 제한</html>", '<table class="gall_list"><tbody></tbody></table>'):
            with self.subTest(html=html), self.assertRaises(ValueError):
                crawler.parse_list(html, crawler.BASE_URL)

    def test_sample_roundtrip_timestamp_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = {
                "request_url": crawler.BASE_URL,
                "collected_at": "2026-10-04T06:00:00Z",
                "saved_encoding": "utf-8",
                "source_mode": "synthetic",
            }
            with (
                patch.object(crawler, "SAMPLE_PATH", root / "sample.html"),
                patch.object(crawler, "META_PATH", root / "sample.meta.json"),
                patch.object(crawler, "OUTPUT_DIR", root / "output"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                crawler.save_sample(self.html, metadata)
                html, loaded = crawler.load_sample()
                self.assertEqual(loaded["collected_at"], metadata["collected_at"])
                parsed = crawler.parse_list(html, crawler.BASE_URL)
                path = crawler.save_result(parsed)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), parsed)
                # 다시 확보해도 기존 샘플·메타데이터가 보존되어야 한다.
                crawler.save_sample(self.html, metadata)
                self.assertEqual(len(list(root.glob("sample_*.html"))), 1)
                self.assertEqual(len(list(root.glob("sample.meta_*.json"))), 1)

    def test_missing_sample_never_requests_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(crawler, "SAMPLE_PATH", Path(directory) / "missing.html"),
                patch.object(crawler, "RUN_MODE", "sample"),
                patch.object(crawler, "fetch_html") as fetch,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(crawler.main(), 1)
                fetch.assert_not_called()

    def test_timeout_does_not_create_success_json(self):
        with (
            patch.object(crawler, "RUN_MODE", "live"),
            patch.object(crawler, "fetch_html", side_effect=requests.Timeout("합성 타임아웃")),
            patch.object(crawler, "save_result") as save,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(crawler.main(), 1)
            save.assert_not_called()

    def test_http_response_validation(self):
        for status, content_type in ((403, "text/html"), (302, "text/html"), (200, "application/json")):
            response = requests.Response()
            response.status_code = status
            response.url = crawler.BASE_URL
            response.headers["Content-Type"] = content_type
            response._content = b"{}"
            response._content_consumed = True
            with self.subTest(status=status, content_type=content_type):
                with patch.object(crawler.requests, "get", return_value=response), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises((requests.RequestException, ValueError)):
                        crawler.fetch_html(crawler.BASE_URL)


if __name__ == "__main__":
    unittest.main()
