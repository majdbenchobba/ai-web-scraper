"""Bounded retries for idempotent page requests."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time

import requests


DEFAULT_RETRIES = 2
MAX_RETRIES = 5
MAX_RETRY_DELAY = 30
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def validate_retries(max_retries: int) -> None:
    if (
        isinstance(max_retries, bool)
        or not isinstance(max_retries, int)
        or not 0 <= max_retries <= MAX_RETRIES
    ):
        raise ValueError(f"Retries must be an integer from 0 to {MAX_RETRIES}.")


def retry_delay(response: requests.Response | None, attempt: int) -> float | None:
    """Return a bounded delay, or None when the server requests a longer wait."""
    backoff = min(0.5 * 2**attempt, MAX_RETRY_DELAY)
    header = response.headers.get("Retry-After") if response is not None else None
    if not isinstance(header, str) or not header.strip():
        return backoff
    header = header.strip()
    if header.isascii() and header.isdigit():
        # Compare before conversion so an arbitrarily large header stays bounded.
        digits = header.lstrip("0") or "0"
        if len(digits) > len(str(MAX_RETRY_DELAY)):
            return None
        delay = float(digits)
    else:
        try:
            deadline = parsedate_to_datetime(header)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            delay = max(0.0, (deadline - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return backoff
    return None if delay > MAX_RETRY_DELAY else max(backoff, delay)


def fetch_html(
    session: requests.Session,
    url: str,
    headers: dict[str, str],
    max_retries: int = DEFAULT_RETRIES,
    progress_callback=None,
) -> str:
    validate_retries(max_retries)
    for attempt in range(max_retries + 1):
        response = None
        try:
            response = session.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            transient = (
                isinstance(exc, (requests.ConnectionError, requests.Timeout))
                and not isinstance(exc, requests.exceptions.SSLError)
            ) or (
                isinstance(exc, requests.HTTPError)
                and response is not None
                and response.status_code in RETRYABLE_STATUS_CODES
            )
            if not transient or attempt == max_retries:
                raise
            delay = retry_delay(response, attempt)
            if delay is None:
                if progress_callback:
                    progress_callback(
                        f"  Server requested a wait over {MAX_RETRY_DELAY}s; leaving this URL for a later run."
                    )
                raise
            if progress_callback:
                progress_callback(f"  Retrying in {delay:g}s ({attempt + 1}/{max_retries})...")
        finally:
            if response is not None:
                response.close()
        time.sleep(delay)

    raise RuntimeError("Request retry loop ended unexpectedly.")
