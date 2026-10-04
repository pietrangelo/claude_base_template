#!/usr/bin/env python3
"""Trace spec clauses to tests.

Fails (exit 1) when:
  - two clauses share an ID,
  - a test file references a clause that no longer exists (orphan test),
  - a clause has no test referencing it (uncovered clause), unless --allow-uncovered.

Language-agnostic: test files are scanned textually for clause IDs.

    python3 tools/spec_trace.py                 # check
    python3 tools/spec_trace.py --report        # also print the clause -> tests matrix
    python3 tools/spec_trace.py --allow-uncovered CART-007   # tolerate specific gaps
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tdd.specs import ROOT, TEST_DIRS, SpecError, clause_refs, load_clauses, prefix_of  # noqa: E402

SKIP_DIRS = {"__pycache__", "node_modules", ".pytest_cache"}


def test_files(root: Path) -> list[Path]:
    files = []
    for test_dir in TEST_DIRS:
        base = root / test_dir
        if base.exists():
            files += [
                p for p in base.rglob("*")
                if p.is_file() and not SKIP_DIRS.intersection(p.parts) and p.suffix not in {".pyc"}
            ]
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", action="store_true", help="print the clause -> tests matrix")
    parser.add_argument("--allow-uncovered", nargs="*", metavar="ID",
                        help="tolerate uncovered clauses (all if no IDs given)")
    args = parser.parse_args(argv)

    try:
        clauses = load_clauses(ROOT)
    except SpecError as exc:
        print(f"spec error: {exc}", file=sys.stderr)
        return 1

    prefixes = {prefix_of(cid) for cid in clauses}
    covered: dict[str, list[str]] = defaultdict(list)
    orphans: list[tuple[str, str]] = []
    for path in test_files(ROOT):
        rel = str(path.relative_to(ROOT))
        for ref in sorted(clause_refs(path.read_text(encoding="utf-8", errors="replace"), prefixes)):
            if ref in clauses:
                covered[ref].append(rel)
            else:
                orphans.append((rel, ref))

    allowed = args.allow_uncovered
    uncovered = [
        cid for cid in sorted(clauses)
        if cid not in covered and not (allowed == [] or (allowed and cid in allowed))
    ]

    if args.report:
        for cid in sorted(clauses):
            files = ", ".join(sorted(set(covered.get(cid, [])))) or "-- no tests --"
            print(f"{cid:<14} {clauses[cid].title[:40]:<40} {files}")
        print()

    ok = True
    for rel, ref in orphans:
        ok = False
        print(f"ORPHAN    {rel}: references {ref}, which is not in any spec. "
              f"Regenerate this test from the current spec.", file=sys.stderr)
    for cid in uncovered:
        ok = False
        c = clauses[cid]
        print(f"UNCOVERED {cid} ({c.path}:{c.line}) has no test. Run the test-author agent for it.",
              file=sys.stderr)

    print(f"spec trace: {len(clauses)} clauses, {len(covered)} covered, "
          f"{len(uncovered)} uncovered, {len(orphans)} orphan references")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
