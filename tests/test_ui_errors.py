import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ui


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


if __name__ == "__main__":
    unittest.main()
