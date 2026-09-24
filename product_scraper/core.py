import csv
from contextlib import nullcontext
import math
import re
from importlib.resources import files as package_files
from pathlib import Path

from matplotlib.figure import Figure
import pandas as pd
import requests
from bs4 import BeautifulSoup
from soupsieve import compile as compile_selector

from .checkpoint import Checkpoint
from .models import PRODUCT_COLUMNS, ScrapeFailure
from .network import DEFAULT_RETRIES, fetch_html, validate_retries


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


def extract_number(value: str, decimal_separator: str = ".") -> float | None:
    if decimal_separator not in (".", ","):
        raise ValueError("The decimal separator must be '.' or ','.")
    if not value:
        return None

    match = re.search(r"[+-]?(?:\d[\d., \u00a0\u202f]*|[.,]\d+)", value)
    if not match:
        return None

    token = re.sub(r"[ \u00a0\u202f]+", " ", match.group(0)).strip()
    sign = ""
    if token.startswith(("-", "+")):
        sign, token = token[0], token[1:]
    error = (
        f"Cannot parse {value!r} with decimal separator {decimal_separator!r}. "
        "Choose the number format used by the page."
    )
    if token.count(decimal_separator) > 1:
        raise ValueError(error)
    integer, separator, fraction = token.partition(decimal_separator)
    if fraction and not fraction.isdigit():
        raise ValueError(error)

    thousands_separator = "," if decimal_separator == "." else "."
    if thousands_separator in integer and " " in integer:
        raise ValueError(error)
    grouping = thousands_separator if thousands_separator in integer else " "
    if grouping in integer:
        if not re.fullmatch(rf"\d{{1,3}}(?:{re.escape(grouping)}\d{{3}})+", integer):
            raise ValueError(error)
        integer = integer.replace(grouping, "")
    elif integer and not integer.isdigit():
        raise ValueError(error)

    number = float(sign + (integer or "0") + ("." + fraction if separator else ""))
    if not math.isfinite(number):
        raise ValueError(error)
    return number


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
    decimal_separator: str = ".",
    max_retries: int = DEFAULT_RETRIES,
    progress_callback=None,
) -> list[dict]:
    html = fetch_html(session, url, DEFAULT_HEADERS, max_retries, progress_callback)

    return parse_product_html(
        html, url, container_selector, title_selector, price_selector,
        rating_selector, decimal_separator,
    )


def parse_product_html(
    html: str,
    url: str,
    container_selector: str,
    title_selector: str,
    price_selector: str,
    rating_selector: str,
    decimal_separator: str = ".",
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for item in soup.select(container_selector):
        title = text_or_none(item.select_one(title_selector))
        price_text = text_or_none(item.select_one(price_selector))
        rating_text = text_or_none(item.select_one(rating_selector))

        record = {
            "SourceURL": url,
            "Title": title or "Untitled product",
            "Price": extract_number(price_text, decimal_separator),
            "Rating": extract_number(rating_text, decimal_separator),
        }

        if any(value is not None for key, value in record.items() if key != "SourceURL"):
            products.append(record)

    return products


def load_demo() -> pd.DataFrame:
    html = package_files("product_scraper").joinpath("data/catalog.html").read_text(encoding="utf-8")
    rows = parse_product_html(
        html, "demo:catalog", ".product-item", ".product-title",
        ".product-price", ".product-rating",
    )
    return pd.DataFrame(rows, columns=["SourceURL", "Title", "Price", "Rating"])


def scrape_urls(
    urls: list[str],
    container_selector: str,
    title_selector: str,
    price_selector: str,
    rating_selector: str,
    progress_callback=None,
    decimal_separator: str = ".",
    max_retries: int = DEFAULT_RETRIES,
    continue_on_error: bool = False,
    error_callback=None,
    checkpoint_path: Path | None = None,
    resume: bool = False,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Return successful rows; opt into continuation with an error callback."""
    validate_retries(max_retries)
    if decimal_separator not in (".", ","):
        raise ValueError("The decimal separator must be '.' or ','.")
    for selector in (container_selector, title_selector, price_selector, rating_selector):
        compile_selector(selector)
    if continue_on_error and not callable(error_callback):
        raise ValueError("Continuing after a failed URL requires an error callback.")
    if resume and checkpoint_path is None:
        raise ValueError("Resuming requires a checkpoint path.")
    urls = list(urls)
    settings = {
        "container_selector": container_selector, "title_selector": title_selector,
        "price_selector": price_selector, "rating_selector": rating_selector,
        "decimal_separator": decimal_separator,
    }
    all_products = []

    checkpoint_context = (
        Checkpoint(checkpoint_path, urls, settings, resume) if checkpoint_path is not None
        else nullcontext(None)
    )
    with checkpoint_context as checkpoint, (
        requests.Session() if session is None else nullcontext(session)
    ) as active_session:
        for index, url in enumerate(urls, start=1):
            saved = checkpoint.snapshot.pages.get(index - 1) if checkpoint else None
            if saved and saved["status"] == "success":
                all_products.extend(saved["rows"])
                if progress_callback:
                    progress_callback(f"Using saved result for {url} ({index}/{len(urls)}).")
                continue
            if progress_callback:
                progress_callback(f"Scraping {url} ({index}/{len(urls)})...")

            try:
                products = scrape_product_page(
                    session=active_session,
                    url=url,
                    container_selector=container_selector,
                    title_selector=title_selector,
                    price_selector=price_selector,
                    rating_selector=rating_selector,
                    decimal_separator=decimal_separator,
                    max_retries=max_retries,
                    progress_callback=progress_callback,
                )
            except (requests.RequestException, ValueError) as exc:
                failure = ScrapeFailure(url=url, error=f"{type(exc).__name__}: {exc}")
                if checkpoint:
                    checkpoint.save(index - 1, [], failure.error)
                if not continue_on_error:
                    raise
                error_callback(failure)
                if progress_callback:
                    progress_callback(f"  Failed: {failure.error}")
                continue

            if checkpoint:
                checkpoint.save(index - 1, products)
            if progress_callback:
                progress_callback(f"  Found {len(products)} product rows.")

            all_products.extend(products)

    return pd.DataFrame(all_products, columns=PRODUCT_COLUMNS)


def generate_chart(df: pd.DataFrame, column: str, ylabel: str, output_path: Path) -> None:
    chart_df = df.dropna(subset=[column]).sort_values(column, ascending=False).head(20)
    if chart_df.empty:
        return

    figure = Figure(figsize=(12, 6))
    axes = figure.subplots()
    axes.bar(chart_df["Title"], chart_df[column], color="#357b68")
    axes.tick_params(axis="x", labelrotation=55)
    for tick in axes.get_xticklabels():
        tick.set_ha("right")
    axes.set_title(f"{column} by Product")
    axes.set_ylabel(ylabel)
    figure.tight_layout()
    figure.savefig(output_path)


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


def write_outputs(
    df: pd.DataFrame,
    output_dir: Path,
    skip_charts: bool,
    failures: list[ScrapeFailure] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {}
    csv_path = output_dir / "scraped_data.csv"
    df.to_csv(csv_path, index=False)
    files["csv"] = csv_path

    for column, key in (("Price", "price_chart"), ("Rating", "rating_chart")):
        chart_path = output_dir / f"{key}.png"
        if skip_charts or df[column].dropna().empty:
            # Never leave a previous run's chart beside the current CSV.
            chart_path.unlink(missing_ok=True)
        else:
            generate_chart(df, column, column, chart_path)
            files[key] = chart_path

    failures = failures or []
    errors_path = output_dir / "failed_urls.csv"
    with errors_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["SourceURL", "Error"])
        writer.writerows((failure.url, failure.error) for failure in failures)
    files["errors"] = errors_path

    summary = build_summary(df) + f"\nURLs failed: {len(failures)}\n"
    if failures:
        summary += "See failed_urls.csv for individual errors.\n"
    summary_path = output_dir / "summary_report.txt"
    summary_path.write_text(summary, encoding="utf-8")
    files["summary"] = summary_path

    return files
