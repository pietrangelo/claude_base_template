"""Tests for tools/check_spec_changes.py, using throwaway git repositories."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_spec_changes.py"

SPEC_V1 = "# Cart\n\n### CART-001 Empty\nA new cart is empty.\n"
SPEC_V2 = "# Cart\n\n### CART-001 Empty\nA new cart is empty and has total 0.\n"
SPEC_PLUS = SPEC_V1 + "\n### CART-002 Add\nAdding a line adds it.\n"
TEST_V1 = '@pytest.mark.spec("CART-001")\ndef test_cart_001_empty(): ...\n'
TEST_V2 = TEST_V1 + "    # stricter\n"


class Repo:
    def __init__(self, path: Path):
        self.path = path
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.path, check=True, capture_output=True, text=True).stdout

    def commit(self, message: str, **files: str | None) -> None:
        for rel, text in files.items():
            p = self.path / rel.replace("__", "/")
            if text is None:
                p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def check(self, base: str = "main") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--base", base], cwd=self.path,
                              capture_output=True, text=True)


SPEC = "specs__cart__cart.md"
TEST = "tests__spec__cart__test_cart.py"
ADV = "tests__adversary__cart__test_adv.py"


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.commit("base", **{SPEC: SPEC_V1, TEST: TEST_V1, ADV: TEST_V1, "src__app.py": "X = 1\n"})
    r.git("checkout", "-q", "-b", "feature")
    return r


def test_code_only_change_passes(repo):
    repo.commit("feat", **{"src__app.py": "X = 2\n"})
    assert repo.check().returncode == 0


def test_test_edit_without_spec_change_fails(repo):
    repo.commit("tweak test", **{TEST: TEST_V2})
    result = repo.check()
    assert result.returncode == 1
    assert "CART-001" in result.stderr


def test_spec_commit_then_test_commit_passes(repo):
    repo.commit("spec: CART-001", **{SPEC: SPEC_V2})
    repo.commit("test: CART-001", **{TEST: TEST_V2})
    assert repo.check().returncode == 0, repo.check().stderr


def test_spec_and_test_in_same_commit_fails(repo):
    repo.commit("both", **{SPEC: SPEC_V2, TEST: TEST_V2})
    result = repo.check()
    assert result.returncode == 1
    assert "commit the spec first" in result.stderr


def test_spec_change_to_other_clause_does_not_unlock_test(repo):
    repo.commit("spec: CART-002", **{SPEC: SPEC_PLUS})
    repo.commit("tweak CART-001 test", **{TEST: TEST_V2})
    assert repo.check().returncode == 1


def test_deleting_a_test_needs_a_spec_change(repo):
    repo.commit("drop test", **{TEST: None})
    assert repo.check().returncode == 1


def test_first_tests_for_a_new_clause_pass(repo):
    repo.commit("spec: CART-002", **{SPEC: SPEC_PLUS})
    repo.commit("test: CART-002", **{"tests__spec__cart__test_add.py": '@pytest.mark.spec("CART-002")\n'})
    assert repo.check().returncode == 0


def test_new_spec_test_for_already_covered_clause_fails(repo):
    repo.commit("more tests", **{"tests__spec__cart__test_more.py": TEST_V1})
    assert repo.check().returncode == 1


def test_new_adversary_test_passes(repo):
    repo.commit("attack", **{"tests__adversary__cart__test_attack.py": TEST_V1})
    assert repo.check().returncode == 0


def test_editing_existing_adversary_test_fails(repo):
    repo.commit("soften attack", **{ADV: TEST_V2})
    assert repo.check().returncode == 1


def test_open_conflict_report_fails(repo):
    repo.commit("conflict", **{".tdd__conflicts__CART-001.md": "# SPEC-CONFLICT CART-001\n"})
    result = repo.check()
    assert result.returncode == 1
    assert "unresolved spec conflict" in result.stderr


def test_merge_from_base_is_ignored(repo):
    repo.commit("spec: CART-001", **{SPEC: SPEC_V2})
    repo.git("checkout", "-q", "main")
    repo.commit("main work", **{"src__other.py": "Y = 1\n"})
    repo.git("checkout", "-q", "feature")
    repo.git("merge", "-q", "--no-edit", "main")
    repo.commit("test: CART-001", **{TEST: TEST_V2})
    assert repo.check().returncode == 0
