---
name: write-spec
description: Write or change spec clauses in specs/ (or the project's rules) for a behaviour the user describes. Use before any tests or code for new or changed behaviour.
argument-hint: <behaviour to specify> | <CLAUSE-ID to change>
effort: xhigh
---

Mistakes in the spec propagate into every test and line of code derived from it,
so this step runs at the highest routine effort. Request: `$ARGUMENTS`.

1. Find the bounded context the behaviour belongs to (`specs/<context>/`). If none fits,
   propose a new context and its clause prefix to the user before writing anything.
2. Read the context's ubiquitous-language glossary and existing clauses. Add any new
   term to the glossary first.
3. Write clauses following `specs/README.md`:
   - one observable behaviour per clause, stated in the ubiquitous language;
   - name every boundary explicitly (at, below, above) and what stays unchanged on failure;
   - new behaviour gets the next free ID; a changed behaviour keeps its ID; a removed
     behaviour is deleted and its ID is never reused.
4. Look for contradictions with other clauses in the same context and list any gap
   you could not close as an open question.
5. Show the user the diff and the open questions. Commit only after they approve:
   `spec(<IDS>): <summary>`, with nothing but `specs/` in the commit.
