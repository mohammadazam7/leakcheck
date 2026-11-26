"""The whole Python side of the playground: read two CSV files and call leakcheck."""

import io
import json

import pyarrow as pa
import pyarrow.csv as pacsv

import leakcheck
from leakcheck.checks import LeakcheckError, align, check

_tables: dict[str, pa.Table] = {}


def version() -> str:
    return leakcheck.__version__


def _kind(dtype: pa.DataType) -> str:
    if pa.types.is_timestamp(dtype) or pa.types.is_date(dtype):
        return "date"
    if pa.types.is_integer(dtype) or pa.types.is_floating(dtype) or pa.types.is_decimal(dtype):
        return "number"
    if pa.types.is_boolean(dtype):
        return "yes/no"
    return "text"


def load(train_csv: str, test_csv: str) -> str:
    """Parse both files and describe them; the tables stay in memory for ``run``."""
    try:
        train = pacsv.read_csv(io.BytesIO(train_csv.encode("utf-8")))
        test = pacsv.read_csv(io.BytesIO(test_csv.encode("utf-8")))
    except (pa.ArrowInvalid, pa.ArrowKeyError) as error:
        return json.dumps({"ok": False, "message": f"Could not read the files as CSV: {error}"})
    _tables["train"], _tables["test"] = align(train, test)
    preview = _tables["train"].slice(0, 6)
    return json.dumps(
        {
            "ok": True,
            "train_rows": train.num_rows,
            "test_rows": test.num_rows,
            "columns": [{"name": f.name, "kind": _kind(f.type)} for f in _tables["train"].schema],
            "test_columns": test.column_names,
            "preview": [
                ["" if v is None else str(v) for v in row.values()] for row in preview.to_pylist()
            ],
        }
    )


def run(payload: str) -> str:
    request = json.loads(payload)
    try:
        report = check(
            _tables["train"],
            _tables["test"],
            target=request["target"],
            entities=request["entities"],
            time=request["time"] or None,
            ignore=request["ignore"],
        )
    except LeakcheckError as error:
        return json.dumps({"ok": False, "message": str(error)})
    return json.dumps(
        {
            "ok": True,
            "train_rows": report.train_rows,
            "test_rows": report.test_rows,
            "findings": [
                {"check": f.check.value, "column": f.column, "value": f.value, "detail": f.detail}
                for f in report.findings
            ],
        }
    )
