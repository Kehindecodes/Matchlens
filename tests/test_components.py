"""S1: the 14 components exist, each with its responsibility and a typed primary callable."""

import importlib
import inspect
import re
import subprocess
import sys
import typing
from pathlib import Path

import pytest

ARCHITECTURE = Path(__file__).parent.parent / "docs" / "ARCHITECTURE.md"

# component name as in the architecture table -> (module, primary callables; dotted for methods)
COMPONENTS = {
    "Match Source": ("matchlens.source", ["simulate"]),
    "Ingest": ("matchlens.ingest", ["Ingest.accept", "FrameAccess.frame_window"]),
    "Understanding": ("matchlens.understanding", ["observe"]),
    "Spotting": ("matchlens.spotting", ["Spotter.consider"]),
    "Explanation": ("matchlens.explanation", ["explain"]),
    "Verification": ("matchlens.verification", ["verify"]),
    "Selection": ("matchlens.selection", ["select"]),
    "Rendering": ("matchlens.rendering", ["render"]),
    "Catch-up": ("matchlens.catchup", ["summarise"]),
    "Delivery": ("matchlens.delivery", ["ReleaseQueues.enqueue", "ReleaseQueues.release_due"]),
    "Session Clock": ("matchlens.delivery.session_clock", ["viewer_position"]),
    "Lens Registry": ("matchlens.lenses", ["get", "all_lenses"]),
    "Control": ("matchlens.control", ["mute", "is_muted"]),
    "Audit": ("matchlens.audit", ["record"]),
}


def _responsibilities() -> dict[str, str]:
    rows = re.findall(r"^\| \d+ \| \*\*(.+?)\*\* \| (.+?) \|$", ARCHITECTURE.read_text(), re.M)
    return dict(rows)


def test_the_architecture_lists_exactly_these_fourteen():
    assert set(_responsibilities()) == set(COMPONENTS)


@pytest.mark.parametrize("component", COMPONENTS)
def test_docstring_is_the_architecture_sentence(component):
    module = importlib.import_module(COMPONENTS[component][0])
    assert module.__doc__ == _responsibilities()[component]


@pytest.mark.parametrize(
    ("module_name", "name"),
    [(m, n) for m, names in COMPONENTS.values() for n in names],
)
def test_primary_callable_is_fully_annotated(module_name, name):
    fn = importlib.import_module(module_name)
    for part in name.split("."):
        fn = getattr(fn, part)
    assert callable(fn)
    signature = inspect.signature(fn)
    unannotated = [
        p for p, v in signature.parameters.items() if v.annotation is inspect._empty and p != "self"
    ]
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
