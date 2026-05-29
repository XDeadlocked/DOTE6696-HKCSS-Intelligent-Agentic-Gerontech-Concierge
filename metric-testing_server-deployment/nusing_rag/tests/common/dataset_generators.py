from __future__ import annotations

from pathlib import Path

from tests.common.io import read_json


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def get_fixture_dir(module_name: str) -> Path:
    return FIXTURES_DIR / module_name


def load_fixture_json(module_name: str, filename: str):
    return read_json(get_fixture_dir(module_name) / filename)


def load_manifest() -> dict:
    return read_json(FIXTURES_DIR / "manifest.json")
