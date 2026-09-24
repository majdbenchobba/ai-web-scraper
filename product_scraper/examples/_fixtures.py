"""An in-memory Requests transport that has no network-capable adapters."""

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from html import escape
from importlib.resources import files

import requests
from requests.adapters import BaseAdapter


SELECTORS = {
    "container_selector": ".product-item",
    "title_selector": ".product-title",
    "price_selector": ".product-price",
    "rating_selector": ".product-rating",
}


def catalog_html():
    return files("product_scraper").joinpath("data/catalog.html").read_text(encoding="utf-8")


def product_html(title, price):
    return (
        '<article class="product-item">'
        f'<h2 class="product-title">{escape(title)}</h2>'
        f'<span class="product-price">{escape(price)}</span>'
        '<span class="product-rating">4.5</span></article>'
    )


@dataclass(frozen=True)
class FixturePage:
    html: str
    status: int = 200


class FixtureAdapter(BaseAdapter):
    def __init__(self, pages):
        self.pages = {url: list(events) if isinstance(events, list) else [events] for url, events in pages.items()}
        self.calls = Counter()
        self.closed = False

    def send(self, request, **kwargs):
        if self.closed:
            raise RuntimeError("The caller-owned fixture session was closed prematurely.")
        self.calls[request.url] += 1
        events = self.pages.get(request.url, [FixturePage("", 404)])
        event = events.pop(0) if len(events) > 1 else events[0]
        if isinstance(event, BaseException):
            raise event
        response = requests.Response()
        response.status_code = event.status
        response.url = request.url
        response.request = request
        response.reason = "Offline fixture"
        response.encoding = "utf-8"
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response._content = event.html.encode("utf-8")
        response._content_consumed = True
        return response

    def close(self):
        self.closed = True


@contextmanager
def fixture_session(pages):
    with requests.Session() as session:
        session.trust_env = False
        for adapter in session.adapters.values():
            adapter.close()
        session.adapters.clear()
        adapter = FixtureAdapter(pages)
        session.mount("fixture://", adapter)
        yield session, adapter
