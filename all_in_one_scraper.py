import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests
from bs4 import BeautifulSoup


DEFAULT_URLS_FILE = Path("sample_urls.txt")
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
}


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


def load_urls(urls_file: Path) -> list[str]:
    if not urls_file.exists():
        raise FileNotFoundError(f"URLs file not found: {urls_file}")

    urls = [line.strip() for line in urls_file.read_text(encoding="utf-8").splitlines()]
    return [url for url in urls if url and not url.startswith("#")]


def extract_number(value: str) -> float | None:
    if not value:
        return None

    match = re.search(r"-?\d[\d,]*\.?\d*", value.replace(" ", ""))
    if not match:
        return None

    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def text_or_none(element) -> str | None:
    if element is None:
        return None
    text = element.get_text(" ", strip=True)
    return text or None


def scrape_product_page(
    session: requests.Session,
    url: str,
    container_selector: str,
    title_selector: str,
    price_selector: str,
    rating_selector: str,
) -> list[dict]:
    response = session.get(url, headers=DEFAULT_HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    products = []

    for item in soup.select(container_selector):
        title = text_or_none(item.select_one(title_selector))
        price_text = text_or_none(item.select_one(price_selector))
        rating_text = text_or_none(item.select_one(rating_selector))

        record = {
            "SourceURL": url,
            "Title": title or "Untitled product",
            "Price": extract_number(price_text),
            "Rating": extract_number(rating_text),
        }

        if any(value is not None for key, value in record.items() if key != "SourceURL"):
            products.append(record)

    return products


def generate_chart(df: pd.DataFrame, column: str, ylabel: str, output_path: Path) -> None:
    chart_df = df.dropna(subset=[column]).sort_values(column, ascending=False).head(20)
    if chart_df.empty:
        return

    plt.figure(figsize=(12, 6))
    plt.bar(chart_df["Title"], chart_df[column])
    plt.xticks(rotation=75, ha="right")
    plt.title(f"{column} by Product")
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def build_summary(df: pd.DataFrame) -> str:
    lines = [f"Products scraped: {len(df)}"]

    price_df = df.dropna(subset=["Price"])
    if not price_df.empty:
        lines.append(f"Average price: {price_df['Price'].mean():.2f}")
        lines.append(f"Highest price: {price_df['Price'].max():.2f}")
        lines.append("")
        lines.append("Top 5 most expensive products:")
        for _, row in price_df.sort_values("Price", ascending=False).head(5).iterrows():
            lines.append(f"- {row['Title']}: {row['Price']:.2f}")

    rating_df = df.dropna(subset=["Rating"])
    if not rating_df.empty:
        if lines[-1] != "":
            lines.append("")
        lines.append(f"Average rating: {rating_df['Rating'].mean():.2f}")
        lines.append(f"Highest rating: {rating_df['Rating'].max():.2f}")
        lines.append("")
        lines.append("Top 5 highest rated products:")
        for _, row in rating_df.sort_values("Rating", ascending=False).head(5).iterrows():
            lines.append(f"- {row['Title']}: {row['Rating']:.2f}")

    if price_df.empty and rating_df.empty:
        lines.append("No numeric price or rating values were detected.")

    return "\n".join(lines).strip() + "\n"


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

    args.output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    all_products = []

    for url in urls:
        print(f"Scraping {url}...")
        try:
            products = scrape_product_page(
                session=session,
                url=url,
                container_selector=args.container_selector,
                title_selector=args.title_selector,
                price_selector=args.price_selector,
                rating_selector=args.rating_selector,
            )
        except requests.RequestException as exc:
            print(f"Failed to scrape {url}: {exc}")
            continue

        print(f"  Found {len(products)} product rows.")
        all_products.extend(products)

    df = pd.DataFrame(all_products, columns=["SourceURL", "Title", "Price", "Rating"])
    csv_path = args.output_dir / "scraped_data.csv"
    df.to_csv(csv_path, index=False)
    print(f"Scraped data saved to: {csv_path}")

    if not args.skip_charts and not df.empty:
        generate_chart(df, "Price", "Price", args.output_dir / "price_chart.png")
        generate_chart(df, "Rating", "Rating", args.output_dir / "rating_chart.png")

    summary = build_summary(df)
    summary_path = args.output_dir / "summary_report.txt"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"Summary saved to: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
