"""pytest plugin: every spec/adversary test must be tagged with existing clause IDs.

Loaded from the root conftest.py. Usage in tests:

    @pytest.mark.spec("CART-002")
    def test_cart_002_zero_quantity_is_rejected(): ...

Collection fails for a test under tests/spec or tests/adversary that has no
`spec` marker, or whose marker names a clause that is not in specs/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tdd.specs import TEST_DIRS, SpecError, load_clauses

_clauses: dict | None = None


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "spec(*ids): spec clause IDs this test verifies")


def _guarded(path: Path, rootdir: Path) -> bool:
    try:
        rel = path.resolve().relative_to(rootdir.resolve()).as_posix()
    except ValueError:
        return False
    return any(rel == d or rel.startswith(d + "/") for d in TEST_DIRS)


def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: list) -> None:
    global _clauses
    try:
        _clauses = load_clauses(Path(config.rootpath))
    except SpecError as exc:
        raise pytest.UsageError(f"spec error: {exc}") from exc

    problems = []
    for item in items:
        if not _guarded(Path(item.path), Path(config.rootpath)):
            continue
        ids = [i for m in item.iter_markers("spec") for i in m.args]
        if not ids:
            problems.append(f"{item.nodeid}: missing @pytest.mark.spec(<clause id>)")
            continue
        for cid in ids:
            if cid not in _clauses:
                problems.append(f"{item.nodeid}: clause {cid} is not in specs/ (orphan test)")
        item.user_properties.append(("spec", ",".join(ids)))

    if problems:
        raise pytest.UsageError(
            "spec traceability check failed:\n  " + "\n  ".join(problems)
            + "\nTests must be regenerated from the spec, not edited to fit the code."
        )
