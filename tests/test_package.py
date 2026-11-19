import leakcheck


def test_version_is_set() -> None:
    assert leakcheck.__version__
