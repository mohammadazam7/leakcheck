import datetime as dt

import numpy as np
import pyarrow as pa
import pytest

from leakcheck.checks import Check, LeakcheckError, check

N = 400


def _split(columns: dict[str, list[object]], test_every: int = 5) -> tuple[pa.Table, pa.Table]:
    table = pa.table(columns)
    test_rows = [i for i in range(table.num_rows) if i % test_every == 0]
    train_rows = [i for i in range(table.num_rows) if i % test_every != 0]
    return table.take(train_rows), table.take(test_rows)


def _clean() -> dict[str, list[object]]:
    rng = np.random.default_rng(0)
    amount = rng.normal(size=N)
    return {
        "amount": amount.round(6).tolist(),
        "plan": [("free", "pro", "team")[i % 3] for i in range(N)],
        # Related to the target but far from perfect.
        "churned": [int(a + rng.normal() > 0.5) for a in amount],
    }


def test_a_clean_split_has_no_findings() -> None:
    train, test = _split(_clean())
    report = check(train, test, target="churned")
    assert report.clean, report.findings
    assert (report.train_rows, report.test_rows) == (320, 80)


def test_a_number_that_encodes_the_target_is_found() -> None:
    columns = _clean()
    columns["days_to_refund"] = [
        float(i % 7 + 1) if y else 0.0 for i, y in enumerate(columns["churned"])
    ]
    train, test = _split(columns)
    [finding] = check(train, test, target="churned").findings
    assert finding.check is Check.SINGLE_FEATURE
    assert finding.column == "days_to_refund"
    assert finding.value == 1.0
    assert "threshold" in finding.detail


def test_a_category_that_encodes_the_target_is_found() -> None:
    columns = _clean()
    columns["status"] = ["closed" if y else "active" for y in columns["churned"]]
    train, test = _split(columns)
    [finding] = check(train, test, target="churned").by_check(Check.SINGLE_FEATURE)
    assert finding.column == "status"


def test_a_number_that_tracks_a_numeric_target_is_found() -> None:
    rng = np.random.default_rng(1)
    spend = rng.normal(100, 20, size=N)
    columns: dict[str, list[object]] = {
        "visits": rng.integers(0, 50, size=N).tolist(),
        "spend_with_tax": (spend * 1.13).round(2).tolist(),
        "spend": spend.round(2).tolist(),
    }
    train, test = _split(columns)
    [finding] = check(train, test, target="spend").findings
    assert finding.column == "spend_with_tax"
    assert finding.value > 0.999


def test_copied_rows_are_counted() -> None:
    train, test = _split(_clean())
    test = pa.concat_tables([test.slice(0, 70), train.slice(0, 10)])
    [finding] = check(train, test, target="churned").findings
    assert finding.check is Check.ROW_OVERLAP
    assert finding.value == pytest.approx(10 / 80)
    assert "10 test rows (12.5%) also appear in training, identical" in finding.detail


def test_shared_entities_are_reported_only_for_entity_columns() -> None:
    columns = _clean()
    columns["customer_id"] = [f"c{i // 4}" for i in range(N)]
    train, test = _split(columns)
    assert check(train, test, target="churned").clean
    [finding] = check(train, test, target="churned", entities=["customer_id"]).findings
    assert finding.check is Check.ENTITY_OVERLAP
    # Customers own four consecutive rows and every fifth row is a test row, so each
    # customer with a test row also has training rows.
    assert finding.value == 1.0
    in_test = set(test["customer_id"].to_pylist())
    assert f"{len(in_test)} values of customer_id" in finding.detail


def test_training_rows_after_the_test_period_are_found() -> None:
    columns = _clean()
    start = dt.datetime(2026, 1, 1)
    columns["seen_at"] = [start + dt.timedelta(days=i) for i in range(N)]
    table = pa.table(columns)
    train, test = table.slice(0, 300), table.slice(300)
    assert check(train, test, target="churned", time="seen_at").clean
    # A random split on dated rows: most training rows are after the first test row.
    train, test = _split(columns)
    [finding] = check(train, test, target="churned", time="seen_at").findings
    assert finding.check is Check.TIME
    assert finding.column == "seen_at"
    assert finding.value > 0.9


def test_another_date_from_after_the_cutoff_is_found() -> None:
    columns = _clean()
    start = dt.datetime(2026, 1, 1)
    columns["seen_at"] = [start + dt.timedelta(days=i) for i in range(N)]
    # Filled in once the outcome was known, months later.
    columns["closed_on"] = [
        (start + dt.timedelta(days=i + 200)).date() if y else None
        for i, y in enumerate(columns["churned"])
    ]
    table = pa.table(columns)
    train, test = table.slice(0, 300), table.slice(300)
    [finding] = check(train, test, target="churned", time="seen_at").findings
    assert finding.column == "closed_on"
    assert "later than the cutoff" in finding.detail


def test_identifiers_and_ignored_columns_are_not_features() -> None:
    columns = _clean()
    columns["row_id"] = [f"r{i}" for i in range(N)]
    columns["label_copy"] = list(columns["churned"])
    train, test = _split(columns)
    assert check(train, test, target="churned", ignore=["label_copy"]).clean


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"target": "nope"}, "not in the train table"),
        ({"target": "churned", "entities": ["nope"]}, "nope"),
        ({"target": "churned", "time": "nope"}, "nope"),
    ],
)
def test_unknown_columns_are_refused(kwargs: dict[str, object], message: str) -> None:
    train, test = _split(_clean())
    with pytest.raises(LeakcheckError, match=message):
        check(train, test, **kwargs)  # type: ignore[arg-type]


def test_tables_with_different_columns_are_refused() -> None:
    train, test = _split(_clean())
    with pytest.raises(LeakcheckError, match="different columns"):
        check(train, test.drop_columns(["plan"]), target="churned")


def test_empty_tables_are_refused() -> None:
    train, test = _split(_clean())
    with pytest.raises(LeakcheckError, match="at least one row"):
        check(train, test.slice(0, 0), target="churned")


def test_a_field_filled_only_after_the_outcome_is_found_from_its_gaps() -> None:
    columns = _clean()
    columns["cancel_reason"] = [
        ("price", "moved")[i % 2] if y else None for i, y in enumerate(columns["churned"])
    ]
    columns["refund_amount"] = [
        float(i % 9 + 1) if y else None for i, y in enumerate(columns["churned"])
    ]
    train, test = _split(columns)
    findings = check(train, test, target="churned").by_check(Check.SINGLE_FEATURE)
    assert sorted(f.column for f in findings) == ["cancel_reason", "refund_amount"]
