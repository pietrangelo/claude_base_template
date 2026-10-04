# Claude Code base template: spec-first TDD + DDD + adversary

A starting structure for Claude Code projects where the separation between spec,
tests and code is enforced mechanically instead of by instructions in `CLAUDE.md`.

## What enforces what

| Requirement | Mechanism |
|---|---|
| Roles with restricted tools | `.claude/agents/{test-author,implementer,adversary}.md` plus per-role allowlists in `.claude/hooks/guard.py` |
| Test-author sees the spec only | guard blocks its reads of `src/`; it writes only `tests/spec/` |
| Implementer cannot touch tests | guard blocks writes outside `src/` and `.tdd/conflicts/`; its shell is an allowlist with no redirection or chaining |
| Adversary in a fresh context, separate directory | subagent context; guard blocks `.tdd/` and git history; it writes only `tests/adversary/` |
| Hard block even through the shell | `SubagentStart` snapshots protected files, `SubagentStop` reverts any change and logs it to `.tdd/violations.log` |
| Spec is the source of truth | clause IDs in `specs/`; `@pytest.mark.spec("ID")` required by `tools/tdd/pytest_plugin.py`; `tools/spec_trace.py` flags orphan tests and uncovered clauses |
| Spec commit before test change | CI runs `tools/check_spec_changes.py` over the PR's commits |
| Tests constrain the code | `tools/mutation_gate.py` (mutmut) fails on surviving mutants |
| Escape hatch | implementer writes `.tdd/conflicts/<ID>.md` and stops; the guard blocks further code writes; CI fails while a report is open |
| At most 3 agents at once | guard reserves a slot when the `Agent` tool is called (so parallel spawns count), holds it from `SubagentStart` to `SubagentStop`, and denies a 4th; set `MAX_CONCURRENT_AGENTS` in `guard.py` |
| Effort per role | `effort:` in agent and skill frontmatter (implementer `medium`, test-author and adversary `high`, `write-spec` `xhigh`), `effortLevel: medium` for the main session; table in `CLAUDE.md` |
| Enforcement can't be edited by an agent | `.claude/settings.json` deny rules on `.claude/`, `tools/`, `.github/`, `conftest.py`, `pyproject.toml` |

## Layout

```
CLAUDE.md                     workflow and role summary (advisory)
specs/                        source of truth, one folder per bounded context
src/<app>/<context>/          domain code, one package per bounded context
tests/spec/                   written only by test-author, derived from specs
tests/adversary/              written only by adversary
.claude/agents/               the three role agents
.claude/hooks/guard.py        role guard (PreToolUse, SubagentStart, SubagentStop)
.claude/skills/tdd-cycle/     /tdd-cycle: orchestrates one spec-to-green cycle
.claude/skills/write-spec/    /write-spec: writes or changes spec clauses (xhigh effort)
.claude/settings.json         hook registration and deny rules
.tdd/conflicts/               implementer's SPEC-CONFLICT reports
tools/                        spec trace, CI backstop, mutation gate, pytest plugin,
                              new_project.py bootstrap, and their tests
.github/workflows/ci.yml      CI backstop
```

## Starting a new project

One-time setup of this repository: on GitHub, Settings → General → tick
**Template repository**.

For each new project:

1. On GitHub, **Use this template** → **Create a new repository**, then clone it.
2. `pip install pytest "mutmut>=3.3"` (Python 3.11+).
3. Remove the worked example and name your app and first bounded context:
   ```
   python3 tools/new_project.py --package billing_app --context invoicing --prefix INV
   ```
   The script runs only once: it refuses when the example is already gone.
4. Commit, then in Claude Code describe the first behaviour, or write clauses in
   `specs/invoicing/invoicing.md` and run `/tdd-cycle INV-001`.

## The worked example (replaceable)

`specs/cart`, `src/shop/cart`, `tests/spec/cart` and `tests/adversary/cart` are a
small shopping-cart context that shows one full cycle: spec clauses, derived tests,
code, adversary tests, and a 100% mutation score. It exists to be deleted by
`tools/new_project.py`; nothing else in the template depends on it.

The reference toolchain is Python (pytest, mutmut). The agents, guard, spec format,
spec trace and CI backstop are language-agnostic: for another stack, change the
allowed test commands in `POLICIES` in `guard.py`, the marker convention in
`specs/README.md` and the mutation tool in `tools/mutation_gate.py`.

## Known limits
- The main session's shell check is a heuristic. Subagents are fully covered by the
  snapshot-and-revert on stop; the main session's backstop is CI.
- The guard relies on Claude Code passing `agent_type` to hooks, which it does for
  subagents. Any other subagent type is treated like the main session.
- Changing the guard, tools or CI means editing them outside Claude Code (or removing
  the deny rules on purpose). Consider a CODEOWNERS entry for those paths.
