"""Tests for .claude/hooks/guard.py, run against a throwaway project directory."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "guard.py"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for rel, text in {
        "specs/cart/cart.md": "### CART-001 x\ny\n",
        "src/shop/cart.py": "X = 1\n",
        "tests/spec/cart/test_cart.py": "# CART-001\n",
        "tests/adversary/cart/test_adv.py": "# CART-001\n",
        ".claude/settings.json": "{}\n",
    }.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return tmp_path


def run(project: Path, event: str, agent: str | None = None, **fields) -> dict | None:
    data = {"hook_event_name": event, "session_id": "s", "cwd": str(project), **fields}
    if agent:
        data.update(agent_type=agent, agent_id=fields.get("agent_id", f"{agent}-1"))
    out = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(data), capture_output=True, text=True,
                         env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)}, check=True).stdout
    return json.loads(out) if out.strip() else None


def tool(project: Path, agent: str | None, name: str, **tool_input) -> bool:
    """True when the guard allows the call."""
    result = run(project, "PreToolUse", agent, tool_name=name, tool_input=tool_input)
    return result is None or result["hookSpecificOutput"]["permissionDecision"] != "deny"


def write(project, agent, path):
    return tool(project, agent, "Write", file_path=str(project / path), content="x")


def bash(project, agent, command):
    return tool(project, agent, "Bash", command=command)


@pytest.mark.parametrize("agent, path, allowed", [
    ("test-author", "tests/spec/cart/test_new.py", True),
    ("test-author", "tests/adversary/cart/test_x.py", False),
    ("test-author", "src/shop/cart.py", False),
    ("test-author", "specs/cart/cart.md", False),
    ("implementer", "src/shop/cart.py", True),
    ("implementer", ".tdd/conflicts/CART-001.md", True),
    ("implementer", "tests/spec/cart/test_cart.py", False),
    ("implementer", "tests/adversary/cart/test_adv.py", False),
    ("implementer", "specs/cart/cart.md", False),
    ("implementer", "/tmp/elsewhere.py", False),
    ("adversary", "tests/adversary/cart/test_adv.py", True),
    ("adversary", "tests/spec/cart/test_cart.py", False),
    ("adversary", "src/shop/cart.py", False),
    (None, "specs/cart/cart.md", True),
    (None, "src/shop/cart.py", False),
    (None, "tests/spec/cart/test_cart.py", False),
    (None, ".claude/settings.json", False),
    (None, "tools/spec_trace.py", False),
    ("general-purpose", "src/shop/cart.py", False),
])
def test_write_policy(project, agent, path, allowed):
    assert write(project, agent, path) is allowed


@pytest.mark.parametrize("agent, path, allowed", [
    ("test-author", "specs/cart/cart.md", True),
    ("test-author", "tests/spec/cart/test_cart.py", True),
    ("test-author", "src/shop/cart.py", False),
    ("adversary", "src/shop/cart.py", True),
    ("adversary", ".tdd/conflicts/CART-001.md", False),
    ("implementer", "tests/spec/cart/test_cart.py", True),
])
def test_read_policy(project, agent, path, allowed):
    assert tool(project, agent, "Read", file_path=str(project / path)) is allowed


def test_test_author_cannot_search_without_explicit_path(project):
    assert not tool(project, "test-author", "Grep", pattern="def ")
    assert not tool(project, "test-author", "Grep", pattern="def ", path=str(project / "src"))
    assert tool(project, "test-author", "Grep", pattern="CART", path=str(project / "specs"))
    assert not tool(project, "test-author", "Glob", pattern="../src/*.py", path=str(project / "specs"))


@pytest.mark.parametrize("agent, command, allowed", [
    ("test-author", "python3 -m pytest --collect-only -q", True),
    ("test-author", "python3 -m pytest -q", False),
    ("test-author", "cat src/shop/cart.py", False),
    ("implementer", "python3 -m pytest -q tests/spec", True),
    ("implementer", "python3 -m pytest -q tests/spec/cart/test_cart.py::test_x", True),
    ("implementer", "python3 -m pytest -p no:tdd.pytest_plugin", False),
    ("implementer", "python3 -m pytest -pno:tdd.pytest_plugin", False),
    ("implementer", "python3 -m pytest -q && rm -rf tests", False),
    ("implementer", "echo x > tests/spec/cart/test_cart.py", False),
    ("implementer", "sed -i s/1/2/ tests/spec/cart/test_cart.py", False),
    ("implementer", "git log --oneline", True),
    ("implementer", "git checkout -- tests", False),
    ("adversary", "mutmut show shop.cart.domain.x__mutmut_1", True),
    ("adversary", "python3 tools/mutation_gate.py", True),
    ("adversary", "git log", False),
    ("adversary", "cat .tdd/conflicts/CART-001.md", False),
    (None, "python3 -m pytest tests/ -q 2>&1", True),
    (None, "git add specs tests && git commit -m 'test: CART-001'", True),
    (None, "echo x > tests/spec/cart/test_cart.py", False),
    (None, "sed -i s/1/2/ src/shop/cart.py", False),
    (None, "rm .claude/settings.json", False),
    (None, "python3 -c \"import os; os.rename('.claude/settings.json', 'x')\"", False),
])
def test_bash_policy(project, agent, command, allowed):
    assert bash(project, agent, command) is allowed


def test_subagent_stop_reverts_changes_to_protected_files(project):
    run(project, "SubagentStart", "implementer", agent_id="impl-1")
    test_file = project / "tests/spec/cart/test_cart.py"
    test_file.write_text("# weakened\n")
    (project / "tests/spec/cart/test_sneaky.py").write_text("# new\n")
    (project / "src/shop/cart.py").write_text("X = 2\n")  # allowed change

    result = run(project, "SubagentStop", "implementer", agent_id="impl-1", stop_hook_active=False)

    assert result["decision"] == "block"
    assert "tests/spec/cart/test_cart.py" in result["reason"]
    assert test_file.read_text() == "# CART-001\n"
    assert not (project / "tests/spec/cart/test_sneaky.py").exists()
    assert (project / "src/shop/cart.py").read_text() == "X = 2\n"
    assert "implementer" in (project / ".tdd/violations.log").read_text()


def test_subagent_stop_passes_clean_run(project):
    run(project, "SubagentStart", "test-author", agent_id="ta-1")
    (project / "tests/spec/cart/test_more.py").write_text("# CART-001\n")
    assert run(project, "SubagentStop", "test-author", agent_id="ta-1", stop_hook_active=False) is None
    assert not (project / ".tdd/state/ta-1.json").exists()


def test_implementer_must_stop_after_filing_conflict(project):
    def write_src():
        return run(project, "PreToolUse", "implementer", agent_id="impl-2", tool_name="Write",
                   tool_input={"file_path": str(project / "src/shop/cart.py"), "content": "x"})

    run(project, "SubagentStart", "implementer", agent_id="impl-2")
    assert write_src() is None
    (project / ".tdd/conflicts").mkdir(parents=True)
    (project / ".tdd/conflicts/CART-001.md").write_text("# SPEC-CONFLICT CART-001\n")
    denied = write_src()
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "SPEC-CONFLICT" in denied["hookSpecificOutput"]["permissionDecisionReason"]


def spawn(project, n):
    return tool(project, None, "Agent", subagent_type="implementer", prompt=f"job {n}", description="x")


def test_at_most_three_agents_run_at_once(project):
    assert all(spawn(project, i) for i in range(3))  # parallel spawns in one turn reserve slots
    assert not spawn(project, 4)
    for i, agent in enumerate(["test-author", "implementer", "general-purpose"]):
        run(project, "SubagentStart", agent, agent_id=f"a{i}")
    assert not spawn(project, 5)

    assert run(project, "SubagentStop", "general-purpose", agent_id="a2", stop_hook_active=False) is None
    assert spawn(project, 6)
    assert not spawn(project, 7)


def test_agent_blocked_on_stop_keeps_its_slot(project):
    for i in range(3):
        spawn(project, i)
        run(project, "SubagentStart", "implementer", agent_id=f"i{i}")
    (project / "tests/spec/cart/test_cart.py").write_text("# weakened\n")
    blocked = run(project, "SubagentStop", "implementer", agent_id="i0", stop_hook_active=False)
    assert blocked["decision"] == "block"
    assert not spawn(project, 9)
    run(project, "SubagentStop", "implementer", agent_id="i0", stop_hook_active=True)
    assert spawn(project, 10)
