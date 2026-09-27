"""Shared pytest configuration: async tests run on asyncio."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
