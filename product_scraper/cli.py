import argparse
from pathlib import Path

import requests
from soupsieve import SelectorSyntaxError

from . import __version__
from .core import DEFAULT_OUTPUT_DIR, load_demo, load_urls, scrape_urls, write_outputs
from .network import DEFAULT_RETRIES, MAX_RETRIES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape product cards from URLs and generate CSV, charts, and a text summary."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true", help="Run the bundled fictional catalog without network access.")
    source.add_argument("--urls-file", type=Path, help="Read permitted product-page URLs from this file.")
    parser.add_argument("--version", action="version", version=f"Product Web Scraper {__version__}")
    parser.add_argument("--output-dir", type=Path, help="Output folder (default: demo-output for the demo, output otherwise).")
    parser.add_argument("--container-selector", default=".product-item")
    parser.add_argument("--title-selector", default=".product-title")
    parser.add_argument("--price-selector", default=".product-price")
    parser.add_argument("--rating-selector", default=".product-rating")
    parser.add_argument(
        "--retries", type=int, choices=range(MAX_RETRIES + 1), default=DEFAULT_RETRIES,
        help=f"Additional attempts for transient GET failures (default: {DEFAULT_RETRIES}, maximum: {MAX_RETRIES}).",
    )
    parser.add_argument(
        "--decimal-separator",
        choices=(".", ","),
        default=".",
        help="Decimal separator used in the page's prices and ratings (default: .).",
    )
    parser.add_argument(
        "--skip-charts",
        action="store_true",
        help="Skip generating chart images.",
    )
    return parser

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    failures = []
    urls = []

    try:
        if args.demo:
            print("Offline demo: fictional products, prices, and ratings. No network requests.")
            df = load_demo()
            output_dir = args.output_dir or Path("demo-output")
        else:
            urls = load_urls(args.urls_file)
            if not urls:
                print("No URLs found in the URLs file.")
                return 1
            df = scrape_urls(
                urls=urls,
                container_selector=args.container_selector,
                title_selector=args.title_selector,
                price_selector=args.price_selector,
                rating_selector=args.rating_selector,
                decimal_separator=args.decimal_separator,
                progress_callback=print,
                max_retries=args.retries,
                continue_on_error=True,
                error_callback=failures.append,
            )
            output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
        files = write_outputs(df, output_dir, args.skip_charts, failures)
    except (requests.RequestException, ValueError, OSError, SelectorSyntaxError) as exc:
        print(f"Scrape failed: {exc}")
        return 1

    print(f"Products extracted: {len(df)}")
    print(f"Scraped data saved to: {files['csv']}")
    print(f"Summary saved to: {files['summary']}")
    print(f"URL errors saved to: {files['errors']}")
    for key in ("price_chart", "rating_chart"):
        if key in files:
            print(f"Chart saved to: {files[key]}")

    if failures:
        print(f"URLs failed: {len(failures)}/{len(urls)}. Product rows saved: {len(df)}.")
        return 1 if len(failures) == len(urls) else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
