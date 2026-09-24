from contextlib import redirect_stdout
import csv
from datetime import datetime, timezone
from email.utils import format_datetime
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, call, patch

import pandas as pd
import requests
from soupsieve import SelectorSyntaxError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_scraper import cli, network
from product_scraper.core import ScrapeFailure, scrape_urls, write_outputs


SELECTORS = {
    "container_selector": ".product-item",
    "title_selector": ".product-title",
    "price_selector": ".product-price",
    "rating_selector": ".product-rating",
}
HTML = (
    '<article class="product-item"><h2 class="product-title">Fixture product</h2>'
    '<span class="product-price">$42.50</span>'
    '<span class="product-rating">4.7</span></article>'
)


def response(status=200, html=HTML, headers=None, url="https://example.test/products"):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result.encoding = "utf-8"
    result._content = html.encode("utf-8")
    result._content_consumed = True
    result.headers.update(headers or {})
    return result


class RequestRecoveryTest(unittest.TestCase):
    def test_connection_and_timeout_failures_recover_with_bounded_backoff(self):
        with patch.object(
            requests.Session, "request",
            side_effect=[requests.ConnectionError("Connection lost"), requests.Timeout("Timed out"), response()],
        ) as request, patch.object(network.time, "sleep") as sleep:
            frame = scrape_urls(["https://example.test/products"], **SELECTORS)
        self.assertEqual(frame["Title"].tolist(), ["Fixture product"])
        self.assertEqual(request.call_count, 3)
        sleep.assert_has_calls([call(0.5), call(1.0)])
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(all(c.args[0] == "GET" for c in request.call_args_list))

    def test_each_transient_http_status_can_recover(self):
        for status in (408, 429, 500, 502, 503, 504):
            with self.subTest(status=status), patch.object(
                requests.Session, "request", side_effect=[response(status), response()]
            ) as request, patch.object(network.time, "sleep"):
                frame = scrape_urls(["https://example.test/products"], **SELECTORS)
                self.assertEqual(len(frame), 1)
                self.assertEqual(request.call_count, 2)

    def test_retry_limit_and_zero_retry_mode_are_enforced(self):
        for retries in (0, 2, 5):
            with self.subTest(retries=retries), patch.object(
                requests.Session, "request", side_effect=requests.Timeout("Persistent timeout")
            ) as request, patch.object(network.time, "sleep") as sleep:
                with self.assertRaises(requests.Timeout):
                    scrape_urls(["https://example.test/products"], max_retries=retries, **SELECTORS)
                self.assertEqual(request.call_count, retries + 1)
                self.assertEqual(sleep.call_count, retries)
                self.assertLessEqual(sum(c.args[0] for c in sleep.call_args_list), 15.5)

    def test_permanent_http_and_certificate_errors_are_not_retried(self):
        errors = [response(code) for code in (400, 401, 403, 404, 501)]
        errors.append(requests.exceptions.SSLError("Certificate validation failed"))
        for failure in errors:
            with self.subTest(failure=failure), patch.object(
                requests.Session, "request",
                side_effect=failure if isinstance(failure, Exception) else None,
                return_value=failure,
            ) as request, patch.object(network.time, "sleep") as sleep:
                with self.assertRaises(requests.RequestException):
                    scrape_urls(["https://example.test/products"], **SELECTORS)
                request.assert_called_once()
                sleep.assert_not_called()

    def test_retry_after_is_respected(self):
        with patch.object(
            requests.Session, "request",
            side_effect=[response(429, headers={"Retry-After": "2"}), response()],
        ), patch.object(network.time, "sleep") as sleep:
            scrape_urls(["https://example.test/products"], **SELECTORS)
        sleep.assert_called_once_with(2.0)

    def test_long_server_wait_is_reported_without_retrying_early(self):
        failures = []
        with patch.object(
            requests.Session, "request",
            return_value=response(503, headers={"Retry-After": "120"}),
        ) as request, patch.object(network.time, "sleep") as sleep:
            frame = scrape_urls(
                ["https://example.test/products"], continue_on_error=True,
                error_callback=failures.append, **SELECTORS,
            )
        self.assertTrue(frame.empty)
        self.assertEqual(len(failures), 1)
        request.assert_called_once()
        sleep.assert_not_called()

    def test_http_date_retry_after_and_invalid_headers(self):
        now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
        deadline = datetime(2026, 9, 24, 12, 0, 4, tzinfo=timezone.utc)
        with patch.object(network, "datetime", wraps=datetime) as clock:
            clock.now.return_value = now
            self.assertEqual(
                network.retry_delay(response(503, headers={"Retry-After": format_datetime(deadline, usegmt=True)}), 0),
                4.0,
            )
        self.assertEqual(network.retry_delay(response(503, headers={"Retry-After": "invalid"}), 1), 1.0)
        self.assertIsNone(network.retry_delay(response(503, headers={"Retry-After": "9" * 10000}), 0))
        self.assertEqual(network.retry_delay(response(429, headers={"Retry-After": "0"}), 0), 0.5)

    def test_bad_configuration_is_rejected_before_any_request(self):
        cases = [
            ({"max_retries": -1}, ValueError),
            ({"max_retries": 6}, ValueError),
            ({"max_retries": True}, ValueError),
            ({"max_retries": 1.5}, ValueError),
            ({"decimal_separator": ";"}, ValueError),
            ({"container_selector": "["}, SelectorSyntaxError),
            ({"continue_on_error": True}, ValueError),
            ({"resume": True}, ValueError),
        ]
        for options, expected in cases:
            with self.subTest(options=options), patch.object(requests.Session, "request") as request:
                with self.assertRaises(expected):
                    scrape_urls(["https://example.test/products"], **{**SELECTORS, **options})
                request.assert_not_called()

    def test_parse_failure_keeps_other_urls_and_is_not_retried(self):
        failures = []
        bad_html = HTML.replace("$42.50", "$12,34.50")
        with patch.object(
            requests.Session, "request", side_effect=[response(), response(html=bad_html), response()]
        ) as request, patch.object(network.time, "sleep") as sleep:
            frame = scrape_urls(
                ["https://example.test/first", "https://example.test/bad", "https://example.test/last"],
                continue_on_error=True, error_callback=failures.append, **SELECTORS,
            )
        self.assertEqual(frame["SourceURL"].tolist(), ["https://example.test/first", "https://example.test/last"])
        self.assertEqual(failures[0].url, "https://example.test/bad")
        self.assertIn("Choose the number format", failures[0].error)
        self.assertEqual(request.call_count, 3)
        sleep.assert_not_called()

    def test_unexpected_programming_errors_are_not_hidden_as_url_failures(self):
        errors = Mock()
        with patch.object(requests.Session, "request", side_effect=RuntimeError("Unexpected bug")):
            with self.assertRaisesRegex(RuntimeError, "Unexpected bug"):
                scrape_urls(
                    ["https://example.test/products"], continue_on_error=True,
                    error_callback=errors, **SELECTORS,
                )
        errors.assert_not_called()

    def test_fail_fast_api_stops_before_the_next_url(self):
        with patch.object(
            requests.Session, "request", side_effect=[response(404), response()]
        ) as request:
            with self.assertRaises(requests.HTTPError):
                scrape_urls(["https://example.test/missing", "https://example.test/next"], **SELECTORS)
        request.assert_called_once()


class BatchReportingTest(unittest.TestCase):
    def run_cli(self, responses, urls):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        url_file = root / "urls.txt"
        url_file.write_text("\n".join(urls), encoding="utf-8")
        with patch.object(
            sys, "argv",
            ["product-scraper", "--urls-file", str(url_file), "--output-dir", str(root), "--skip-charts"],
        ), patch.object(requests.Session, "request", side_effect=responses), patch.object(
            network.time, "sleep"
        ), redirect_stdout(StringIO()) as console:
            code = cli.main()
        with (root / "failed_urls.csv").open(encoding="utf-8", newline="") as stream:
            failures = list(csv.DictReader(stream))
        return code, pd.read_csv(root / "scraped_data.csv"), failures, console.getvalue()

    def test_partial_cli_result_has_its_own_exit_code_and_error_csv(self):
        code, frame, errors, console = self.run_cli(
            [response(), response(404), response()],
            ["https://example.test/first", "https://example.test/missing", "https://example.test/last"],
        )
        self.assertEqual(code, 3)
        self.assertEqual(len(frame), 2)
        self.assertEqual(errors[0]["SourceURL"], "https://example.test/missing")
        self.assertIn("404", errors[0]["Error"])
        self.assertIn("URLs failed: 1/3", console)

    def test_all_failed_urls_return_failure_and_write_readable_empty_csv(self):
        code, frame, errors, console = self.run_cli(
            [response(403), response(404)], ["https://example.test/denied", "https://example.test/missing"]
        )
        self.assertEqual(code, 1)
        self.assertTrue(frame.empty)
        self.assertEqual(list(frame.columns), ["SourceURL", "Title", "Price", "Rating"])
        self.assertEqual(len(errors), 2)
        self.assertIn("URLs failed: 2/2", console)

    def test_successful_batch_has_no_error_rows(self):
        code, frame, errors, _ = self.run_cli([response()], ["https://example.test/products"])
        self.assertEqual(code, 0)
        self.assertEqual(len(frame), 1)
        self.assertEqual(errors, [])

    def test_report_round_trips_commas_and_newlines_and_clears_stale_outputs(self):
        frame = pd.DataFrame(columns=["SourceURL", "Title", "Price", "Rating"])
        failure = ScrapeFailure("https://example.test/a,b", "Request failed,\ntry later")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("price_chart.png", "rating_chart.png"):
                (root / name).write_bytes(b"previous run")
            files = write_outputs(frame, root, skip_charts=False, failures=[failure])
            with files["errors"].open(encoding="utf-8", newline="") as stream:
                self.assertEqual(list(csv.DictReader(stream)), [{"SourceURL": failure.url, "Error": failure.error}])
            self.assertFalse((root / "price_chart.png").exists())
            self.assertFalse((root / "rating_chart.png").exists())
            self.assertIn("URLs failed: 1", files["summary"].read_text(encoding="utf-8"))
            write_outputs(frame, root, skip_charts=True)
            with files["errors"].open(encoding="utf-8", newline="") as stream:
                self.assertEqual(list(csv.DictReader(stream)), [])


if __name__ == "__main__":
    unittest.main()
