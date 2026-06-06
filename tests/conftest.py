"""Fixtures compartidas de la suite de tests."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA = REPO_ROOT / "examples" / "caso_demo" / "datos" / "tablas"


@pytest.fixture
def demo_data_dir() -> Path:
    return DEMO_DATA


@pytest.fixture
def demo_config() -> Path:
    return REPO_ROOT / "examples" / "caso_demo" / "config.yaml"
