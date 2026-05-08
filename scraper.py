"""Scrape books.toscrape.com for titles, prices, and ratings."""

import csv
import sys
import time
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.exceptions import (
    ChunkedEncodingError,
    ConnectionError as RequestsConnectionError,
    HTTPError,
    RequestException,
    Timeout,
)

BASE_URL = "https://books.toscrape.com/"
MAX_BOOKS = 20
OUTPUT_CSV = "scraped_data.csv"
REQUEST_TIMEOUT = 15  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


def fetch_html(url: str) -> str:
    last_error: RequestException | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; BooksScraper/1.0)"},
            )
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            return resp.text
        except Timeout as exc:
            last_error = exc
            print(f"Timeout fetching {url} (attempt {attempt}/{MAX_RETRIES}).", file=sys.stderr)
        except RequestsConnectionError as exc:
            last_error = exc
            print(
                f"Connection error fetching {url} (attempt {attempt}/{MAX_RETRIES}): {exc}",
                file=sys.stderr,
            )
        except ChunkedEncodingError as exc:
            last_error = exc
            print(
                f"Incomplete transfer for {url} (attempt {attempt}/{MAX_RETRIES}): {exc}",
                file=sys.stderr,
            )
        except HTTPError as exc:
            print(f"HTTP error for {url}: {exc}", file=sys.stderr)
            raise
        except RequestException as exc:
            last_error = exc
            print(
                f"Request failed for {url} (attempt {attempt}/{MAX_RETRIES}): {exc}",
                file=sys.stderr,
            )

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    if last_error is not None:
        raise last_error
    raise RequestException(f"Failed to fetch {url}")


def rating_from_class(classes: Iterable[str]) -> str:
    rating_map = {
        "One": "1",
        "Two": "2",
        "Three": "3",
        "Four": "4",
        "Five": "5",
    }
    for c in classes:
        if c in rating_map:
            return rating_map[c]
    return "unknown"


def next_page_url(soup: BeautifulSoup, current_url: str) -> str | None:
    next_li = soup.select_one("li.next > a")
    if next_li is None or not next_li.get("href"):
        return None
    return urljoin(current_url, next_li["href"])


def collect_books(limit: int) -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    url = BASE_URL

    while url and len(collected) < limit:
        html = fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        for article in soup.select("article.product_pod"):
            if len(collected) >= limit:
                break

            title_el = article.select_one("h3 > a")
            price_el = article.select_one(".price_color")
            rating_el = article.select_one("p.star-rating")

            title = ""
            if title_el is not None:
                title = title_el.get("title") or title_el.get_text(strip=True)

            price = ""
            if price_el is not None:
                price = price_el.get_text(strip=True)

            rating = ""
            if rating_el is not None:
                rating = rating_from_class(rating_el.get("class", []) or [])

            if title:
                collected.append({"title": title, "price": price, "rating": rating})

        url = next_page_url(soup, url)

    return collected[:limit]


def save_csv(rows: list[dict[str, str]], path: str) -> None:
    fieldnames = ("title", "price", "rating")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    try:
        rows = collect_books(MAX_BOOKS)
    except (Timeout, RequestsConnectionError, ChunkedEncodingError, RequestException) as exc:
        print(f"Giving up due to connection/network issues: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Unexpected I/O error: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("No books were scraped.", file=sys.stderr)
        return 1

    if len(rows) < MAX_BOOKS:
        print(
            f"Warning: only {len(rows)} book(s) collected (requested {MAX_BOOKS}).",
            file=sys.stderr,
        )

    try:
        save_csv(rows, OUTPUT_CSV)
    except OSError as exc:
        print(f"Could not write {OUTPUT_CSV}: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(rows)} row(s) to {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
