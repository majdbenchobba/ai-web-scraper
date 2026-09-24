"""Parse the bundled fictional HTML catalog with explicit CSS selectors."""

import argparse
from pathlib import Path

import pandas as pd

from ..core import parse_product_html, write_outputs
from ..models import PRODUCT_COLUMNS
from ._fixtures import SELECTORS, catalog_html


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("example-output/selectors"))
    args = parser.parse_args(argv)
    rows = parse_product_html(
        catalog_html(), "fixture://catalog/demo", decimal_separator=".", **SELECTORS,
    )
    frame = pd.DataFrame(rows, columns=PRODUCT_COLUMNS)
    outputs = write_outputs(frame, args.output_dir, skip_charts=True)
    print(f"Parsed {len(frame)} fictional products without network access.")
    print(f"First product: {frame.iloc[0]['Title']} ({frame.iloc[0]['Price']:.2f}).")
    print(f"CSV: {outputs['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
