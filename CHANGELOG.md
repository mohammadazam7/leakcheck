# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- A playground that runs the package in the browser on Pyodide: two sample splits, or
  two CSV files of your own that stay on your machine. Every finding is shown with what
  was measured and the matching command line.
- `leakcheck.checks.align`, the type alignment the command line applies to two tables
  read from files.

## [0.1.0] - 2026-11-25

First release.

### Added
- `check(train, test, target=...)`: single-feature, row-overlap, entity-overlap and
  time checks on an existing split, each finding stating what was measured.
- The `leakcheck` command for CSV, TSV and Parquet files, with `--entity`, `--time`,
  `--ignore` and `--json`; exit status 0, 1 or 2 for use in CI.
- `leakcheck.testing.assert_no_leakage` for test suites, taking pandas DataFrames or
  Arrow tables.
- `examples/make_churn_split.py`, a made-up data set split the careless way.
- Project foundation: package layout, CI, contribution and security guides.

[Unreleased]: https://github.com/mohammadazam7/leakcheck/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mohammadazam7/leakcheck/releases/tag/v0.1.0
