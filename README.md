# Product Web Scraper

[![Python tests](https://github.com/majdbenchobba/ai-web-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/majdbenchobba/ai-web-scraper/actions/workflows/tests.yml)

Extract products from HTML with explicit CSS selectors, then save a CSV, summary,
and charts. Try the bundled fictional catalog without visiting a website.

## Install

Python 3.11 or newer is required. Install the v0.3.0 wheel in a virtual environment:

```bash
python -m pip install "https://github.com/majdbenchobba/ai-web-scraper/releases/download/v0.3.0/majd_product_scraper-0.3.0-py3-none-any.whl"
```

Or install the downloaded wheel from the [release page](https://github.com/majdbenchobba/ai-web-scraper/releases/tag/v0.3.0):

```bash
python -m pip install ./majd_product_scraper-0.3.0-py3-none-any.whl
```

## Try it in one command

```bash
product-scraper --demo
```

The offline demo reads eight fictional products bundled with the package and
writes these files to `demo-output/`:

- `scraped_data.csv`
- `summary_report.txt`
- `price_chart.png`
- `rating_chart.png`
- `failed_urls.csv` (a header-only report when there are no failed URLs)

No network requests are made in demo mode. Products, prices, and ratings are
invented demonstration data, not real offers.

![Price chart generated from the fictional offline catalog](docs/demo-price-chart.png)

Choose another directory or skip charts:

```bash
product-scraper --demo --output-dir my-demo --skip-charts
```

The demo uses its fixed catalog selectors and dot-decimal format. Custom selector
and number-format options apply to URL scraping.

## Scrape an HTML product page

Put URLs you are authorized to scrape in `my_urls.txt`, one per line, then use
selectors matching that site's product cards:

```bash
product-scraper --urls-file my_urls.txt --container-selector ".product-item" --title-selector ".product-title" --price-selector ".product-price" --rating-selector ".product-rating"
```

The default output directory for URL scraping is `output/`. A URL file is required;
the program does not silently request placeholder websites.

This is a selector-driven HTML tool. It does not run browser JavaScript, discover
selectors automatically, or bypass access controls.

## Retries and partial results

URL runs retry connection failures, timeouts, and HTTP 408, 429, 500, 502, 503,
and 504 up to twice after the initial attempt. Other HTTP errors and certificate
errors are reported without retries. Adjust the number of additional attempts
from zero to five:

```bash
product-scraper --urls-file my_urls.txt --retries 0
```

Retries use exponential backoff. A server's `Retry-After` header is honored up to
a 30-second wait. If the server requests a longer wait, the URL is reported as
failed for a later run rather than retried early.

The CLI and desktop **Run scrape** action keep successful pages even if another
URL fails. `failed_urls.csv` records each failed URL and its request or parsing
error; the summary includes the failure count. Invalid selectors and global
configuration errors stop the run before requests are made.

| CLI exit code | Meaning |
| --- | --- |
| `0` | All URLs completed without errors, or the offline demo succeeded |
| `1` | Every URL failed, or setup/output failed |
| `2` | Invalid command-line arguments |
| `3` | Some URLs failed; successful product rows and the error report were saved |

Each run replaces its error report, including when there are no failures.
Charts from a previous run are removed when charts are skipped or the current
data has no values for that chart.

Python callers still receive a DataFrame from `scrape_urls`. Its default preserves
fail-fast behavior after retries. Batch continuation requires
`continue_on_error=True` and an `error_callback`, such as `failures.append`, so
partial results cannot silently discard errors.

## Checkpoint and resume

Enable durable progress for a URL run:

```bash
product-scraper --urls-file my_urls.txt --checkpoint output/scrape-checkpoint.sqlite3
```

Each successfully parsed URL is committed to SQLite before the next URL starts,
including pages with zero matching products. A failed URL is recorded separately.
If the process is interrupted, resume with the same URL file and extraction options:

```bash
product-scraper --urls-file my_urls.txt --checkpoint output/scrape-checkpoint.sqlite3 --resume
```

Resume reuses saved successful rows and retries failed or unfinished URLs. Results
stay in input order, including intentional duplicate URL occurrences. URLs, their
order, selectors, and decimal format must match the saved run. Retry count, chart
choice, and output directory may change.

A new run never overwrites an existing checkpoint. Choose a new checkpoint path
for a fresh scrape or changed selectors. Resuming a completed checkpoint reuses its
data; it does not refresh successful pages.

`Ctrl+C` returns exit code `130`. When a checkpoint is enabled, committed rows are
also exported to the usual reports where possible. After an abrupt process exit,
the checkpoint still holds completed pages; resume regenerates the reports.

Keep checkpoints on local disk. A small `.lock` sidecar prevents concurrent writers
and may remain after a run; ownership is released automatically when the process
exits. Close a run before moving its checkpoint.

In Python, pass `checkpoint_path=Path("run.sqlite3")` and later `resume=True`
to `scrape_urls`. `product_scraper.checkpoint.read_checkpoint` reads the saved
URLs, extraction settings, rows, and failure information without changing the file.
If a process stopped during a database write, `recover_checkpoint` acquires the
writer lock and lets SQLite recover the interrupted transaction before reading.
The CLI and desktop resume paths perform this recovery automatically.

## Runnable offline API examples

These examples are included in the installed wheel and run from any directory:

```bash
python -m product_scraper.examples.selectors
python -m product_scraper.examples.partial_results
python -m product_scraper.examples.checkpoint_resume
```

- `selectors` parses the bundled fictional HTML with explicit selectors.
- `partial_results` retains eight product rows while handling two deliberately
  failed fixtures through an error callback.
- `checkpoint_resume` simulates an interruption and resumes three fixture pages
  without requesting the completed page again.

The examples write to separate folders under `example-output/`; each accepts
`--output-dir`. The checkpoint example uses a fresh checkpoint name on each run.
Its in-memory `fixture://` transport has no HTTP adapters and cannot access real
websites.

For integrations, `scrape_urls(session=...)` accepts a caller-owned Requests
session. The caller controls its lifetime; the scraper only closes sessions it
creates itself. See the [example source](product_scraper/examples) for complete
selector, callback, transport, and resume code.

## Number formats

The default decimal separator is `.`: `$1,249.50` becomes `1249.5`.
For pages using a decimal comma, pass `--decimal-separator ","`. Both
`1 249,50 EUR` and `1.249,50 EUR` then become `1249.5`; a rating of `4,7 / 5`
becomes `4.7`.

The setting applies to prices and ratings. Thousands groups must contain three
digits. A value such as `1,249` follows the explicit setting: `1249` with decimal
`.` and `1.249` with decimal `,`. Use separate runs for different number formats.

## Desktop interface

```bash
product-scraper-gui
```

The desktop interface needs Tkinter, included with standard Python installers on
Windows and macOS. Some Linux distributions package it separately. It supports
URL entry, selector and decimal-format settings, preview, and export.

**Save progress** is enabled by default for desktop batch runs and writes
`scrape-checkpoint.sqlite3` in the selected output folder. **Resume saved run**
restores the saved URLs and selectors, then continues unfinished work. Choose a
different output folder for a new checkpoint, or switch off **Save progress**
to run without one.

## Source checkout and tests

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m product_scraper --demo
```

Legacy launch commands remain available from the repository:

```bash
python all_in_one_scraper.py --demo
python ui.py
```

CI runs the tests on Linux with Python 3.11, 3.12, and 3.13, plus Windows with
Python 3.13. It builds and checks the wheel/source archive and runs the installed
wheel's demo and API examples outside the checkout.
Tests use local fixtures and mocked requests.

## Responsible use

Use URL scraping only where you have permission. Follow the site's terms and
request limits, and avoid personal data or authenticated pages.

Released under the MIT license. See [CHANGELOG.md](CHANGELOG.md) for v0.3.0.
