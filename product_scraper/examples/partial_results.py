"""Retain good pages and handle individual failures through a callback."""

import argparse
from pathlib import Path

from ..core import scrape_urls, write_outputs
from ._fixtures import SELECTORS, FixturePage, catalog_html, fixture_session, product_html


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("example-output/partial-results"))
    args = parser.parse_args(argv)
    urls = ["fixture://catalog/good", "fixture://catalog/missing", "fixture://catalog/bad-number"]
    pages = {
        urls[0]: FixturePage(catalog_html()),
        urls[1]: FixturePage("", 404),
        urls[2]: FixturePage(product_html("Malformed fixture price", "$12,34.50")),
    }
    failures = []

    def report_failure(failure):
        failures.append(failure)
        print(f"Handled {failure.url}: {failure.error}")

    print("Offline example: two fixture pages intentionally fail.")
    with fixture_session(pages) as (session, _):
        frame = scrape_urls(
            urls, session=session, max_retries=0, continue_on_error=True,
            error_callback=report_failure, **SELECTORS,
        )
    outputs = write_outputs(frame, args.output_dir, skip_charts=True, failures=failures)
    print(f"Retained {len(frame)} product rows; handled {len(failures)} expected fixture failures.")
    print(f"CSV: {outputs['csv']}")
    print(f"Errors: {outputs['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
