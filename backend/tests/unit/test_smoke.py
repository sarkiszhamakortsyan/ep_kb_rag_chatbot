"""Smoke test: the backend package imports."""

import app


def test_package_imports() -> None:
    assert app.__version__
