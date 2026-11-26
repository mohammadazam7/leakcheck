"""Write the two sample splits the playground offers, from one made-up churn data set.

``careless``: the split examples/make_churn_split.py writes, with its three planted
problems (a column filled in after the outcome, customers on both sides, a random split
of dated rows).

``careful``: the same rows split by customer, so nobody is on both sides, without the
column that is only known after a customer leaves. It is not a split in time, so the
page does not ask for the time check on it.

Usage: python make_samples.py OUT_DIR
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv

REPO = Path(__file__).resolve().parents[2]


def main() -> None:
    out = Path(sys.argv[1])
    careless = out / "careless"
    careful = out / "careful"
    careful.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(REPO / "examples" / "make_churn_split.py"), str(careless)], check=True
    )

    rows = pa.concat_tables(
        [pacsv.read_csv(careless / "train.csv"), pacsv.read_csv(careless / "test.csv")]
    ).drop_columns(["cancel_reason"])
    in_test = [
        hashlib.sha256(str(c).encode()).digest()[0] < 51  # about 20% of customers
        for c in rows["customer_id"].to_pylist()
    ]
    pacsv.write_csv(rows.filter(pa.array([not t for t in in_test])), careful / "train.csv")
    pacsv.write_csv(rows.filter(pa.array(in_test)), careful / "test.csv")


if __name__ == "__main__":
    main()
