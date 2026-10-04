"""Tests for tools/new_project.py, run against a copy of the template."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[2]
SCRIPT = TEMPLATE / "tools" / "new_project.py"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "proj"
    shutil.copytree(TEMPLATE, dest, ignore=shutil.ignore_patterns(".git", "mutants", "__pycache__", ".pytest_cache"))
    return dest


def bootstrap(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(project / "tools" / "new_project.py"), *args],
                          capture_output=True, text=True)


def test_bootstrap_removes_example_and_leaves_a_green_empty_project(project):
    result = bootstrap(project, "--package", "billing_app", "--context", "invoicing", "--prefix", "INV")
    assert result.returncode == 0, result.stderr

    assert not (project / "specs/cart").exists()
    assert not (project / "src/shop").exists()
    assert not (project / "tests/spec/cart").exists()
    assert (project / "src/billing_app/invoicing/__init__.py").exists()
    assert "Clause prefix: `INV`" in (project / "specs/invoicing/invoicing.md").read_text()
    assert 'name = "billing-app"' in (project / "pyproject.toml").read_text()

    trace = subprocess.run([sys.executable, "tools/spec_trace.py"], cwd=project, capture_output=True, text=True)
    assert trace.returncode == 0, trace.stderr
    gate = subprocess.run([sys.executable, "tools/mutation_gate.py"], cwd=project, capture_output=True, text=True)
    assert gate.returncode == 0, gate.stderr


def test_bootstrap_runs_only_once(project):
    assert bootstrap(project, "--package", "app").returncode == 0
    again = bootstrap(project, "--package", "other")
    assert again.returncode == 1
    assert "already" in again.stderr


def test_context_needs_prefix(project):
    assert bootstrap(project, "--package", "app", "--context", "invoicing").returncode == 2
    assert (project / "specs/cart").exists()
