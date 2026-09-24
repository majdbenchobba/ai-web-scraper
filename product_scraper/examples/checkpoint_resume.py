"""Simulate an interruption, then resume without requesting a completed URL."""

import argparse
from pathlib import Path
from uuid import uuid4

from ..checkpoint import read_checkpoint
from ..core import scrape_urls, write_outputs
from ._fixtures import SELECTORS, FixturePage, fixture_session, product_html


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("example-output/checkpoint-resume"))
    args = parser.parse_args(argv)
    checkpoint = args.output_dir / f"resume-{uuid4().hex[:8]}.sqlite3"
    urls = ["fixture://catalog/cable", "fixture://catalog/knob", "fixture://catalog/workbench"]
    pages = {
        urls[0]: FixturePage(product_html("Fixture cable", "$12.50")),
        urls[1]: [KeyboardInterrupt(), FixturePage(product_html("Fixture knob", "$3.00"))],
        urls[2]: FixturePage(product_html("Fixture workbench", "$60.00")),
    }
    print("Offline example: deliberately interrupting the second fixture URL.")
    with fixture_session(pages) as (session, transport):
        try:
            scrape_urls(urls, session=session, checkpoint_path=checkpoint, **SELECTORS)
        except KeyboardInterrupt:
            saved = read_checkpoint(checkpoint)
            print(f"Interruption recovered: {saved.completed} completed URL saved.")
        frame = scrape_urls(
            urls, session=session, checkpoint_path=checkpoint, resume=True,
            progress_callback=print, **SELECTORS,
        )
        if transport.calls[urls[0]] != 1:
            raise RuntimeError("A completed URL was requested again.")
        print(f"Completed URL requested once: {transport.calls[urls[0]] == 1}.")
    outputs = write_outputs(frame, args.output_dir, skip_charts=True)
    print(f"Resumed to {len(frame)} rows without duplicates.")
    print(f"Checkpoint: {checkpoint}")
    print(f"CSV: {outputs['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
