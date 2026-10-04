#!/usr/bin/env python3
"""CI backstop: tests may only change after the spec clauses they verify changed.

Walks the commits in BASE..HEAD in order. For every commit that touches tests:

  tests/spec/**       any change (add, modify, delete, rename) must reference at
                      least one clause that was changed by an EARLIER commit in the
                      range. Exception: a new test file whose clauses had no test
                      at BASE (first-time coverage of an existing clause).
  tests/adversary/**  new files are always allowed (that is the adversary's job);
                      modifying or deleting existing ones follows the tests/spec rule.

"Changed clause" means a clause whose ID, title or text differs between the
commit's parent and the commit, in any specs/**/*.md file.

It also fails while unresolved conflict reports exist in .tdd/conflicts/.

    python3 tools/check_spec_changes.py --base origin/main
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tdd.specs import TEST_DIRS, clause_refs, is_spec_path, parse_spec_text, prefix_of  # noqa: E402

ZERO_SHA = "0" * 40
SPEC_TESTS, ADVERSARY_TESTS = TEST_DIRS
CONFLICTS_DIR = ".tdd/conflicts"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def show(rev: str | None, path: str) -> str | None:
    if rev is None:
        return None
    try:
        return git("show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return None


def ls_files(rev: str | None, prefix: str) -> list[str]:
    if rev is None:
        return []
    out = git("ls-tree", "-r", "--name-only", rev, "--", prefix)
    return [line for line in out.splitlines() if line]


def under(path: str, directory: str) -> bool:
    return path.startswith(directory + "/")


def clauses_at(rev: str | None) -> dict[str, str]:
    """clause id -> title + text, for every spec file at `rev`."""
    result = {}
    for path in ls_files(rev, "specs"):
        if is_spec_path(path):
            for c in parse_spec_text(show(rev, path) or "", path):
                result[c.id] = f"{c.title}\n{c.text}"
    return result


def changed_clause_ids(parent: str | None, commit: str, spec_paths: list[str]) -> set[str]:
    changed = set()
    for path in spec_paths:
        before = {c.id: (c.title, c.text) for c in parse_spec_text(show(parent, path) or "", path)}
        after = {c.id: (c.title, c.text) for c in parse_spec_text(show(commit, path) or "", path)}
        for cid in before.keys() | after.keys():
            if before.get(cid) != after.get(cid):
                changed.add(cid)
    return changed


def commit_changes(commit: str) -> tuple[list[str], list[tuple[str, str, str | None]]]:
    """(parents, [(status, path, old_path)]) relative to the first parent."""
    parents = git("rev-list", "--parents", "-n", "1", commit).split()[1:]
    parent = parents[0] if parents else None
    args = ["diff-tree", "-r", "-M", "--name-status", "--no-commit-id"]
    out = git(*args, parent, commit) if parent else git(*args, "--root", commit)
    changes = []
    for line in out.splitlines():
        fields = line.split("\t")
        status = fields[0][0]
        if status == "R":
            changes.append(("R", fields[2], fields[1]))
        else:
            changes.append((status, fields[1], None))
    return parents, changes


def resolve_base(base: str | None) -> str | None:
    if not base or base == ZERO_SHA:
        return None
    try:
        return git("merge-base", base, "HEAD").strip()
    except subprocess.CalledProcessError:
        sys.exit(f"cannot resolve base {base!r}; fetch full history (fetch-depth: 0)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", help="base ref or sha; omit to check the whole history")
    args = parser.parse_args(argv)

    base = resolve_base(args.base)
    rev_range = f"{base}..HEAD" if base else "HEAD"
    commits = git("rev-list", "--reverse", "--topo-order", rev_range).split()

    base_clauses = clauses_at(base)
    prefixes = {prefix_of(cid) for cid in base_clauses}
    covered_at_base: set[str] = set()
    for path in ls_files(base, "tests"):
        if under(path, SPEC_TESTS) or under(path, ADVERSARY_TESTS):
            covered_at_base |= clause_refs(show(base, path) or "", prefixes)

    errors: list[str] = []
    changed_before: set[str] = set()  # clauses changed by earlier commits in the range

    for commit in commits:
        parents, changes = commit_changes(commit)
        if len(parents) > 1:
            continue  # merge commit: integrates already-checked history
        parent = parents[0] if parents else None
        short = commit[:10]
        subject = git("log", "-1", "--format=%s", commit).strip()

        touched = {path for _, path, _ in changes} | {old for _, _, old in changes if old}
        spec_paths = sorted(p for p in touched if is_spec_path(p))
        changed_now = changed_clause_ids(parent, commit, spec_paths)
        prefixes |= {prefix_of(cid) for cid in changed_now}

        for status, path, old_path in changes:
            in_spec = under(path, SPEC_TESTS) or bool(old_path and under(old_path, SPEC_TESTS))
            in_adv = under(path, ADVERSARY_TESTS) or bool(old_path and under(old_path, ADVERSARY_TESTS))
            if not (in_spec or in_adv):
                continue
            if in_adv and not in_spec and status == "A":
                continue
            refs = clause_refs(show(commit, path) or "", prefixes)
            refs |= clause_refs(show(parent, old_path or path) or "", prefixes)
            if refs & changed_before:
                continue
            if status == "A" and refs and not (refs & covered_at_base):
                continue  # first tests for clauses that had none
            hint = ""
            if refs & changed_now:
                hint = " The spec change is in the same commit: commit the spec first, then the tests."
            errors.append(
                f"{short} {subject!r}: {status} {path} references {sorted(refs) or 'no clause'}, "
                f"but none of those clauses changed in an earlier spec commit.{hint}"
            )

        changed_before |= changed_now

    head_conflicts = [p for p in ls_files("HEAD", CONFLICTS_DIR) if p.endswith(".md")]
    for path in head_conflicts:
        errors.append(f"unresolved spec conflict report: {path}. Resolve it with a spec commit, then delete it.")

    if errors:
        print("Spec-first check failed. Tests are regenerated from the spec, never edited to fit the code.",
              file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"spec-first check: {len(commits)} commits OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
