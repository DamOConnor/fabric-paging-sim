"""Shared pytest fixtures."""
from types import SimpleNamespace

import pytest


def _make_req(params: dict | None = None, url: str = "http://localhost:7071/api/paging/x") -> SimpleNamespace:
    """Build a minimal stand-in for azure.functions.HttpRequest.

    Only `.params` (mapping) and `.url` (str) are consumed by the
    pagination strategies.
    """
    return SimpleNamespace(params=dict(params or {}), url=url)


@pytest.fixture
def make_req():
    return _make_req


@pytest.fixture
def base_url() -> str:
    return "http://localhost:7071"
