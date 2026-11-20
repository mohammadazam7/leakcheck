import json
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import pytest

from leakcheck.cli import main

N = 200


def _write(tmp_path: Path, leak: bool, suffix: str = ".csv") -> tuple[Path, Path]:
    columns: dict[str, list[object]] = {
        "visits": [(i * 37) % 211 for i in range(N)],
        "plan": [("free", "pro")[i % 2] for i in range(N)],
        "churned": [int((i * 7) % 5 == 0) for i in range(N)],
    }
    if leak:
        columns["cancel_reason"] = ["price" if c else "none" for c in columns["churned"]]
    table = pa.table(columns)
    train, test = table.slice(0, 150), table.slice(150)
    paths = (tmp_path / f"train{suffix}", tmp_path / f"test{suffix}")
    for t, p in zip((train, test), paths, strict=True):
        if suffix == ".parquet":
            pq.write_table(t, p)
        else:
            pacsv.write_csv(t, p)
    return paths


def test_a_clean_split_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    train, test = _write(tmp_path, leak=False)
    assert main([str(train), str(test), "--target", "churned"]) == 0
    assert "no leakage found" in capsys.readouterr().out


def test_a_leak_exits_one_and_names_the_column(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    train, test = _write(tmp_path, leak=True, suffix=".parquet")
    assert main([str(train), str(test), "--target", "churned"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("leakcheck: 150 train rows, 50 test rows\n")
    assert "[single_feature] cancel_reason alone scores 1.000" in out


def test_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    train, test = _write(tmp_path, leak=True)
    assert main([str(train), str(test), "--target", "churned", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["findings"][0]["check"] == "single_feature"
    assert report["findings"][0]["column"] == "cancel_reason"


def test_ignoring_the_column_clears_the_finding(tmp_path: Path) -> None:
    train, test = _write(tmp_path, leak=True)
    args = [str(train), str(test), "--target", "churned", "--ignore", "cancel_reason"]
    assert main(args) == 0


def test_an_int_column_read_as_float_in_one_file_still_matches(tmp_path: Path) -> None:
    train_path, test_path = _write(tmp_path, leak=False)
    test = pacsv.read_csv(test_path)
    # Half values make the column float in this file only.
    visits = pc.add(test["visits"].cast(pa.float64()), 0.5)
    pacsv.write_csv(test.set_column(0, "visits", visits), test_path)
    assert main([str(train_path), str(test_path), "--target", "churned"]) == 0


def test_unusable_input_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    train, test = _write(tmp_path, leak=False)
    assert main([str(train), str(test), "--target", "nope"]) == 2
    assert "nope" in capsys.readouterr().err
    assert main([str(train), str(tmp_path / "missing.csv"), "--target", "churned"]) == 2
    other = tmp_path / "data.json"
    other.write_text("{}")
    assert main([str(train), str(other), "--target", "churned"]) == 2
