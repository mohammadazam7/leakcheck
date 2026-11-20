import pyarrow as pa
import pytest

from leakcheck.testing import assert_no_leakage

N = 200


def _tables(leak: bool) -> tuple[pa.Table, pa.Table]:
    columns: dict[str, list[object]] = {
        "visits": [(i * 37) % 211 for i in range(N)],
        "churned": [int(i % 5 == 0) for i in range(N)],
    }
    if leak:
        columns["closed"] = [bool(c) for c in columns["churned"]]
    table = pa.table(columns)
    return table.slice(0, 150), table.slice(150)


def test_a_clean_split_passes_and_returns_the_report() -> None:
    report = assert_no_leakage(*_tables(leak=False), target="churned")
    assert report.clean


def test_a_leaky_split_fails_with_every_finding_listed() -> None:
    with pytest.raises(AssertionError) as raised:
        assert_no_leakage(*_tables(leak=True), target="churned")
    message = str(raised.value)
    assert message.startswith("leakcheck found 1 problem(s) in the split:")
    assert "[single_feature] closed alone scores 1.000" in message


def test_pandas_frames_are_accepted() -> None:
    pd = pytest.importorskip("pandas")
    train, test = _tables(leak=False)
    assert assert_no_leakage(train.to_pandas(), pd.DataFrame(test.to_pydict()), target="churned")


def test_other_inputs_are_refused() -> None:
    train, _ = _tables(leak=False)
    with pytest.raises(TypeError, match="test must be"):
        assert_no_leakage(train, [{"visits": 1}], target="churned")
