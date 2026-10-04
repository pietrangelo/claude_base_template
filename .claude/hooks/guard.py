#!/usr/bin/env python3
"""Role guard: mechanically enforces which agent may read, write and run what.

Registered in .claude/settings.json for PreToolUse, SubagentStart and SubagentStop.
The role comes from the hook input's `agent_type` (the subagent's name); the main
session and any other agent get the `orchestrator` policy.

PreToolUse    denies file writes, reads and Bash commands outside the role's policy,
              and denies spawning a subagent when MAX_CONCURRENT_AGENTS already run.
SubagentStart snapshots every protected file the role may not change.
SubagentStop  compares against the snapshot; any change made by other means (for
              example through Bash) is reverted and the agent is told why.

Stdlib only. Policy lives in POLICIES below; keep it in sync with .claude/agents/.
Tests: tools/tests/test_guard.py.
"""

from __future__ import annotations

import base64
import fnmatch
import json
import os
import re
import shlex
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no lock, the cap stays best-effort
    fcntl = None

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()
STATE_DIR = ROOT / ".tdd" / "state"
CONFLICTS_DIR = ".tdd/conflicts"
VIOLATIONS_LOG = ROOT / ".tdd" / "violations.log"

# At most this many subagents run at once, whatever their type.
MAX_CONCURRENT_AGENTS = 3
AGENT_TOOLS = {"Agent", "Task"}
AGENT_SLOTS = STATE_DIR / "agents.json"
# Stale entries (a spawn the user declined, a crashed session) stop counting after these many seconds.
PENDING_TTL = 10 * 60
RUNNING_TTL = 4 * 60 * 60

# Nobody, including the orchestrator, may change the enforcement machinery from inside Claude Code.
INFRA = [".claude/**", "tools/**", ".github/**", "conftest.py", "pyproject.toml"]
# Everything the guard snapshots for subagents.
PROTECTED_ROOTS = ["specs", "tests", "src", "tools", ".claude", ".github", ".tdd/conflicts",
                   "conftest.py", "pyproject.toml", "CLAUDE.md"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", "mutants", "node_modules"}

# Bash for subagents: one simple command, no chaining, redirection or substitution.
SHELL_META = re.compile(r"[;&|<>`\n]|\$\(")
PYTEST = [["pytest"], ["python", "-m", "pytest"], ["python3", "-m", "pytest"]]
# pytest flags that would switch off or bypass the spec-traceability plugin.
PYTEST_FORBIDDEN = ("-p", "-o", "-c", "--override-ini", "--noconftest", "--confcutdir", "--rootdir", "--config-file")
GIT_READ = [["git", "status"], ["git", "diff"], ["git", "log"], ["git", "show"]]

POLICIES: dict[str, dict] = {
    "test-author": {
        "write": ["tests/spec/**"],
        "read": ["specs/**", "tests/**", "CLAUDE.md", "README.md"],
        "bash": [["pytest", "--collect-only"], ["python", "-m", "pytest", "--collect-only"],
                 ["python3", "-m", "pytest", "--collect-only"], ["python3", "tools/spec_trace.py"],
                 ["git", "status"]],
        "why": "The test-author derives tests from specs/ only. It may not read src/ or write outside tests/spec/.",
    },
    "implementer": {
        "write": ["src/**", f"{CONFLICTS_DIR}/*.md"],
        "read": ["**"],
        "bash": PYTEST + [["python3", "tools/spec_trace.py"], ["ls"]] + GIT_READ,
        "why": "The implementer may only change src/. If a test looks wrong, write a conflict report "
               f"to {CONFLICTS_DIR}/<CLAUSE-ID>.md and stop; never edit tests or specs.",
    },
    "adversary": {
        "write": ["tests/adversary/**"],
        "read": ["specs/**", "src/**", "tests/**", "CLAUDE.md", "README.md", "pyproject.toml"],
        "bash": PYTEST + [["mutmut", "run"], ["mutmut", "results"], ["mutmut", "show"],
                          ["python3", "tools/mutation_gate.py"], ["python3", "tools/spec_trace.py"],
                          ["git", "status"]],
        "why": "The adversary attacks the code through tests in tests/adversary/ only. It does not read "
               "the implementer's notes (.tdd/, git history) and may not change src/, specs/ or tests/spec/.",
    },
    "orchestrator": {
        "write_deny": ["src/**", "tests/**", ".tdd/state/**"] + INFRA,
        "why": "The orchestrator writes specs and delegates: tests come from the test-author agent, "
               "code from the implementer agent, attacks from the adversary agent.",
    },
}

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead"}
# Bash in the orchestrator: a speed bump against writing protected paths by shell. It is a
# heuristic; CI (tools/check_spec_changes.py) is the backstop.
SHELL_REDIRECT = re.compile(r">>?\s*['\"]?(\./)?(src|tests|tools|\.claude|\.github|\.tdd)/")
SHELL_WRITE = re.compile(
    r"(\btee\b|\bsed\s+-i|\bperl\s+-\w*i|\bcp\b|\bmv\b|\brm\b|\btouch\b|\bln\b|\btruncate\b|\bdd\b|\binstall\b"
    r"|\bpatch\b|git\s+(checkout|restore|rm|mv|apply|stash|reset)|open\(|write_text|write_bytes"
    r"|os\.(rename|replace|remove|unlink)|shutil\.|rmtree|\.unlink\(|\.rename\()"
)
SHELL_PROTECTED = re.compile(
    r"(^|[\s'\"=(])(\./)?(src|tests|tools|\.claude|\.github|\.tdd/state)(/|\s|$)|conftest\.py|pyproject\.toml"
)


# ---------------------------------------------------------------- helpers

def rel(path: str | None) -> str | None:
    """Project-relative POSIX path, or None when outside the project."""
    if not path:
        return None
    p = Path(path)
    p = (p if p.is_absolute() else ROOT / p).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return None


def matches(path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatchcase(path, pat):
            return True
        if pat.endswith("/**") and (path == pat[:-3] or path.startswith(pat[:-2])):
            return True
    return False


def role_of(data: dict) -> str:
    agent = data.get("agent_type") or ""
    return agent if agent in POLICIES and agent != "orchestrator" else "orchestrator"


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    sys.exit(0)


def log_violation(role: str, message: str) -> None:
    VIOLATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with VIOLATIONS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now(timezone.utc).isoformat()} {role}: {message}\n")


def forbidden_pytest_flag(arg: str) -> bool:
    return any(arg == f or arg.startswith(f + "=") or (len(f) == 2 and arg.startswith(f))
               for f in PYTEST_FORBIDDEN)


# ---------------------------------------------------------------- PreToolUse

def check_bash(role: str, policy: dict, command: str) -> None:
    if role == "orchestrator":
        if SHELL_REDIRECT.search(command) or (SHELL_WRITE.search(command) and SHELL_PROTECTED.search(command)):
            deny(f"Shell writes to src/, tests/ or the guard's own files are blocked for the orchestrator. "
                 f"{policy['why']}")
        return
    if SHELL_META.search(command):
        deny(f"[{role}] only single commands are allowed: no ;, &&, |, redirection or substitution.")
    try:
        argv = shlex.split(command)
    except ValueError:
        deny(f"[{role}] could not parse the command.")
    prefix = next((p for p in policy["bash"] if argv[: len(p)] == p), None)
    if prefix is None:
        allowed = ", ".join("`" + " ".join(p) + "`" for p in policy["bash"])
        deny(f"[{role}] command not allowed. Allowed: {allowed}. {policy['why']}")
    if "pytest" in argv and any(forbidden_pytest_flag(a) for a in argv):
        deny(f"[{role}] pytest options that change plugins or configuration are not allowed.")
    for arg in argv[len(prefix):]:
        if not arg.startswith("-") and ("/" in arg or (ROOT / arg).exists()):
            target = rel(arg.split("::")[0])
            if target is None or not matches(target, policy["read"]):
                deny(f"[{role}] may not access {arg}. {policy['why']}")


def check_read(role: str, policy: dict, tool: str, tool_input: dict) -> None:
    readable = policy["read"]
    if readable == ["**"]:
        return
    if tool in {"Read", "NotebookRead"}:
        raw = tool_input.get("file_path") or tool_input.get("notebook_path")
        target = rel(raw)
        if target is None or not matches(target, readable):
            deny(f"[{role}] may not read {raw}. {policy['why']}")
        return
    # Grep / Glob: the search root must be explicit and inside a readable directory.
    base = rel(tool_input.get("path")) if tool_input.get("path") else None
    pattern = (tool_input.get("pattern") if tool == "Glob" else tool_input.get("glob")) or ""
    if not base or not matches(base + "/x", readable) or ".." in pattern or pattern.startswith("/"):
        dirs = sorted({p.split("/")[0] for p in readable if "/" in p})
        deny(f"[{role}] {tool} needs an explicit `path` inside {', '.join(dirs)}. {policy['why']}")


def check_write(role: str, policy: dict, tool_input: dict, agent_id: str | None) -> None:
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    target = rel(raw)
    if role == "orchestrator":
        if target is not None and matches(target, policy["write_deny"]):
            deny(f"The orchestrator may not write {target}. {policy['why']}")
        return
    if target is None or not matches(target, policy["write"]):
        deny(f"[{role}] may not write {raw}. Writable: {', '.join(policy['write'])}. {policy['why']}")
    if role == "implementer" and agent_id and not target.startswith(CONFLICTS_DIR + "/"):
        snap = load_snapshot(agent_id)
        if snap is not None and conflict_files() - set(snap.get("conflicts", [])):
            deny("[implementer] you filed a spec conflict report in this run. Stop now and return the "
                 "SPEC-CONFLICT summary; do not keep changing code.")


@contextmanager
def agent_slots():
    """Locked read-modify-write of the subagent registry: {"pending": [...], "running": {...}}."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / "agents.lock", "a+") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(AGENT_SLOTS.read_text()) if AGENT_SLOTS.exists() else {}
        now = time.time()
        data["pending"] = [p for p in data.get("pending", []) if now - p["t"] < PENDING_TTL]
        data["running"] = {k: t for k, t in data.get("running", {}).items() if now - t < RUNNING_TTL}
        yield data
        AGENT_SLOTS.write_text(json.dumps(data))


def reserve_agent_slot(data: dict) -> None:
    """A spawn reserves a slot at PreToolUse, so parallel spawns in one turn are counted too."""
    with agent_slots() as slots:
        in_use = len(slots["pending"]) + len(slots["running"])
        if in_use >= MAX_CONCURRENT_AGENTS:
            denied = True
        else:
            denied = False
            slots["pending"].append({"id": data.get("tool_use_id") or str(time.time()), "t": time.time()})
    if denied:
        deny(f"At most {MAX_CONCURRENT_AGENTS} subagents may run at once and {in_use} already do. "
             "Wait for one to finish, then delegate again.")


def pre_tool_use(data: dict) -> None:
    role = role_of(data)
    policy = POLICIES[role]
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    if tool in AGENT_TOOLS:
        reserve_agent_slot(data)
    elif tool in WRITE_TOOLS:
        check_write(role, policy, tool_input, data.get("agent_id"))
    elif tool in READ_TOOLS and role != "orchestrator":
        check_read(role, policy, tool, tool_input)
    elif tool == "Bash":
        check_bash(role, policy, tool_input.get("command", ""))


# ---------------------------------------------------------------- Subagent snapshots

def conflict_files() -> set[str]:
    d = ROOT / CONFLICTS_DIR
    return {p.relative_to(ROOT).as_posix() for p in d.glob("*.md")} if d.exists() else set()


def protected_files(writable: list[str]) -> dict[str, Path]:
    files = {}
    for root in PROTECTED_ROOTS:
        base = ROOT / root
        candidates = [base] if base.is_file() else (base.rglob("*") if base.is_dir() else [])
        for p in candidates:
            if p.is_file() and not SKIP_PARTS.intersection(p.parts):
                r = p.relative_to(ROOT).as_posix()
                if not matches(r, writable):
                    files[r] = p
    return files


def snapshot_path(agent_id: str) -> Path:
    return STATE_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", agent_id) + ".json")


def load_snapshot(agent_id: str) -> dict | None:
    p = snapshot_path(agent_id)
    return json.loads(p.read_text()) if p.exists() else None


def subagent_start(data: dict) -> None:
    role = role_of(data)
    if not data.get("agent_id"):
        return
    with agent_slots() as slots:
        if slots["pending"]:
            slots["pending"].pop(0)
        slots["running"][data["agent_id"]] = time.time()
    if role == "orchestrator":
        return
    files = protected_files(POLICIES[role]["write"])
    snap = {
        "role": role,
        "files": {r: base64.b64encode(p.read_bytes()).decode() for r, p in files.items()},
        "conflicts": sorted(conflict_files()),
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path(data["agent_id"]).write_text(json.dumps(snap))


def release_agent_slot(agent_id: str) -> None:
    with agent_slots() as slots:
        slots["running"].pop(agent_id, None)


def subagent_stop(data: dict) -> None:
    role = role_of(data)
    agent_id = data.get("agent_id")
    if not agent_id:
        return
    snap = load_snapshot(agent_id) if role != "orchestrator" else None
    if snap is None:
        release_agent_slot(agent_id)
        return
    before = snap["files"]
    restored = []
    for r, b64 in before.items():
        content = base64.b64decode(b64)
        p = ROOT / r
        if not p.is_file() or p.read_bytes() != content:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
            restored.append(r)
    for r, p in protected_files(POLICIES[role]["write"]).items():
        if r not in before:
            p.unlink()
            restored.append(r)
    if restored and not data.get("stop_hook_active"):
        msg = f"changed protected files, reverted: {', '.join(sorted(restored))}"
        log_violation(role, msg)
        print(json.dumps({"decision": "block", "reason":
              f"[{role}] {msg}. {POLICIES[role]['why']} Finish using only the files you are allowed to change."}))
        return  # the agent continues, so it keeps its slot
    snapshot_path(agent_id).unlink(missing_ok=True)
    release_agent_slot(agent_id)


def main() -> None:
    data = json.load(sys.stdin)
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        pre_tool_use(data)
    elif event == "SubagentStart":
        subagent_start(data)
    elif event == "SubagentStop":
        subagent_stop(data)


if __name__ == "__main__":
    main()
