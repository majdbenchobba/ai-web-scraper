import argparse
from pathlib import Path

import requests
from scraper_core import DEFAULT_OUTPUT_DIR, DEFAULT_URLS_FILE, load_urls, scrape_urls, write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape product cards from URLs and generate CSV, charts, and a text summary."
    )
    parser.add_argument("--urls-file", type=Path, default=DEFAULT_URLS_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--container-selector", default=".product-item")
    parser.add_argument("--title-selector", default=".product-title")
    parser.add_argument("--price-selector", default=".product-price")
    parser.add_argument("--rating-selector", default=".product-rating")
    parser.add_argument(
        "--skip-charts",
        action="store_true",
        help="Skip generating chart images.",
    )
    return parser

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        urls = load_urls(args.urls_file)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    if not urls:
        print("No URLs found in the URLs file.")
        return 1

    try:
        df = scrape_urls(
            urls=urls,
            container_selector=args.container_selector,
            title_selector=args.title_selector,
            price_selector=args.price_selector,
            rating_selector=args.rating_selector,
            progress_callback=print,
        )
    except requests.RequestException as exc:
        print(f"Scrape failed: {exc}")
        return 1

    files = write_outputs(df, args.output_dir, args.skip_charts)
    print(f"Scraped data saved to: {files['csv']}")
    print(f"Summary saved to: {files['summary']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
