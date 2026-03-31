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


def normalize_urls(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def load_urls(urls_file: Path) -> list[str]:
    if not urls_file.exists():
        raise FileNotFoundError(f"URLs file not found: {urls_file}")

    return normalize_urls(urls_file.read_text(encoding="utf-8").splitlines())


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


def scrape_urls(
    urls: list[str],
    container_selector: str,
    title_selector: str,
    price_selector: str,
    rating_selector: str,
    progress_callback=None,
) -> pd.DataFrame:
    session = requests.Session()
    all_products = []

    for index, url in enumerate(urls, start=1):
        if progress_callback:
            progress_callback(f"Scraping {url} ({index}/{len(urls)})...")

        products = scrape_product_page(
            session=session,
            url=url,
            container_selector=container_selector,
            title_selector=title_selector,
            price_selector=price_selector,
            rating_selector=rating_selector,
        )

        if progress_callback:
            progress_callback(f"  Found {len(products)} product rows.")

        all_products.extend(products)

    return pd.DataFrame(all_products, columns=["SourceURL", "Title", "Price", "Rating"])


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


def write_outputs(df: pd.DataFrame, output_dir: Path, skip_charts: bool) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {}
    csv_path = output_dir / "scraped_data.csv"
    df.to_csv(csv_path, index=False)
    files["csv"] = csv_path

    if not skip_charts and not df.empty:
        price_chart = output_dir / "price_chart.png"
        rating_chart = output_dir / "rating_chart.png"
        generate_chart(df, "Price", "Price", price_chart)
        generate_chart(df, "Rating", "Rating", rating_chart)
        if price_chart.exists():
            files["price_chart"] = price_chart
        if rating_chart.exists():
            files["rating_chart"] = rating_chart

    summary = build_summary(df)
    summary_path = output_dir / "summary_report.txt"
    summary_path.write_text(summary, encoding="utf-8")
    files["summary"] = summary_path

    return files
