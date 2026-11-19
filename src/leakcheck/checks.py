"""The leakage checks, on two Arrow tables that are already split.

Each check returns findings that say what was measured, never just "leak". A finding is a
reason to look, not a verdict: a feature can be legitimately that strong, and an entity
can be meant to recur.

``single_feature``
    One column on its own predicts the target almost perfectly on the test rows, using a
    rule learned only on the training rows (a threshold for numbers, the usual target
    per value for categories). For a numeric target, the absolute correlation on the
    training rows.
``row_overlap``
    Test rows that also appear in training with every column equal: the same record
    copied to both sides. Rows that only share their feature values are not counted,
    since coarse features repeat in any data set.
``entity_overlap``
    Values of an entity column (customer, patient) present on both sides.
``time``
    Training rows dated at or after the first test row of the time column, and other
    date columns holding values later than that cutoff in training rows.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

import pyarrow as pa
import pyarrow.compute as pc

# A single feature at or above this held-out score is reported.
SUSPICIOUS_SCORE = 0.98
# A string column whose values are this unique is an identifier, not a feature.
IDENTIFIER_SHARE = 0.9
# An integer column with more distinct values than this is treated as a number.
MAX_INTEGER_CATEGORIES = 20


_MISSING = "(missing)"


class LeakcheckError(ValueError):
    pass


class Check(Enum):
    SINGLE_FEATURE = "single_feature"
    ROW_OVERLAP = "row_overlap"
    ENTITY_OVERLAP = "entity_overlap"
    TIME = "time"


@dataclass(frozen=True)
class Finding:
    check: Check
    column: str | None
    value: float
    detail: str


@dataclass(frozen=True)
class Report:
    train_rows: int
    test_rows: int
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        return not self.findings

    def by_check(self, check: Check) -> list[Finding]:
        return [f for f in self.findings if f.check is check]


class _Kind(Enum):
    NUMBER = "number"
    CATEGORY = "category"
    DATE = "date"
    SKIP = "skip"


def _kind(values: pa.ChunkedArray) -> _Kind:
    dtype = values.type
    present = len(values) - values.null_count
    if present == 0:
        return _Kind.SKIP
    if pa.types.is_timestamp(dtype) or pa.types.is_date(dtype):
        return _Kind.DATE
    distinct = int(pc.count_distinct(values).as_py())
    if distinct < 2:
        return _Kind.SKIP
    if pa.types.is_floating(dtype) or pa.types.is_decimal(dtype):
        return _Kind.NUMBER
    if pa.types.is_integer(dtype):
        return _Kind.NUMBER if distinct > MAX_INTEGER_CATEGORIES else _Kind.CATEGORY
    if pa.types.is_boolean(dtype) or pa.types.is_dictionary(dtype):
        return _Kind.CATEGORY
    if pa.types.is_string(dtype) or pa.types.is_large_string(dtype):
        return _Kind.SKIP if distinct >= IDENTIFIER_SHARE * present else _Kind.CATEGORY
    return _Kind.SKIP


def _balanced_accuracy(truth: Sequence[object], predicted: Sequence[object]) -> float:
    """Mean recall over the classes present: 1 / k for a constant guess, 1 for perfect."""
    totals: Counter[object] = Counter(truth)
    hits: Counter[object] = Counter(t for t, p in zip(truth, predicted, strict=True) if t == p)
    return sum(hits[c] / n for c, n in totals.items()) / len(totals)


def _usual(counter: Counter[object]) -> object:
    return max(counter.items(), key=lambda kv: (kv[1], str(kv[0])))[0]


def _stump(xs: Sequence[float], ys: Sequence[object]) -> tuple[float, object, object]:
    """The single threshold, learned on training rows, that best splits two sides."""
    pairs = sorted(zip(xs, ys, strict=True), key=lambda p: p[0])
    total: Counter[object] = Counter(y for _, y in pairs)
    left: Counter[object] = Counter()
    truth = [y for _, y in pairs]
    best = (-1.0, pairs[0][0], pairs[0][1], pairs[0][1])
    for i in range(len(pairs) - 1):
        left[pairs[i][1]] += 1
        if pairs[i][0] == pairs[i + 1][0]:
            continue
        low, high = _usual(left), _usual(total - left)
        score = _balanced_accuracy(truth, [low] * (i + 1) + [high] * (len(pairs) - i - 1))
        if score > best[0]:
            best = (score, (pairs[i][0] + pairs[i + 1][0]) / 2, low, high)
    return best[1], best[2], best[3]


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return 0.0 if sxx == 0 or syy == 0 else sxy / math.sqrt(sxx * syy)


def _pairs(
    table: pa.Table, column: str, target: str, missing: object = None
) -> tuple[list[object], list[object]]:
    """Feature and target values for rows with a target. A missing feature value becomes
    ``missing``, or the row is dropped when ``missing`` is None: whether a value is
    missing can itself give the target away (a field filled in only after the outcome)."""
    kept = []
    for x, y in zip(table[column].to_pylist(), table[target].to_pylist(), strict=True):
        if y is None:
            continue
        if x is None:
            if missing is None:
                continue
            x = missing
        kept.append((x, y))
    return [x for x, _ in kept], [y for _, y in kept]


def _single_feature(
    train: pa.Table, test: pa.Table, target: str, features: dict[str, _Kind], numeric_target: bool
) -> list[Finding]:
    findings = []
    for name, kind in features.items():
        if kind is _Kind.DATE:
            continue
        # Missing numbers sort below every value, so one threshold can separate them;
        # a missing category is a category of its own.
        missing: object = None
        if not numeric_target:
            missing = -math.inf if kind is _Kind.NUMBER else _MISSING
        train_x, train_y = _pairs(train, name, target, missing)
        test_x, test_y = _pairs(test, name, target, missing)
        if len(set(train_y)) < 2 or len(set(test_y)) < 2 or not test_x:
            continue
        if numeric_target:
            if kind is not _Kind.NUMBER:
                continue
            xs = [float(x) for x in train_x]  # type: ignore[arg-type]
            score = abs(_pearson(xs, [float(y) for y in train_y]))  # type: ignore[arg-type]
            measure = "absolute correlation with the target on training rows"
        elif kind is _Kind.NUMBER:
            cut, low, high = _stump([float(x) for x in train_x], train_y)  # type: ignore[arg-type]
            predicted = [low if float(x) <= cut else high for x in test_x]  # type: ignore[arg-type]
            score = _balanced_accuracy(test_y, predicted)
            measure = f"test balanced accuracy of one threshold at {cut:g}"
        else:
            seen: dict[object, Counter[object]] = {}
            for x, y in zip(train_x, train_y, strict=True):
                seen.setdefault(x, Counter())[y] += 1
            rule = {x: _usual(c) for x, c in seen.items()}
            fallback = _usual(Counter(train_y))
            score = _balanced_accuracy(test_y, [rule.get(x, fallback) for x in test_x])
            measure = "test balanced accuracy of mapping each value to its usual target"
        if score >= SUSPICIOUS_SCORE:
            findings.append(
                Finding(
                    Check.SINGLE_FEATURE,
                    name,
                    score,
                    f"{name} alone scores {score:.3f} ({measure}); check whether it is known "
                    "before the prediction is made",
                )
            )
    return findings


def _row_overlap(train: pa.Table, test: pa.Table, columns: Sequence[str]) -> list[Finding]:
    train_rows = set(zip(*(train[n].to_pylist() for n in columns), strict=True))
    test_rows = list(zip(*(test[n].to_pylist() for n in columns), strict=True))
    shared = sum(1 for row in test_rows if row in train_rows)
    if not shared:
        return []
    share = shared / len(test_rows)
    return [
        Finding(
            Check.ROW_OVERLAP,
            None,
            share,
            f"{shared} test rows ({share:.1%}) also appear in training, identical in every column",
        )
    ]


def _entity_overlap(train: pa.Table, test: pa.Table, entities: Sequence[str]) -> list[Finding]:
    findings = []
    for name in entities:
        seen = set(train[name].drop_null().to_pylist())
        in_test = set(test[name].drop_null().to_pylist())
        both = seen & in_test
        if both:
            share = len(both) / len(in_test)
            findings.append(
                Finding(
                    Check.ENTITY_OVERLAP,
                    name,
                    share,
                    f"{len(both)} values of {name} ({share:.1%} of those in test) have rows "
                    "on both sides; the model is tested partly on entities it has seen",
                )
            )
    return findings


def _time(train: pa.Table, test: pa.Table, time: str, features: dict[str, _Kind]) -> list[Finding]:
    cutoff = pc.min(test[time]).as_py()
    if cutoff is None:
        raise LeakcheckError(f"{time} has no values in the test rows")
    findings = []
    late = [v for v in train[time].to_pylist() if v is not None and v >= cutoff]
    if late:
        share = len(late) / train.num_rows
        findings.append(
            Finding(
                Check.TIME,
                time,
                share,
                f"{len(late)} training rows ({share:.1%}) are dated at or after the first test "
                f"row ({cutoff}); the split does not keep the future out of training",
            )
        )
    for name, kind in features.items():
        if kind is not _Kind.DATE:
            continue
        values = train[name].to_pylist()
        after = [v for v in values if v is not None and _later(v, cutoff)]
        if after:
            share = len(after) / train.num_rows
            findings.append(
                Finding(
                    Check.TIME,
                    name,
                    share,
                    f"{name} is later than the cutoff ({cutoff}) in {len(after)} training rows "
                    f"({share:.1%}): it may be recorded after the outcome",
                )
            )
    return findings


def _later(value: object, cutoff: object) -> bool:
    """``value > cutoff`` for dates and timestamps, comparing a date with a timestamp by day."""
    if not isinstance(value, dt.date) or not isinstance(cutoff, dt.date):
        raise LeakcheckError(f"cannot compare {value!r} with the cutoff {cutoff!r}")
    if isinstance(value, dt.datetime) != isinstance(cutoff, dt.datetime):
        value = value.date() if isinstance(value, dt.datetime) else value
        cutoff = cutoff.date() if isinstance(cutoff, dt.datetime) else cutoff
    return value > cutoff


def check(
    train: pa.Table,
    test: pa.Table,
    *,
    target: str,
    entities: Sequence[str] = (),
    time: str | None = None,
    ignore: Sequence[str] = (),
) -> Report:
    """Run every check that applies to ``train`` and ``test``.

    ``entities`` are columns whose values should not appear on both sides; ``time`` is the
    column the split was made on, if it was made in time; ``ignore`` lists columns to
    leave out of the feature checks.
    """
    for name in (target, *entities, *([time] if time else []), *ignore):
        for side, table in (("train", train), ("test", test)):
            if name not in table.column_names:
                raise LeakcheckError(f"column {name!r} is not in the {side} table")
    if train.num_rows == 0 or test.num_rows == 0:
        raise LeakcheckError("both tables need at least one row")
    missing = set(train.column_names) ^ set(test.column_names)
    if missing:
        raise LeakcheckError(f"train and test have different columns: {sorted(missing)}")
    try:
        test = test.select(train.column_names).cast(train.schema)
    except (pa.ArrowInvalid, pa.ArrowNotImplementedError) as error:
        raise LeakcheckError(f"test columns do not match the train types: {error}") from error

    both = pa.concat_tables([train, test])
    skip = {target, *entities, *([time] if time else []), *ignore}
    features: dict[str, _Kind] = {
        name: kind
        for name in train.column_names
        if name not in skip and (kind := _kind(both[name])) is not _Kind.SKIP
    }
    target_kind = _kind(both[target])
    numeric_target = target_kind is _Kind.NUMBER

    findings = _single_feature(train, test, target, features, numeric_target)
    findings += _row_overlap(train, test, [c for c in train.column_names if c not in ignore])
    findings += _entity_overlap(train, test, entities)
    if time is not None:
        findings += _time(train, test, time, features)
    return Report(train.num_rows, test.num_rows, tuple(findings))
