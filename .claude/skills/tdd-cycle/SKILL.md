---
name: tdd-cycle
description: Run the spec-first TDD + DDD + adversary cycle for one or more spec clause IDs (spec commit, test-author, implementer, adversary, mutation gate). Use for any new or changed behaviour.
argument-hint: <CLAUSE-ID ...> | <specs/context/file.md>
effort: high
---

You are the orchestrator. You never write tests or production code yourself (the
guard blocks it); you write specs, brief the role agents, check their results and
commit between phases. Arguments: `$ARGUMENTS`.

At most 3 subagents may run at once (the guard denies a 4th). The cycle runs the
role agents one after another; only parallelise across independent clauses, and
never more than 3 at a time.

## 0. Preconditions
- `git status` is clean and `.tdd/conflicts/` holds no `*.md` report. If one exists,
  stop and show it to the user: it must be resolved by a spec commit first.
- Resolve the arguments to a list of clause IDs. A spec file means every clause in it.

## 1. Spec (source of truth)
- If the behaviour is new or changes, use the `write-spec` skill (it runs at `xhigh`
  effort) to edit the spec in `specs/<context>/` following `specs/README.md`.
- Show the user the spec diff and wait for their approval. Do not continue on your own.
- Commit the spec alone: `spec(<IDS>): <summary>`. The CI backstop rejects test
  changes that are not preceded by a spec commit for their clauses.

## 2. Tests from the spec (test-author)
- Delegate to the `test-author` agent. The brief contains only: the clause IDs, the spec
  file path, and "write or regenerate tests for these clauses". Nothing about code.
- Run `python3 -m pytest -q tests/spec`. New behaviour must be red. A new test that is
  already green means either the behaviour exists or the test is weak: tell the user.
- Run `python3 tools/spec_trace.py`. Commit: `test(<IDS>): derive tests from spec`.
- Relay any `SPEC-GAPS` to the user before going on.

## 3. Implementation (implementer)
- Delegate to the `implementer` agent with the clause IDs and the failing test command.
- If its reply starts with `SPEC-CONFLICT` or a file appeared in `.tdd/conflicts/`:
  STOP. Show the report to the user. The fix is a spec change (back to step 1) or a
  test regeneration from the unchanged spec (back to step 2), never a test edit.
- Otherwise run `python3 -m pytest -q` and commit: `feat(<IDS>): <summary>`.

## 4. Attack (adversary)
- Delegate to the `adversary` agent in a fresh context. The brief contains only: the
  clause IDs, the spec file path and the `src/` paths to attack. Never pass on the
  implementer's reply, your own reasoning about the code, or commit messages.
- Commit its tests: `test(adversary,<IDS>): <summary>`.
- If it reports `FAILING` tests, go back to step 3 with those test names. After three
  rounds without convergence, stop and ask the user.

## 5. Gates
Run and require all to pass before reporting done:
```
python3 -m pytest -q
python3 tools/spec_trace.py
python3 tools/mutation_gate.py
python3 tools/check_spec_changes.py --base origin/main
```
A surviving mutant goes back to step 4 (adversary), or to step 1 if it shows a
behaviour the spec never defined.

## 6. Report
Clause IDs done, commits made, mutation score, and every `SPEC-GAP` the agents
raised, so the user can decide on follow-up spec changes. If `.tdd/violations.log`
has new lines, include them: an agent tried to cross its boundary.
