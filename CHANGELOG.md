# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- `check(train, test, target=...)`: single-feature, row-overlap, entity-overlap and
  time checks on an existing split, each finding stating what was measured.
- The `leakcheck` command for CSV, TSV and Parquet files, with `--entity`, `--time`,
  `--ignore` and `--json`; exit status 0, 1 or 2 for use in CI.
- `leakcheck.testing.assert_no_leakage` for test suites, taking pandas DataFrames or
  Arrow tables.
- `examples/make_churn_split.py`, a made-up data set split the careless way.
- Project foundation: package layout, CI, contribution and security guides.
