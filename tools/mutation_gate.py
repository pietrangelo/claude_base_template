#!/usr/bin/env python3
"""Mutation-testing gate: fail when mutants survive the test suite.

Surviving mutants mean the tests do not constrain the implementation. Each one
must be killed by a new test derived from an existing clause (adversary), or
reveal a missing clause (spec change), or be marked as an equivalent mutant in
the source with `# pragma: no mutate (<reason>)`.

    python3 tools/mutation_gate.py                    # run mutmut, allow 0 survivors
    python3 tools/mutation_gate.py --max-survivors 2
    python3 tools/mutation_gate.py --no-run           # only evaluate the last run

Uses mutmut (configured in pyproject.toml). For another language, swap the
commands below for your mutation tool (Stryker, PIT, cargo-mutants, ...) and keep the gate.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATS = ROOT / "mutants" / "mutmut-cicd-stats.json"
BAD = ("survived", "no_tests", "suspicious", "timeout", "segfault")


def has_code(src: Path) -> bool:
    return any(p.stat().st_size and p.name != "__init__.py" for p in src.rglob("*.py"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-survivors", type=int, default=0)
    parser.add_argument("--no-run", action="store_true", help="evaluate the previous run only")
    args = parser.parse_args(argv)

    if not has_code(ROOT / "src"):
        print("mutation gate: no code under src/ yet, nothing to mutate")
        return 0

    if not args.no_run:
        # mutmut caches results per source hash and does not notice new tests: start clean.
        shutil.rmtree(ROOT / "mutants", ignore_errors=True)
        run = subprocess.run(["mutmut", "run"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if run.returncode != 0:
            print(run.stderr, file=sys.stderr)
            print("mutmut run failed (the suite must pass unmutated first)", file=sys.stderr)
            return 1
    subprocess.run(["mutmut", "export-cicd-stats"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    stats = json.loads(STATS.read_text())

    escaped = sum(stats.get(k, 0) for k in BAD)
    total = stats.get("total", 0)
    score = 100.0 * stats.get("killed", 0) / total if total else 100.0
    print(f"mutation score {score:.1f}% ({stats.get('killed', 0)}/{total} killed, {escaped} not killed: "
          + ", ".join(f"{k}={stats.get(k, 0)}" for k in BAD) + ")")

    if escaped > args.max_survivors:
        results = subprocess.run(["mutmut", "results"], cwd=ROOT, capture_output=True, text=True).stdout
        print("\nMutants not killed (inspect with `mutmut show <name>`):", file=sys.stderr)
        print(results, file=sys.stderr)
        print(f"FAIL: {escaped} mutants not killed, at most {args.max_survivors} allowed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
