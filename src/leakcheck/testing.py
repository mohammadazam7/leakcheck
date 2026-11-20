"""``assert_no_leakage`` for test suites: fail a test when a split leaks.

    from leakcheck.testing import assert_no_leakage

    def test_the_training_split_does_not_leak():
        train, test = make_split()
        assert_no_leakage(train, test, target="churned", entities=["customer_id"])

Tables can be Arrow tables or pandas DataFrames; pandas is converted with
``pyarrow.Table.from_pandas`` and is not a dependency of leakcheck.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pyarrow as pa

from leakcheck.checks import Report, check


def _as_arrow(table: Any, name: str) -> pa.Table:
    if isinstance(table, pa.Table):
        return table
    if type(table).__module__.startswith("pandas"):
        return pa.Table.from_pandas(table, preserve_index=False)
    raise TypeError(f"{name} must be a pyarrow.Table or a pandas.DataFrame")


def assert_no_leakage(
    train: Any,
    test: Any,
    *,
    target: str,
    entities: Sequence[str] = (),
    time: str | None = None,
    ignore: Sequence[str] = (),
) -> Report:
    """Run every check and raise ``AssertionError`` listing the findings, if any."""
    report = check(
        _as_arrow(train, "train"),
        _as_arrow(test, "test"),
        target=target,
        entities=entities,
        time=time,
        ignore=ignore,
    )
    if not report.clean:
        lines = [f"leakcheck found {len(report.findings)} problem(s) in the split:"]
        lines += [f"  [{f.check.value}] {f.detail}" for f in report.findings]
        raise AssertionError("\n".join(lines))
    return report
