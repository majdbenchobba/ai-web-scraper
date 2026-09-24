# Product Web Scraper and Analyzer

[![Python tests](https://github.com/majdbenchobba/ai-web-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/majdbenchobba/ai-web-scraper/actions/workflows/tests.yml)

Simple Python scraper for product-listing pages.

It works by:

1. loading one or more URLs
2. finding repeated product containers with a CSS selector
3. pulling title, price, and rating values from each container using more CSS selectors
4. saving the result to CSV and optional charts

That means this is not a generic "scrape any site automatically" tool. It works best on pages with a repeated product-card layout where you already know, or can inspect, the selectors you want.

## Install

```bash
pip install -r requirements.txt
```

## Basic use

1. Put the URLs in `sample_urls.txt`
2. Run the script with selectors for the site you want

Example:

```bash
python all_in_one_scraper.py ^
  --container-selector ".product-item" ^
  --title-selector ".product-title" ^
  --price-selector ".product-price" ^
  --rating-selector ".product-rating"
```

PowerShell version:

```powershell
python .\all_in_one_scraper.py `
  --container-selector ".product-item" `
  --title-selector ".product-title" `
  --price-selector ".product-price" `
  --rating-selector ".product-rating"
```

## UI

There is also a small desktop UI:

```bash
python ui.py
```

The UI fits the current scraper model:

- you paste one or more URLs
- you enter the CSS selectors for the container/title/price/rating fields
- you preview the first URL
- then you run the full scrape

Select the page's decimal separator in the UI before previewing or scraping.

## Number formats

The default decimal separator is `.`: `$1,249.50` becomes `1249.5`.
For pages using a decimal comma, pass `--decimal-separator ","` or choose `,`
in the desktop UI. Both `1 249,50 EUR` and `1.249,50 EUR` then become `1249.5`,
and a rating of `4,7 / 5` becomes `4.7`.

The setting applies to prices and ratings. Thousands groups must contain three
digits. Incompatible or malformed formats stop the scrape with an error, so
an incorrect number format cannot silently inflate prices. A value such as
`1,249` is interpreted according to the explicit setting: `1249` with decimal
`.` and `1.249` with decimal `,`. Use separate runs for pages with different
number formats.

## Output

The script writes:

- `scraped_data.csv`
- `price_chart.png`
- `rating_chart.png`
- `summary_report.txt`

into the output folder.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use synthetic HTML and local temporary files; they do not access an
external website.

## Responsible use

Only scrape pages you are allowed to access and automate. Review the website's
terms, robots guidance, rate limits, and applicable law. Avoid personal data,
authenticated pages, and aggressive request rates. This project does not bypass
access controls.

## Notes

- The default selectors are only placeholders.
- Some sites block scraping or rate-limit requests, so use it carefully.
