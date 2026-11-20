# leakcheck

Find data leakage in a train/test split before you trust the score.

```bash
leakcheck train.csv test.csv --target churned --entity customer_id --time month
```

```text
leakcheck: 1600 train rows, 400 test rows
[single_feature] cancel_reason alone scores 1.000 (test balanced accuracy of mapping each value to its usual target); check whether it is known before the prediction is made
[entity_overlap] 282 values of customer_id (93.7% of those in test) have rows on both sides; the model is tested partly on entities it has seen
[time] 1600 training rows (100.0%) are dated at or after the first test row (2026-01-01 00:00:00); the split does not keep the future out of training
```

That is the output on a made-up churn data set split the careless way
(`python examples/make_churn_split.py out/` writes it). Any model trained on that split
would score well and then disappoint: it can read the answer from a field filled in
after the customer left, it has already seen most test customers, and it learned from
months that come after the test period.

> **Status:** early. The checks come from
> [ml-research-agent](https://github.com/mohammadazam7/ml-research-agent), where they run
> before any model is trained; this package makes them usable on any split. The first
> release is planned for the end of November.

## Install

```bash
pip install git+https://github.com/mohammadazam7/leakcheck
```

Python 3.11 or later. The only dependency is pyarrow.

## What it looks for

| Check | What it means |
|---|---|
| `single_feature` | One column on its own predicts the target almost perfectly on the test rows (0.98 balanced accuracy or more, using a rule learned on the training rows only). Usually the target recorded another way. A column that is empty exactly when the target is 0 counts too. |
| `row_overlap` | Test rows that also appear in training, identical in every column: the same record copied to both sides. |
| `entity_overlap` | Values of an `--entity` column, such as a customer or patient ID, with rows on both sides. |
| `time` | With `--time`, training rows dated at or after the first test row, and other date columns holding values later than that in training rows. |

Every finding says what was measured, so you can decide whether it is a real leak or a
feature that is legitimately that strong. Exit status is 0 with no findings, 1 with
findings and 2 when the files could not be checked, so it can run as a CI step after a
split is written. `--json` prints the report for other tools, and `--ignore COLUMN`
leaves a column out once you have decided it is fine.

## In a test suite

```python
from leakcheck.testing import assert_no_leakage

def test_the_training_split_does_not_leak():
    train, test = make_split()
    assert_no_leakage(train, test, target="churned", entities=["customer_id"])
```

`train` and `test` can be pandas DataFrames or Arrow tables. A leaky split fails the
test with every finding in the message. For the report itself, call
`leakcheck.checks.check` with Arrow tables.

## Limits

- It finds leaks that show up in the data. A feature that is computed from the future
  but is not strongly predictive on its own will not be flagged.
- The single-feature check looks at one column at a time; a leak spread across two
  columns that only reveal the target together is missed.
- Columns are classified from their types: strings that are almost all distinct are
  treated as identifiers and skipped.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
make install
make check
```

## License

MIT
