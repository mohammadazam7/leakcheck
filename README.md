# leakcheck

Find data leakage in a train/test split before you trust the score.

> **Status:** just started. The checks below come from
> [ml-research-agent](https://github.com/mohammadazam7/ml-research-agent), where they
> run before any model is trained; this package makes them usable on their own. The
> first release is planned for the end of November.

```bash
leakcheck train.parquet test.parquet --target churned --entity customer_id
```

## What it looks for

| Check | What it means |
|---|---|
| Single feature | One column on its own predicts the target almost perfectly on the test rows. Usually the target recorded another way, such as a refund date when predicting refunds. |
| Row overlap | The same features and target appear in both train and test, so the test set partly measures memorisation. |
| Entity overlap | The same customer or patient has rows on both sides of a split that was meant to keep them apart. |
| Time | Training rows dated after the first test row, or other date columns holding values from after the cutoff. |

Every finding says what was measured, so you can decide whether it is a real leak or a
feature that is legitimately that strong.

## Planned

- `leakcheck` command for CSV and Parquet files, exiting non-zero when it finds a leak,
  so it can sit in CI.
- `assert_no_leakage(train, test, target=...)` for pytest, taking pandas or Arrow tables.
- JSON output for other tools.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
make install
make check
```

## License

MIT
