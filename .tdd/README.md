# .tdd

Workflow state for the role guard.

- `conflicts/<CLAUSE-ID>.md`: SPEC-CONFLICT reports filed by the implementer. CI fails
  while any exists. Resolve each with a spec commit (or a test regeneration from the
  unchanged spec), then delete the report.
- `state/` (git-ignored): snapshots the guard takes when a subagent starts.
- `violations.log` (git-ignored): every time a subagent changed a file outside its
  area and the guard reverted it.

The adversary agent is not allowed to read this directory.
