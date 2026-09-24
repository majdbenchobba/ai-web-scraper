from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_scraper.examples import checkpoint_resume, partial_results, selectors
from product_scraper.examples._fixtures import FixturePage, fixture_session, product_html
from product_scraper.checkpoint import read_checkpoint
from product_scraper.core import scrape_urls
from product_scraper.examples._fixtures import SELECTORS


class OfflineExamplesTest(unittest.TestCase):
    def test_examples_run_without_network_access_and_produce_expected_outputs(self):
        for example, expected_rows, expected_errors in (
            (selectors, 8, 0), (partial_results, 8, 2), (checkpoint_resume, 3, 0),
        ):
            with self.subTest(example=example.__name__), TemporaryDirectory() as directory, patch.object(
                socket.socket, "connect", side_effect=AssertionError("Offline examples must not connect")
            ), redirect_stdout(StringIO()):
                self.assertEqual(example.main(["--output-dir", directory]), 0)
                output = Path(directory)
                self.assertEqual(len(pd.read_csv(output / "scraped_data.csv")), expected_rows)
                self.assertEqual(len(pd.read_csv(output / "failed_urls.csv")), expected_errors)
                if example is checkpoint_resume:
                    checkpoints = list(output.glob("*.sqlite3"))
                    self.assertEqual(len(checkpoints), 1)
                    self.assertEqual(read_checkpoint(checkpoints[0]).completed, 3)

    def test_fixture_session_cannot_fall_back_to_real_http(self):
        with fixture_session({}) as (session, _), patch.object(
            socket.socket, "connect", side_effect=AssertionError("No network access")
        ):
            with self.assertRaises(requests.exceptions.InvalidSchema):
                session.get("https://example.test/")

    def test_scraping_does_not_close_a_caller_owned_session(self):
        url = "fixture://catalog/product"
        with fixture_session({url: FixturePage(product_html("Fixture cable", "$12.50"))}) as (session, transport):
            for _ in range(2):
                frame = scrape_urls([url], session=session, **SELECTORS)
                self.assertEqual(len(frame), 1)
                self.assertFalse(transport.closed)
            self.assertEqual(transport.calls[url], 2)
        self.assertTrue(transport.closed)


if __name__ == "__main__":
    unittest.main()
