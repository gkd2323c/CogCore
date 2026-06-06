"""Pytest configuration for CogCore."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


def pytest_addoption(parser):
    parser.addoption(
        "--evals",
        action="store_true",
        default=False,
        help="Run opt-in evals/ tests.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "evals: opt-in evaluation tests")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--evals"):
        return

    import pytest

    skip_evals = pytest.mark.skip(reason="need --evals option to run")
    for item in items:
        if "evals" in item.keywords:
            item.add_marker(skip_evals)


@pytest.fixture
def client():
    """FastAPI TestClient fixture（全局可用）。"""
    return TestClient(app)
