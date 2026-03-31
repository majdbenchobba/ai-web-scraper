# Product Web Scraper and Analyzer

Simple Python scraper for product-listing pages.

It reads URLs from a text file, scrapes repeated product cards, saves a CSV, and can generate price/rating charts.

This only works well when the target site has a clear repeating product structure and you know the CSS selectors you want to use.

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

## Output

The script writes:

- `scraped_data.csv`
- `price_chart.png`
- `rating_chart.png`
- `summary_report.txt`

into the output folder.

## Notes

- The default selectors are only placeholders.
- Some sites block scraping or rate-limit requests, so use it carefully.
