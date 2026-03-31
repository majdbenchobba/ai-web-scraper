# Product Web Scraper and Analyzer

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

This is a better fit than pretending the tool can automatically understand arbitrary page structure.

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
