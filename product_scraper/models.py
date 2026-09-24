from dataclasses import dataclass


PRODUCT_COLUMNS = ("SourceURL", "Title", "Price", "Rating")


@dataclass(frozen=True)
class ScrapeFailure:
    url: str
    error: str
