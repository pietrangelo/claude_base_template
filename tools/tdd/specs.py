"""Parse spec files into clauses and find clause references in test files.

The format is documented in specs/README.md. Kept free of third-party
dependencies so every tool and CI job can import it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = ROOT / "specs"
TEST_DIRS = ("tests/spec", "tests/adversary")

CLAUSE_ID = r"[A-Z][A-Z0-9]*-\d{3}"
CLAUSE_ID_RE = re.compile(rf"\b({CLAUSE_ID})\b")
CLAUSE_HEADING_RE = re.compile(rf"^###\s+({CLAUSE_ID})\b\s*(.*)$")
HEADING_RE = re.compile(r"^#{1,6}\s")
# Test files reference clauses either as `CART-003` or, in test names, `cart_003`.
TEST_REF_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*)[-_](\d{3})(?!\d)")


@dataclass(frozen=True)
class Clause:
    id: str
    title: str
    text: str
    path: str
    line: int


class SpecError(Exception):
    pass


def parse_spec_text(text: str, path: str) -> list[Clause]:
    clauses: list[Clause] = []
    current: dict | None = None
    body: list[str] = []

    def close() -> None:
        if current is not None:
            clauses.append(Clause(text="\n".join(body).strip(), **current))

    for lineno, line in enumerate(text.splitlines(), start=1):
        match = CLAUSE_HEADING_RE.match(line)
        if match:
            close()
            current = {"id": match.group(1), "title": match.group(2).strip(), "path": path, "line": lineno}
            body = []
        elif HEADING_RE.match(line):
            close()
            current, body = None, []
        elif current is not None:
            body.append(line.rstrip())
    close()
    return clauses


def spec_files(specs_dir: Path = SPECS_DIR) -> list[Path]:
    return sorted(p for p in specs_dir.rglob("*.md") if is_spec_path(str(p.relative_to(specs_dir.parent))))


def is_spec_path(rel_path: str) -> bool:
    """True for specs/**/*.md except README and files whose name starts with `_`."""
    p = Path(rel_path)
    return (
        p.parts[:1] == ("specs",)
        and p.suffix == ".md"
        and p.name != "README.md"
        and not p.name.startswith("_")
    )


def load_clauses(root: Path = ROOT) -> dict[str, Clause]:
    """All clauses by ID. Raises SpecError on duplicate IDs."""
    clauses: dict[str, Clause] = {}
    for path in spec_files(root / "specs"):
        rel = str(path.relative_to(root))
        for clause in parse_spec_text(path.read_text(encoding="utf-8"), rel):
            if clause.id in clauses:
                other = clauses[clause.id]
                raise SpecError(
                    f"duplicate clause id {clause.id}: {other.path}:{other.line} and {rel}:{clause.line}"
                )
            clauses[clause.id] = clause
    return clauses


def clause_refs(text: str, known_prefixes: set[str]) -> set[str]:
    """Clause IDs referenced in a test file, in either `CART-003` or `cart_003` form.

    Only prefixes that exist in the specs count, so unrelated tokens such as
    `utf-8` or `sha-256` are not mistaken for clause references. A reference
    with a known prefix but an unknown number is returned and reported as an orphan.
    """
    refs = set()
    for prefix, number in TEST_REF_RE.findall(text):
        if prefix.upper() in known_prefixes:
            refs.add(f"{prefix.upper()}-{number}")
    return refs


def prefix_of(clause_id: str) -> str:
    return clause_id.rsplit("-", 1)[0]
