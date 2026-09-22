import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraper_core import (  # noqa: E402
    build_summary,
    extract_number,
    normalize_urls,
    scrape_product_page,
    write_outputs,
)


class ScraperCoreTest(unittest.TestCase):
    def test_normalize_urls_ignores_blanks_and_comments(self):
        self.assertEqual(
            normalize_urls([" https://example.test/a ", "", " # note", "https://example.test/b"]),
            ["https://example.test/a", "https://example.test/b"],
        )

    def test_extract_number_handles_currency_and_missing_values(self):
        self.assertEqual(extract_number("$1,249.50"), 1249.5)
        self.assertEqual(extract_number("-19.25 USD"), -19.25)
        self.assertIsNone(extract_number("not available"))
        self.assertIsNone(extract_number(""))

    def test_scrape_product_page_uses_explicit_selectors(self):
        response = Mock()
        response.text = """
        <article class="card">
          <h2 class="name">Example Product</h2>
          <span class="price">$42.50</span>
          <span class="rating">4.7 / 5</span>
        </article>
        """
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response

        rows = scrape_product_page(
            session,
            "https://example.test/products",
            ".card",
            ".name",
            ".price",
            ".rating",
        )

        self.assertEqual(
            rows,
            [
                {
                    "SourceURL": "https://example.test/products",
                    "Title": "Example Product",
                    "Price": 42.5,
                    "Rating": 4.7,
                }
            ],
        )
        session.get.assert_called_once()

    def test_summary_and_outputs_use_only_local_data(self):
        frame = pd.DataFrame(
            [
                {"SourceURL": "https://example.test/a", "Title": "A", "Price": 10.0, "Rating": 4.0},
                {"SourceURL": "https://example.test/b", "Title": "B", "Price": 20.0, "Rating": 5.0},
            ]
        )
        self.assertIn("Average price: 15.00", build_summary(frame))

        with TemporaryDirectory() as directory:
            files = write_outputs(frame, Path(directory), skip_charts=True)
            self.assertTrue(files["csv"].exists())
            self.assertTrue(files["summary"].exists())
            self.assertNotIn("price_chart", files)


if __name__ == "__main__":
    unittest.main()
