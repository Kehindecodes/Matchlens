"""S1: the 13 components exist, each with its responsibility and a typed primary callable."""

import importlib
import inspect
import re
import subprocess
import sys
import typing
from pathlib import Path

import pytest

ARCHITECTURE = Path(__file__).parent.parent / "docs" / "ARCHITECTURE.md"

# component name as in the architecture table -> (module, primary callables)
COMPONENTS = {
    "Match Source": ("matchlens.source", ["simulate"]),
    "Ingest": ("matchlens.ingest", ["accept", "frame_window"]),
    "Understanding": ("matchlens.understanding", ["observe"]),
    "Spotting": ("matchlens.spotting", ["consider"]),
    "Explanation": ("matchlens.explanation", ["explain"]),
    "Verification": ("matchlens.verification", ["verify"]),
    "Personalization": ("matchlens.personalization", ["render"]),
    "Catch-up": ("matchlens.catchup", ["summarise"]),
    "Delivery": ("matchlens.delivery", ["enqueue", "release_due"]),
    "Session Clock": ("matchlens.delivery.session_clock", ["viewer_position"]),
    "Lens Registry": ("matchlens.lenses", ["get", "all_lenses"]),
    "Control": ("matchlens.control", ["mute", "is_muted"]),
    "Audit": ("matchlens.audit", ["record"]),
}

# Their architecture sentences contain "and" (Q5). Remove once the table is settled.
_HAS_AND = {"Match Source", "Ingest", "Verification", "Personalization", "Audit"}


def _responsibilities() -> dict[str, str]:
    rows = re.findall(r"^\| \d+ \| \*\*(.+?)\*\* \| (.+?) \|$", ARCHITECTURE.read_text(), re.M)
    return dict(rows)


def test_the_architecture_lists_exactly_these_thirteen():
    assert set(_responsibilities()) == set(COMPONENTS)


@pytest.mark.parametrize("component", COMPONENTS)
def test_docstring_is_the_architecture_sentence(component):
    module = importlib.import_module(COMPONENTS[component][0])
    assert module.__doc__ == _responsibilities()[component]


@pytest.mark.parametrize(
    "component",
    [
        pytest.param(c, marks=pytest.mark.xfail(strict=True, reason="Q5")) if c in _HAS_AND else c
        for c in COMPONENTS
    ],
)
def test_responsibility_has_no_and(component):
    module = importlib.import_module(COMPONENTS[component][0])
    assert not re.search(r"\band\b", module.__doc__ or "")


@pytest.mark.parametrize(
    ("module_name", "name"),
    [(m, n) for m, names in COMPONENTS.values() for n in names],
)
def test_primary_callable_is_fully_annotated(module_name, name):
    fn = getattr(importlib.import_module(module_name), name)
    assert callable(fn)
    signature = inspect.signature(fn)
    unannotated = [p for p, v in signature.parameters.items() if v.annotation is inspect._empty]
    assert not unannotated, f"{name} has unannotated parameters: {unannotated}"
    assert signature.return_annotation is not inspect.Signature.empty
    typing.get_type_hints(fn)  # every annotation resolves


@pytest.mark.parametrize("module_name", [m for m, _ in COMPONENTS.values()])
def test_imports_cleanly_with_no_side_effects(module_name):
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        capture_output=True,
        text=True,
        cwd=ARCHITECTURE.parent.parent,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
