# Changelog

## 0.3.0

- Per-URL SQLite checkpoints that preserve completed pages across interruptions
  and abrupt process exit. Resume skips successes and retries failed or pending
  pages without duplicating rows.
- Strict URL/order/selector/decimal matching and exclusive process ownership
  protect saved runs from incompatible or concurrent writes.
- CLI `--checkpoint` / `--resume`, partial export on `Ctrl+C`, and desktop
  progress saving with a button that restores and resumes the saved run.
- Caller-owned Requests sessions and three packaged, runnable offline API
  examples for selectors, partial results, and checkpoint recovery.
- Windows CI coverage alongside the Linux Python matrix.

## 0.2.0

- Bounded retries for transient GET failures, with exponential backoff and
  `Retry-After` handling that never retries earlier than the server requests.
- CLI and desktop batch runs retain successful pages and export individual
  failures to `failed_urls.csv`.
- Distinct CLI status for partial results; desktop warnings for partial and
  total failures.
- Configuration validation before requests, session cleanup, and removal of
  stale charts when a new run has no chart data.
- Offline regression coverage for recovery, retry exhaustion, HTTP errors,
  certificate errors, parse failures, and partial-result reporting.

## 0.1.0

- Installable `product-scraper` command and `product-scraper-gui` launcher.
- Bundled fictional catalog for an offline, one-command demonstration.
- CSV, summary, and chart output from the same parsing pipeline as URL scraping.
- Explicit decimal-separator selection and validation of number grouping.
- Deferred UI errors retain their messages; progress is queued to the UI loop.
- Legacy Python launch scripts remain available from a source checkout.

This is an initial release for selector-driven product pages. It does not
render JavaScript pages or automatically determine selectors.
