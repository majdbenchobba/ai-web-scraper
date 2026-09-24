# Changelog

## 0.1.0

- Installable `product-scraper` command and `product-scraper-gui` launcher.
- Bundled fictional catalog for an offline, one-command demonstration.
- CSV, summary, and chart output from the same parsing pipeline as URL scraping.
- Explicit decimal-separator selection and validation of number grouping.
- Deferred UI errors retain their messages; progress is queued to the UI loop.
- Legacy Python launch scripts remain available from a source checkout.

This is an initial release for selector-driven product pages. It does not
render JavaScript pages or automatically determine selectors.
