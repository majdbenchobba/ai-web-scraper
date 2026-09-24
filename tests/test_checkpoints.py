from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_scraper import cli
from product_scraper.checkpoint import Checkpoint, CheckpointError, read_checkpoint
from product_scraper.core import scrape_urls
from product_scraper.examples._fixtures import SELECTORS


REPOSITORY = Path(__file__).resolve().parents[1]
SETTINGS = {**SELECTORS, "decimal_separator": "."}


def product(url, title="Saved product"):
    return [{"SourceURL": url, "Title": title, "Price": 12.5, "Rating": None}]


class CheckpointTests(unittest.TestCase):
    def test_keyboard_interrupt_keeps_completed_pages_and_resume_skips_them(self):
        urls = ["fixture://first", "fixture://second", "fixture://third"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run café.sqlite3"
            with patch(
                "product_scraper.core.scrape_product_page",
                side_effect=[product(urls[0], "Câble café"), KeyboardInterrupt()],
            ), self.assertRaises(KeyboardInterrupt):
                scrape_urls(urls, checkpoint_path=path, **SELECTORS)
            self.assertEqual(read_checkpoint(path).completed, 1)
            with patch(
                "product_scraper.core.scrape_product_page",
                side_effect=lambda **kwargs: product(kwargs["url"]),
            ) as fetch:
                frame = scrape_urls(urls, checkpoint_path=path, resume=True, **SELECTORS)
            self.assertEqual([c.kwargs["url"] for c in fetch.call_args_list], urls[1:])
            self.assertEqual(frame["SourceURL"].tolist(), urls)
            self.assertEqual(frame.iloc[0]["Title"], "Câble café")
            self.assertEqual(read_checkpoint(path).completed, 3)

    def test_success_is_committed_before_a_progress_callback_can_interrupt(self):
        def interrupt_after_success(message):
            if "Found" in message:
                raise KeyboardInterrupt()

        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.sqlite3"
            with patch(
                "product_scraper.core.scrape_product_page", return_value=product("fixture://first")
            ), self.assertRaises(KeyboardInterrupt):
                scrape_urls(
                    ["fixture://first", "fixture://second"], checkpoint_path=path,
                    progress_callback=interrupt_after_success, **SELECTORS,
                )
            self.assertEqual(read_checkpoint(path).completed, 1)

    def test_failed_urls_are_retried_and_clear_old_errors_on_resume(self):
        urls = ["fixture://first", "fixture://failed", "fixture://last"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.sqlite3"
            failures = []
            with patch(
                "product_scraper.core.scrape_product_page",
                side_effect=[product(urls[0]), requests.HTTPError("404 fixture"), product(urls[2])],
            ):
                scrape_urls(
                    urls, checkpoint_path=path, continue_on_error=True,
                    error_callback=failures.append, **SELECTORS,
                )
            self.assertEqual(len(failures), 1)
            self.assertEqual(len(read_checkpoint(path).failures), 1)
            with patch(
                "product_scraper.core.scrape_product_page", return_value=product(urls[1])
            ) as fetch:
                frame = scrape_urls(urls, checkpoint_path=path, resume=True, **SELECTORS)
            fetch.assert_called_once()
            self.assertEqual(fetch.call_args.kwargs["url"], urls[1])
            self.assertEqual(frame["SourceURL"].tolist(), urls)
            self.assertEqual(read_checkpoint(path).failures, [])

    def test_empty_pages_and_duplicate_url_occurrences_are_saved_exactly_once(self):
        urls = ["fixture://same", "fixture://same", "fixture://empty"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.sqlite3"
            with patch(
                "product_scraper.core.scrape_product_page",
                side_effect=[product(urls[0], "First occurrence"), product(urls[1], "Second occurrence"), []],
            ):
                original = scrape_urls(urls, checkpoint_path=path, **SELECTORS)
            self.assertEqual(read_checkpoint(path).completed, 3)
            with patch("product_scraper.core.scrape_product_page") as fetch:
                resumed = scrape_urls(urls, checkpoint_path=path, resume=True, **SELECTORS)
            fetch.assert_not_called()
            pd.testing.assert_frame_equal(original, resumed)

    def test_mismatched_settings_and_url_order_do_not_modify_saved_data(self):
        urls = ["fixture://first", "fixture://second"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.sqlite3"
            with Checkpoint(path, urls, SETTINGS) as checkpoint:
                checkpoint.save(0, product(urls[0]))
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            cases = [
                (list(reversed(urls)), SELECTORS),
                (urls, {**SELECTORS, "title_selector": ".different"}),
                (urls, {**SELECTORS, "decimal_separator": ","}),
            ]
            for queue, options in cases:
                with self.subTest(options=options), patch("product_scraper.core.scrape_product_page") as fetch:
                    with self.assertRaisesRegex(CheckpointError, "differ"):
                        scrape_urls(queue, checkpoint_path=path, resume=True, **options)
                    fetch.assert_not_called()
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_new_run_refuses_to_overwrite_an_existing_checkpoint(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.sqlite3"
            with Checkpoint(path, ["fixture://first"], SETTINGS) as checkpoint:
                checkpoint.save(0, product("fixture://first"))
            before = path.read_bytes()
            with patch("product_scraper.core.scrape_product_page") as fetch:
                with self.assertRaisesRegex(CheckpointError, "already exists"):
                    scrape_urls(["fixture://first"], checkpoint_path=path, **SELECTORS)
                fetch.assert_not_called()
            self.assertEqual(path.read_bytes(), before)

    def test_corrupt_and_missing_checkpoints_fail_without_requests(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.sqlite3"
            corrupt = Path(directory) / "corrupt.sqlite3"
            corrupt.write_bytes(b"This is not a SQLite checkpoint.")
            for path in (missing, corrupt):
                with self.subTest(path=path.name), patch("product_scraper.core.scrape_product_page") as fetch:
                    with self.assertRaises(CheckpointError):
                        scrape_urls(["fixture://first"], checkpoint_path=path, resume=True, **SELECTORS)
                    fetch.assert_not_called()
            self.assertFalse(missing.exists())
            self.assertEqual(corrupt.read_bytes(), b"This is not a SQLite checkpoint.")

    def test_another_process_cannot_write_while_a_run_owns_the_checkpoint(self):
        script = """
import json, sys
from pathlib import Path
from product_scraper.checkpoint import Checkpoint, CheckpointError
try:
    with Checkpoint(Path(sys.argv[1]), ["fixture://first"], json.loads(sys.argv[2]), resume=True):
        raise RuntimeError("A second writer acquired the checkpoint")
except CheckpointError as error:
    assert "locked" in str(error) or "in use" in str(error), str(error)
    print("writer excluded")
"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.sqlite3"
            with Checkpoint(path, ["fixture://first"], SETTINGS):
                with self.assertRaisesRegex(CheckpointError, "in use|locked"):
                    with Checkpoint(path, ["fixture://first"], SETTINGS, resume=True):
                        pass
                result = subprocess.run(
                    [sys.executable, "-c", script, str(path), json.dumps(SETTINGS)],
                    cwd=REPOSITORY, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("writer excluded", result.stdout)
            with Checkpoint(path, ["fixture://first"], SETTINGS, resume=True):
                pass

    def test_hard_process_exit_preserves_committed_pages_and_releases_the_lock(self):
        script = """
import json, os, sys
from pathlib import Path
from unittest.mock import patch
from product_scraper.core import scrape_urls
urls = ["fixture://first", "fixture://second"]
def fetch(**kwargs):
    if kwargs["url"] == urls[1]:
        os._exit(37)
    return [{"SourceURL": urls[0], "Title": "Committed before exit", "Price": 12.5, "Rating": None}]
with patch("product_scraper.core.scrape_product_page", side_effect=fetch):
    scrape_urls(urls, checkpoint_path=Path(sys.argv[1]), **json.loads(sys.argv[2]))
"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.sqlite3"
            result = subprocess.run(
                [sys.executable, "-c", script, str(path), json.dumps(SELECTORS)],
                cwd=REPOSITORY, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 37, result.stderr)
            self.assertEqual(read_checkpoint(path).completed, 1)
            with patch(
                "product_scraper.core.scrape_product_page", return_value=product("fixture://second")
            ) as fetch:
                frame = scrape_urls(
                    ["fixture://first", "fixture://second"], checkpoint_path=path,
                    resume=True, **SELECTORS,
                )
            fetch.assert_called_once()
            self.assertEqual(frame["Title"].tolist(), ["Committed before exit", "Saved product"])

    def test_checkpoint_save_errors_stop_the_run_and_preserve_prior_pages(self):
        original_save = Checkpoint.save

        def fail_second(checkpoint, index, rows, error=None):
            if index == 1:
                raise OSError("Synthetic disk failure")
            return original_save(checkpoint, index, rows, error)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.sqlite3"
            with patch(
                "product_scraper.core.scrape_product_page",
                side_effect=lambda **kwargs: product(kwargs["url"]),
            ) as fetch, patch.object(Checkpoint, "save", fail_second):
                with self.assertRaisesRegex(OSError, "Synthetic disk failure"):
                    scrape_urls(
                        ["fixture://first", "fixture://second", "fixture://third"],
                        checkpoint_path=path, **SELECTORS,
                    )
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(read_checkpoint(path).completed, 1)

    def test_cli_interrupt_exports_saved_rows_and_resume_finishes_the_same_run(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            queue = root / "urls.txt"
            urls = ["fixture://first", "fixture://second"]
            queue.write_text("\n".join(urls), encoding="utf-8")
            path = root / "run.sqlite3"
            args = [
                "product-scraper", "--urls-file", str(queue), "--checkpoint", str(path),
                "--output-dir", str(root), "--skip-charts",
            ]
            with patch.object(sys, "argv", args), patch(
                "product_scraper.core.scrape_product_page",
                side_effect=[product(urls[0]), KeyboardInterrupt()],
            ), redirect_stdout(StringIO()):
                self.assertEqual(cli.main(), 130)
            self.assertEqual(len(pd.read_csv(root / "scraped_data.csv")), 1)
            self.assertIn("Run interrupted", (root / "summary_report.txt").read_text(encoding="utf-8"))
            with patch.object(sys, "argv", [*args, "--resume"]), patch(
                "product_scraper.core.scrape_product_page", return_value=product(urls[1])
            ) as fetch, redirect_stdout(StringIO()):
                self.assertEqual(cli.main(), 0)
            fetch.assert_called_once()
            self.assertEqual(len(pd.read_csv(root / "scraped_data.csv")), 2)
            self.assertNotIn("Run interrupted", (root / "summary_report.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
