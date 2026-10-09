import importlib

import pytest

MODULES = [
    "config",
    "models",
    "source",
    "ingest",
    "understanding",
    "spotting",
    "explanation",
    "verification",
    "personalization",
    "catchup",
    "delivery",
    "lenses",
    "control",
    "audit",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(f"matchlens.{name}")


def test_apps_package_imports():
    importlib.import_module("apps")
