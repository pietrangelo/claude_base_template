# Specs: the source of truth

Every behaviour of the system is described here first. Tests are derived from
these files and code is written to pass those tests. Never the other way round.

## Layout

```
specs/
  <bounded-context>/        one folder per DDD bounded context
    <aggregate-or-feature>.md
  _template.md              copy this to start a new spec (files starting with _ are ignored)
```

## Clause format

A clause is a level-3 heading that starts with a clause ID, followed by its text.
The text runs until the next heading.

```markdown
### CART-003 Quantity must be positive
Adding a line with a quantity lower than 1 raises `InvalidQuantity`
and leaves the cart unchanged.
```

Rules (checked by `tools/spec_trace.py`):

- An ID is `PREFIX-NNN`: an upper-case prefix naming the context (`CART`, `BILLING`)
  and a three-digit number. IDs are unique across all specs.
- IDs are never reused. To drop a behaviour, delete the clause; every test that
  still references it becomes an orphan and the trace check fails until the tests
  are regenerated.
- One clause, one observable behaviour. If a clause needs "and" to describe two
  outcomes, split it.
- Write clauses in the ubiquitous language of the context (see the glossary at the
  top of each spec), never in terms of the implementation.

## Referencing clauses from tests

Every test under `tests/spec/` and `tests/adversary/` must name the clause(s) it
verifies. In Python use the marker, and put the ID in the test name too:

```python
@pytest.mark.spec("CART-003")
def test_cart_003_zero_quantity_is_rejected(): ...
```

For other languages, put the ID in the test name or a tag/comment
(`// spec: CART-003`); `tools/spec_trace.py` scans test files for IDs textually.

## Changing behaviour

1. Commit the spec change on its own (`spec: CART-003 allow quantity 0 to remove a line`).
2. Regenerate the affected tests with the `test-author` agent and commit them.
3. Let the `implementer` agent make them pass.

CI (`tools/check_spec_changes.py`) fails a PR that changes tests whose clauses
were not changed in an earlier spec commit of the same PR.
