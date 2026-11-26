"""``leakcheck TRAIN TEST --target COLUMN``: report leakage between two files.

Exit status 0 means no findings, 1 means at least one finding, 2 means the input could
not be checked. That makes it usable as a CI step after a split is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from leakcheck import __version__
from leakcheck.checks import LeakcheckError, Report, align, check


def read_table(path: Path) -> pa.Table:
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pq.read_table(path)
    if suffix in {".csv", ".tsv"}:
        options = pacsv.ParseOptions(delimiter="\t" if suffix == ".tsv" else ",")
        return pacsv.read_csv(path, parse_options=options)
    raise LeakcheckError(f"{path}: expected a .csv, .tsv or .parquet file")


def _text(report: Report) -> str:
    lines = [f"leakcheck: {report.train_rows} train rows, {report.test_rows} test rows"]
    if report.clean:
        lines.append("no leakage found")
    for finding in report.findings:
        lines.append(f"[{finding.check.value}] {finding.detail}")
    return "\n".join(lines)


def _json(report: Report) -> str:
    return json.dumps(
        {
            "train_rows": report.train_rows,
            "test_rows": report.test_rows,
            "findings": [
                {
                    "check": f.check.value,
                    "column": f.column,
                    "value": round(f.value, 6),
                    "detail": f.detail,
                }
                for f in report.findings
            ],
        },
        indent=2,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leakcheck", description="Find data leakage in a train/test split."
    )
    parser.add_argument("train", type=Path, help="training rows (.csv, .tsv or .parquet)")
    parser.add_argument("test", type=Path, help="test rows, same columns")
    parser.add_argument("--target", required=True, help="the column being predicted")
    parser.add_argument(
        "--entity",
        action="append",
        default=[],
        help="a column whose values should not be on both sides (repeatable)",
    )
    parser.add_argument("--time", help="the column the split was made on, for a time split")
    parser.add_argument(
        "--ignore", action="append", default=[], help="a column to leave out (repeatable)"
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--version", action="version", version=f"leakcheck {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        train, test = align(read_table(args.train), read_table(args.test))
        report = check(
            train,
            test,
            target=args.target,
            entities=args.entity,
            time=args.time,
            ignore=args.ignore,
        )
    except (LeakcheckError, OSError, pa.ArrowInvalid) as error:
        print(f"leakcheck: {error}", file=sys.stderr)
        return 2
    print(_json(report) if args.json else _text(report))
    return 0 if report.clean else 1


if __name__ == "__main__":
    sys.exit(main())
