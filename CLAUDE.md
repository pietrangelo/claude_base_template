# Working in this repository

This project is built spec-first with TDD, DDD and an adversarial tester. The rules
below are enforced mechanically (see "Enforcement"); this file only explains them.

## The cycle

Use the `/tdd-cycle <CLAUSE-ID ...>` skill for every new or changed behaviour.

1. **Spec**: write or change clauses in `specs/<context>/*.md` (format: `specs/README.md`).
   The user approves the diff; it is committed on its own.
2. **Tests**: the `test-author` agent derives tests from the clauses, without seeing `src/`.
3. **Code**: the `implementer` agent makes them pass, touching `src/` only.
4. **Attack**: the `adversary` agent, in a fresh context, writes breaking tests in
   `tests/adversary/` and kills surviving mutants.
5. **Gates**: tests, spec trace, mutation gate, spec-first check.

## Roles

| Role | Reads | Writes | Shell |
|---|---|---|---|
| main session (orchestrator) | everything | `specs/`, docs | anything except writing `src/`, `tests/` or the guard |
| `test-author` | `specs/`, `tests/` | `tests/spec/` | `pytest --collect-only`, spec trace |
| `implementer` | everything | `src/`, `.tdd/conflicts/` | pytest, spec trace, read-only git |
| `adversary` | `specs/`, `src/`, `tests/` | `tests/adversary/` | pytest, mutmut, mutation gate |

## Effort levels

| Work | Effort | Set by |
|---|---|---|
| Writing specs and project rules | `xhigh` | `write-spec` skill frontmatter |
| Orchestrating a cycle | `high` | `tdd-cycle` skill frontmatter |
| `test-author`: tests are the safety net, missed edge cases are costly | `high` | agent frontmatter |
| `adversary`: finding subtle breaks is where deeper reasoning pays off | `high` | agent frontmatter |
| `implementer`: tight, verifiable constraints, so extra thinking adds little | `medium` | agent frontmatter |
| Routine edits, small features, refactors with good test coverage | `medium` | `effortLevel` in `.claude/settings.json` |
| Large multi-stage runs | consider the `ultracode` keyword | the user, per request |

Do not raise the implementer above `medium` to get past a failing test: a test it
cannot satisfy is a SPEC-CONFLICT, not a reasoning problem.

## Rules
- The spec is the source of truth. Every test names its clause ID in a
  `@pytest.mark.spec("CTX-NNN")` marker and in its name.
- A test is never edited to fit the code. To change a test, change the spec clause in
  its own commit, then regenerate the tests from it.
- If the implementer thinks a test is wrong it writes `.tdd/conflicts/<CLAUSE-ID>.md`,
  replies `SPEC-CONFLICT <CLAUSE-ID>` and stops. The orchestrator stops too and asks the user.
- The adversary is briefed with clause IDs and source paths only, never with the
  implementer's output or reasoning.
- Domain code lives in `src/<app>/<context>/`, one package per bounded context, named
  in the spec's ubiquitous language. Infrastructure stays out of the domain package.

## Enforcement
- `.claude/hooks/guard.py` (PreToolUse, SubagentStart, SubagentStop): per-role read,
  write and shell allowlists; snapshots protected files when a subagent starts and
  reverts anything it changed outside its area when it stops; denies spawning a
  subagent while 3 are already running (`MAX_CONCURRENT_AGENTS`).
- `.claude/settings.json` deny rules: nobody edits `.claude/`, `tools/`, `.github/`,
  `conftest.py` or `pyproject.toml` from inside Claude Code. Change those by hand.
- `tools/tdd/pytest_plugin.py`: collection fails for an untagged or orphan test.
- CI (`.github/workflows/ci.yml`): spec trace, spec-first check
  (`tools/check_spec_changes.py`), tests, guard self-tests, mutation gate.

## Commands
```
python3 -m pytest -q                    # spec + adversary tests
python3 tools/spec_trace.py --report    # clause -> tests matrix
python3 tools/mutation_gate.py          # mutation testing gate (mutmut)
python3 tools/check_spec_changes.py --base origin/main
python3 -m pytest -q tools/tests        # tests for the guard and CI tooling
```
