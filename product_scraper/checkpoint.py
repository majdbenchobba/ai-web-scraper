"""Durable, per-page checkpoints with exclusive writer ownership."""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import sqlite3

from .models import PRODUCT_COLUMNS, ScrapeFailure


SCHEMA_VERSION = 1
SETTINGS = {
    "container_selector", "title_selector", "price_selector",
    "rating_selector", "decimal_separator",
}


class CheckpointError(ValueError):
    pass


@dataclass
class CheckpointSnapshot:
    urls: list[str]
    settings: dict[str, str]
    pages: dict[int, dict]

    @property
    def completed(self) -> int:
        return sum(page["status"] == "success" for page in self.pages.values())

    @property
    def rows(self) -> list[dict]:
        return [
            row for _, page in sorted(self.pages.items())
            if page["status"] == "success" for row in page["rows"]
        ]

    @property
    def failures(self) -> list[ScrapeFailure]:
        return [
            ScrapeFailure(self.urls[index], page["error"])
            for index, page in sorted(self.pages.items())
            if page["status"] == "failed"
        ]


def _validate_config(config):
    if (
        not isinstance(config, dict)
        or type(config.get("schema_version")) is not int
        or config["schema_version"] != SCHEMA_VERSION
        or not isinstance(config.get("urls"), list)
        or not all(isinstance(url, str) for url in config["urls"])
        or not isinstance(config.get("settings"), dict)
        or set(config["settings"]) != SETTINGS
        or not all(isinstance(value, str) for value in config["settings"].values())
        or config["settings"]["decimal_separator"] not in (".", ",")
    ):
        raise CheckpointError("Unsupported or invalid checkpoint configuration.")
    return config


def _validate_rows(rows, url):
    if not isinstance(rows, list):
        raise CheckpointError("Invalid product rows in checkpoint.")
    for row in rows:
        if (
            not isinstance(row, dict) or set(row) != set(PRODUCT_COLUMNS)
            or row["SourceURL"] != url or not isinstance(row["Title"], str)
        ):
            raise CheckpointError("Invalid product row or source URL in checkpoint.")
        for field in ("Price", "Rating"):
            value = row[field]
            if value is not None and (
                type(value) not in (int, float) or not math.isfinite(value)
            ):
                raise CheckpointError("Checkpoint contains an invalid numeric value.")


def _snapshot(connection):
    try:
        record = connection.execute("SELECT config FROM checkpoint_meta WHERE id=1").fetchone()
        if record is None:
            raise CheckpointError("Checkpoint configuration is missing.")
        config = _validate_config(json.loads(record[0]))
        pages = {}
        for index, status, encoded, error in connection.execute(
            "SELECT page_index, status, rows_json, error FROM checkpoint_pages ORDER BY page_index"
        ):
            if type(index) is not int or not 0 <= index < len(config["urls"]):
                raise CheckpointError("Checkpoint contains an invalid page index.")
            rows = json.loads(encoded)
            _validate_rows(rows, config["urls"][index])
            if status == "success" and error is None:
                pass
            elif status == "failed" and isinstance(error, str) and not rows:
                pass
            else:
                raise CheckpointError("Checkpoint contains an invalid page outcome.")
            pages[index] = {"status": status, "rows": rows, "error": error}
        return CheckpointSnapshot(config["urls"], config["settings"], pages)
    except (sqlite3.Error, ValueError, TypeError, OverflowError) as exc:
        raise CheckpointError(f"Cannot read checkpoint: {exc}") from exc


def read_checkpoint(path: Path) -> CheckpointSnapshot:
    """Read committed results without creating or modifying a checkpoint."""
    connection = None
    try:
        connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        return _snapshot(connection)
    except sqlite3.Error as exc:
        raise CheckpointError(f"Cannot open checkpoint {path}: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def recover_checkpoint(path: Path) -> CheckpointSnapshot:
    """Recover an interrupted SQLite write under the writer lock, then inspect it."""
    path = Path(path)
    if not path.is_file():
        raise CheckpointError(f"Checkpoint not found: {path}")
    with Checkpoint(path, None, None, resume=True) as checkpoint:
        return checkpoint.snapshot


class Checkpoint:
    def __init__(self, path: Path, urls: list[str] | None, settings: dict[str, str] | None, resume=False):
        self.path = Path(path).resolve()
        if urls is None or settings is None:
            if not (resume and urls is None and settings is None):
                raise CheckpointError("Both URLs and extraction settings are required for a new checkpoint.")
            self.config = None
        else:
            self.config = _validate_config({
                "schema_version": SCHEMA_VERSION, "urls": list(urls), "settings": dict(settings),
            })
        self.resume = resume
        self.connection = None
        self.lock_file = None
        self.locked = False
        self.snapshot = None

    def _lock(self):
        if not self.resume:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = Path(str(self.path) + ".lock").open("a+b")
        self.lock_file.seek(0, os.SEEK_END)
        if self.lock_file.tell() == 0:
            self.lock_file.write(b"\0")
            self.lock_file.flush()
        self.lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise CheckpointError(f"Checkpoint is in use or cannot be locked: {self.path}") from exc
        self.locked = True

    def __enter__(self):
        try:
            self._lock()
            if not self.resume:
                try:
                    descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                    os.close(descriptor)
                except FileExistsError as exc:
                    raise CheckpointError(
                        f"Checkpoint already exists: {self.path}. Resume it or choose a new checkpoint path."
                    ) from exc
            self.connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=0.5)
            self.connection.execute("PRAGMA synchronous=FULL")
            if not self.resume:
                with self.connection:
                    self.connection.execute("BEGIN IMMEDIATE")
                    self.connection.execute(
                        "CREATE TABLE checkpoint_meta (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL)"
                    )
                    self.connection.execute(
                        "CREATE TABLE checkpoint_pages ("
                        "page_index INTEGER PRIMARY KEY, status TEXT NOT NULL, "
                        "rows_json TEXT NOT NULL, error TEXT)"
                    )
                    self.connection.execute(
                        "INSERT INTO checkpoint_meta VALUES (1, ?)",
                        (json.dumps(self.config, ensure_ascii=False, allow_nan=False),),
                    )
            self.snapshot = _snapshot(self.connection)
            if self.config is None:
                self.config = {
                    "schema_version": SCHEMA_VERSION,
                    "urls": self.snapshot.urls, "settings": self.snapshot.settings,
                }
            elif self.snapshot.urls != self.config["urls"] or self.snapshot.settings != self.config["settings"]:
                raise CheckpointError(
                    "Checkpoint URLs, their order, or extraction settings differ from this run."
                )
            return self
        except BaseException as exc:
            self.close()
            if isinstance(exc, sqlite3.Error):
                raise CheckpointError(f"Cannot open checkpoint {self.path}: {exc}") from exc
            raise

    def save(self, index: int, rows: list[dict], error: str | None = None):
        if type(index) is not int or not 0 <= index < len(self.config["urls"]):
            raise CheckpointError("Invalid checkpoint page index.")
        _validate_rows(rows, self.config["urls"][index])
        if error is not None and (not isinstance(error, str) or rows):
            raise CheckpointError("A failed page must have an error and no product rows.")
        try:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO checkpoint_pages VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(page_index) DO UPDATE SET "
                    "status=excluded.status, rows_json=excluded.rows_json, error=excluded.error",
                    (index, "failed" if error is not None else "success",
                     json.dumps(rows, ensure_ascii=False, allow_nan=False), error),
                )
        except sqlite3.Error as exc:
            raise CheckpointError(f"Cannot save checkpoint {self.path}: {exc}") from exc

    def close(self):
        try:
            if self.connection is not None:
                self.connection.close()
                self.connection = None
        finally:
            if self.lock_file is not None:
                try:
                    if self.locked:
                        self.lock_file.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                finally:
                    self.lock_file.close()
                    self.lock_file = None
                    self.locked = False

    def __exit__(self, exc_type, exc, traceback):
        self.close()
