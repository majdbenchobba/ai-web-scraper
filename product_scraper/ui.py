import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import requests
from soupsieve import SelectorSyntaxError

from .core import DEFAULT_OUTPUT_DIR, scrape_urls, write_outputs


class ScraperApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Product Web Scraper")
        self.root.geometry("980x720")

        self.urls_text = None
        self.output_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.container_var = tk.StringVar(value=".product-item")
        self.title_var = tk.StringVar(value=".product-title")
        self.price_var = tk.StringVar(value=".product-price")
        self.rating_var = tk.StringVar(value=".product-rating")
        self.decimal_var = tk.StringVar(value=".")
        self.skip_charts_var = tk.BooleanVar(value=False)
        self.preview_table = None
        self.log_box = None

        self._build_layout()

    def _build_layout(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="URLs (one per line)").grid(row=0, column=0, sticky="w")
        self.urls_text = scrolledtext.ScrolledText(frame, height=7, wrap="word")
        self.urls_text.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(4, 12))

        ttk.Label(frame, text="Container selector").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.container_var).grid(row=3, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(frame, text="Title selector").grid(row=2, column=1, sticky="w")
        ttk.Entry(frame, textvariable=self.title_var).grid(row=3, column=1, sticky="ew", padx=(0, 8))

        ttk.Label(frame, text="Price selector").grid(row=2, column=2, sticky="w")
        ttk.Entry(frame, textvariable=self.price_var).grid(row=3, column=2, sticky="ew", padx=(0, 8))

        ttk.Label(frame, text="Rating selector").grid(row=2, column=3, sticky="w")
        ttk.Entry(frame, textvariable=self.rating_var).grid(row=3, column=3, sticky="ew")

        ttk.Label(frame, text="Output folder").grid(row=4, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(frame, textvariable=self.output_var).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        ttk.Button(frame, text="Browse", command=self.pick_output_dir).grid(row=5, column=3, sticky="ew", padx=(8, 0))

        ttk.Checkbutton(frame, text="Skip chart images", variable=self.skip_charts_var).grid(
            row=6, column=0, sticky="w", pady=(12, 12)
        )
        ttk.Label(frame, text="Decimal separator").grid(row=6, column=1, sticky="e")
        ttk.Combobox(
            frame, textvariable=self.decimal_var, values=(".", ","), state="readonly", width=5
        ).grid(row=6, column=2, sticky="w", padx=8)

        button_row = ttk.Frame(frame)
        button_row.grid(row=7, column=0, columnspan=4, sticky="ew")
        ttk.Button(button_row, text="Preview first URL", command=self.preview).pack(side="left")
        ttk.Button(button_row, text="Run scrape", command=self.run_scrape).pack(side="left", padx=(8, 0))

        ttk.Label(frame, text="Preview").grid(row=8, column=0, sticky="w", pady=(12, 4))
        columns = ("SourceURL", "Title", "Price", "Rating")
        self.preview_table = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        for column in columns:
            self.preview_table.heading(column, text=column)
            width = 180 if column != "Title" else 360
            self.preview_table.column(column, width=width, anchor="w")
        self.preview_table.grid(row=9, column=0, columnspan=4, sticky="nsew")

        ttk.Label(frame, text="Log").grid(row=10, column=0, sticky="w", pady=(12, 4))
        self.log_box = scrolledtext.ScrolledText(frame, height=10, wrap="word", state="disabled")
        self.log_box.grid(row=11, column=0, columnspan=4, sticky="nsew")

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(9, weight=1)
        frame.rowconfigure(11, weight=1)

    def pick_output_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.output_var.get() or str(DEFAULT_OUTPUT_DIR))
        if chosen:
            self.output_var.set(chosen)

    def get_urls(self) -> list[str]:
        raw = self.urls_text.get("1.0", "end").splitlines()
        urls = [line.strip() for line in raw if line.strip() and not line.strip().startswith("#")]
        return urls

    def append_log(self, message: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_preview(self):
        for row_id in self.preview_table.get_children():
            self.preview_table.delete(row_id)

    def show_preview(self, rows):
        self.clear_preview()
        for row in rows:
            self.preview_table.insert(
                "",
                "end",
                values=(
                    row.get("SourceURL", ""),
                    row.get("Title", ""),
                    row.get("Price", ""),
                    row.get("Rating", ""),
                ),
            )

    def selectors(self) -> dict[str, str]:
        return {
            "container_selector": self.container_var.get().strip(),
            "title_selector": self.title_var.get().strip(),
            "price_selector": self.price_var.get().strip(),
            "rating_selector": self.rating_var.get().strip(),
            "decimal_separator": self.decimal_var.get(),
        }

    def report_progress(self, message: str):
        self.root.after(0, lambda text=message: self.append_log(text))

    def preview(self):
        urls = self.get_urls()
        if not urls:
            messagebox.showerror("Missing URL", "Add at least one URL first.")
            return

        self.append_log("Previewing the first URL...")
        options = self.selectors()

        def worker():
            try:
                df = scrape_urls(urls[:1], progress_callback=self.report_progress, **options)
            except (requests.RequestException, ValueError, OSError, SelectorSyntaxError) as exc:
                self.root.after(
                    0, lambda message=str(exc): messagebox.showerror("Preview failed", message)
                )
                return

            preview_rows = df.head(20).to_dict("records")
            self.root.after(0, lambda: self.show_preview(preview_rows))

        threading.Thread(target=worker, daemon=True).start()

    def run_scrape(self):
        urls = self.get_urls()
        if not urls:
            messagebox.showerror("Missing URL", "Add at least one URL first.")
            return

        output_dir = Path(self.output_var.get().strip() or DEFAULT_OUTPUT_DIR)
        options = self.selectors()
        skip_charts = self.skip_charts_var.get()
        self.append_log(f"Running scrape for {len(urls)} URL(s)...")

        def worker():
            failures = []
            try:
                df = scrape_urls(
                    urls, progress_callback=self.report_progress, continue_on_error=True,
                    error_callback=failures.append, **options,
                )
                files = write_outputs(df, output_dir, skip_charts, failures)
            except (requests.RequestException, ValueError, OSError, SelectorSyntaxError) as exc:
                self.root.after(
                    0, lambda message=str(exc): messagebox.showerror("Scrape failed", message)
                )
                return

            preview_rows = df.head(20).to_dict("records")

            def finish():
                self.show_preview(preview_rows)
                self.append_log(f"Saved CSV to {files['csv']}")
                self.append_log(f"Saved summary to {files['summary']}")
                self.append_log(f"Saved URL errors to {files['errors']}")
                if "price_chart" in files:
                    self.append_log(f"Saved price chart to {files['price_chart']}")
                if "rating_chart" in files:
                    self.append_log(f"Saved rating chart to {files['rating_chart']}")
                if failures:
                    title = "All URLs failed" if len(failures) == len(urls) else "Completed with errors"
                    messagebox.showwarning(
                        title,
                        f"Saved {len(df)} row(s). {len(failures)}/{len(urls)} URLs failed.\n"
                        f"See {files['errors']} for details.",
                    )
                else:
                    messagebox.showinfo("Done", f"Finished scraping {len(df)} row(s).")

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


def main():
    root = tk.Tk()
    app = ScraperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
