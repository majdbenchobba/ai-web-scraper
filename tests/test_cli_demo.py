from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_scraper import __version__, cli
from product_scraper.core import load_demo


class OfflineDemoTest(unittest.TestCase):
    def test_bundled_catalog_uses_the_parser_without_network_access(self):
        with patch.object(
            requests.sessions.Session, "request",
            side_effect=AssertionError("The demo must not access the network"),
        ):
            frame = load_demo()
        self.assertEqual(len(frame), 8)
        self.assertEqual(set(frame["SourceURL"]), {"demo:catalog"})
        self.assertEqual(frame.iloc[0]["Title"], "Patch Cable Kit")
        self.assertEqual(frame.iloc[0]["Price"], 19.5)
        self.assertEqual(frame.iloc[0]["Rating"], 4.4)

    def test_cli_demo_produces_readable_csv_summary_and_charts(self):
        with TemporaryDirectory() as directory, patch.object(
            sys, "argv", ["product-scraper", "--demo", "--output-dir", directory]
        ), patch.object(
            requests.sessions.Session, "request",
            side_effect=AssertionError("The demo must not access the network"),
        ), redirect_stdout(StringIO()) as console:
            self.assertEqual(cli.main(), 0)
            output = Path(directory)
            self.assertEqual(len(pd.read_csv(output / "scraped_data.csv")), 8)
            self.assertIn(
                "Products scraped: 8", (output / "summary_report.txt").read_text(encoding="utf-8")
            )
            for name in ("price_chart.png", "rating_chart.png"):
                self.assertTrue((output / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertIn("No network requests", console.getvalue())

    def test_real_urls_and_demo_cannot_be_combined(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            cli.build_parser().parse_args(["--demo", "--urls-file", "urls.txt"])
        self.assertEqual(error.exception.code, 2)

    def test_missing_urls_file_reports_a_clear_error(self):
        with TemporaryDirectory() as directory, patch.object(
            sys, "argv", ["product-scraper", "--urls-file", str(Path(directory) / "missing.txt")]
        ), redirect_stdout(StringIO()) as console:
            self.assertEqual(cli.main(), 1)
        self.assertIn("URLs file not found", console.getvalue())

    def test_version_does_not_require_a_source(self):
        with redirect_stdout(StringIO()) as console, self.assertRaises(SystemExit) as result:
            cli.build_parser().parse_args(["--version"])
        self.assertEqual(result.exception.code, 0)
        self.assertIn(__version__, console.getvalue())

    def test_legacy_launcher_still_runs_the_offline_demo(self):
        repository = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(repository / "all_in_one_scraper.py"),
                 "--demo", "--skip-charts", "--output-dir", directory],
                cwd=directory, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(pd.read_csv(Path(directory) / "scraped_data.csv")), 8)


if __name__ == "__main__":
    unittest.main()
