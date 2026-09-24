"""Compatibility launcher; prefer the product-scraper command."""
from product_scraper.cli import build_parser, main

if __name__ == "__main__":
    raise SystemExit(main())
