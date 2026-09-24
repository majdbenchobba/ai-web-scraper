import sys
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from soupsieve import SelectorSyntaxError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_scraper import ui
from product_scraper.core import ScrapeFailure, load_demo
from product_scraper.checkpoint import Checkpoint


class ImmediateWorker:
    def __init__(self, target, daemon):
        self.target = target

    def start(self):
        self.target()


class ScraperErrorDialogTest(unittest.TestCase):
    def test_deferred_error_dialog_keeps_the_exception_message(self):
        for action in ("preview", "run_scrape"):
            for error in (
                requests.RequestException("Synthetic timeout"),
                ValueError("Choose the number format used by the page."),
                OSError("Synthetic output folder error"),
                SelectorSyntaxError("Invalid CSS selector"),
            ):
                with self.subTest(action=action, error=type(error).__name__):
                    app = Mock()
                    app.get_urls.return_value = ["https://example.test/products"]
                    app.selectors.return_value = {"decimal_separator": ","}
                    app.output_var.get.return_value = "output"
                    callbacks = []
                    app.root.after.side_effect = (
                        lambda delay, callback: callbacks.append(callback)
                    )
                    with patch.object(ui, "scrape_urls", side_effect=error), patch.object(
                        ui.threading, "Thread", ImmediateWorker
                    ):
                        getattr(ui.ScraperApp, action)(app)
                    with patch.object(ui.messagebox, "showerror") as dialog:
                        for callback in callbacks:
                            callback()
                        expected_title = "Preview failed" if action == "preview" else "Scrape failed"
                        dialog.assert_called_once_with(expected_title, str(error))

    def test_worker_progress_waits_for_the_ui_event_loop(self):
        app = Mock()
        callbacks = []
        app.root.after.side_effect = lambda delay, callback: callbacks.append(callback)
        ui.ScraperApp.report_progress(app, "One page finished")
        app.append_log.assert_not_called()
        callbacks[0]()
        app.append_log.assert_called_once_with("One page finished")

    def test_partial_and_total_url_failures_show_warnings_instead_of_success(self):
        for all_failed in (False, True):
            with self.subTest(all_failed=all_failed), TemporaryDirectory() as directory:
                app = Mock()
                app.get_urls.return_value = ["https://example.test/first", "https://example.test/second"]
                app.selectors.return_value = {}
                app.output_var.get.return_value = directory
                app.skip_charts_var.get.return_value = True
                callbacks = []
                app.root.after.side_effect = lambda delay, callback: callbacks.append(callback)

                def scrape(urls, *, error_callback, **options):
                    error_callback(ScrapeFailure(urls[0], "HTTPError: 404"))
                    if all_failed:
                        error_callback(ScrapeFailure(urls[1], "Timeout: request timed out"))
                    return load_demo().head(0 if all_failed else 1)

                with patch.object(ui, "scrape_urls", side_effect=scrape), patch.object(
                    ui.threading, "Thread", ImmediateWorker
                ), patch.object(ui.messagebox, "showwarning") as warning, patch.object(
                    ui.messagebox, "showinfo"
                ) as success:
                    ui.ScraperApp.run_scrape(app)
                    for callback in callbacks:
                        callback()
                    warning.assert_called_once()
                    self.assertEqual(
                        warning.call_args.args[0],
                        "All URLs failed" if all_failed else "Completed with errors",
                    )
                    self.assertIn("failed_urls.csv", warning.call_args.args[1])
                    success.assert_not_called()

    def test_resume_restores_saved_urls_and_selectors_before_starting_the_worker(self):
        urls = ["fixture://saved/first", "fixture://saved/second"]
        settings = {
            "container_selector": ".saved-card", "title_selector": ".saved-title",
            "price_selector": ".saved-price", "rating_selector": ".saved-rating",
            "decimal_separator": ",",
        }
        with TemporaryDirectory() as directory:
            checkpoint_path = Path(directory) / "scrape-checkpoint.sqlite3"
            with Checkpoint(checkpoint_path, urls, settings):
                pass
            app = Mock()
            app.output_var.get.return_value = directory
            app.skip_charts_var.get.return_value = True
            callbacks = []
            app.root.after.side_effect = lambda delay, callback: callbacks.append(callback)
            with patch.object(ui, "scrape_urls", return_value=load_demo()) as scrape, patch.object(
                ui.threading, "Thread", ImmediateWorker
            ), patch.object(ui.messagebox, "showinfo"):
                ui.ScraperApp.run_scrape(app, resume=True)
                for callback in callbacks:
                    callback()
            app.get_urls.assert_not_called()
            app.urls_text.insert.assert_called_once_with("1.0", "\n".join(urls))
            app.container_var.set.assert_called_once_with(".saved-card")
            app.decimal_var.set.assert_called_once_with(",")
            self.assertEqual(scrape.call_args.args[0], urls)
            self.assertTrue(scrape.call_args.kwargs["resume"])
            self.assertEqual(scrape.call_args.kwargs["checkpoint_path"], checkpoint_path)
            for name, value in settings.items():
                self.assertEqual(scrape.call_args.kwargs[name], value)

    def test_missing_saved_run_does_not_start_a_worker_or_create_a_checkpoint(self):
        with TemporaryDirectory() as directory:
            app = Mock()
            app.output_var.get.return_value = directory
            with patch.object(ui.messagebox, "showerror") as error, patch.object(
                ui.threading, "Thread"
            ) as thread:
                ui.ScraperApp.run_scrape(app, resume=True)
            self.assertEqual(error.call_args.args[0], "Cannot resume")
            thread.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
