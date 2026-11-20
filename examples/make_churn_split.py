"""Write a small synthetic churn data set, split the careless way, to try leakcheck on.

Usage: python examples/make_churn_split.py OUT_DIR

The data is made up. It has three planted problems: a cancellation reason that is only
filled in after a customer leaves, customers with rows on both sides of the split, and a
random split of rows that are dated, so training rows come from after the test period.
"""

from __future__ import annotations

import datetime as dt
import random
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    start = dt.datetime(2026, 1, 1)
    rows = []
    for _ in range(2000):
        visits = rng.randint(0, 40)
        churned = int(rng.random() < 0.6 - visits / 80)
        rows.append(
            {
                "customer_id": f"c{rng.randint(1, 600):04d}",
                "month": start + dt.timedelta(days=rng.randint(0, 364)),
                "visits": visits,
                "plan": rng.choice(["free", "pro", "team"]),
                "cancel_reason": rng.choice(["price", "moved", "other"]) if churned else None,
                "churned": churned,
            }
        )
    rng.shuffle(rows)
    cut = int(len(rows) * 0.8)
    for name, part in (("train", rows[:cut]), ("test", rows[cut:])):
        pacsv.write_csv(pa.Table.from_pylist(part), out / f"{name}.csv")


if __name__ == "__main__":
    main()
