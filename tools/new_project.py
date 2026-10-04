#!/usr/bin/env python3
"""Turn a fresh copy of this template into your project. Run once, right after cloning.

Removes the worked example (the `cart` context of the `shop` app), renames the
application package, and optionally creates an empty first bounded context:

    python3 tools/new_project.py --package billing_app
    python3 tools/new_project.py --package billing_app --context invoicing --prefix INV

It refuses to run once the example is gone, so it cannot be used later to wipe
tests or code.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

EXAMPLE_APP = "shop"
EXAMPLE_CONTEXT = "cart"
EXAMPLE_PATHS = [
    f"specs/{EXAMPLE_CONTEXT}",
    f"src/{EXAMPLE_APP}",
    f"tests/spec/{EXAMPLE_CONTEXT}",
    f"tests/adversary/{EXAMPLE_CONTEXT}",
]
IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
PREFIX = re.compile(r"^[A-Z][A-Z0-9]*$")

SPEC_SKELETON = """# {title}

Bounded context: `{context}`
Clause prefix: `{prefix}`

## Ubiquitous language

- **Term**: what it means in this context.

## Invariants

## Behaviours
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", required=True, help="application package name, e.g. billing_app")
    parser.add_argument("--context", help="first bounded context, e.g. invoicing")
    parser.add_argument("--prefix", help="clause ID prefix for that context, e.g. INV")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root)

    if not (root / "specs" / EXAMPLE_CONTEXT).is_dir() or not (root / "src" / EXAMPLE_APP).is_dir():
        print("The template example is already gone: this project was bootstrapped before. Nothing to do.",
              file=sys.stderr)
        return 1
    if not IDENT.match(args.package):
        parser.error("--package must be a lower-case Python identifier")
    if args.context and not IDENT.match(args.context):
        parser.error("--context must be a lower-case Python identifier")
    if bool(args.context) != bool(args.prefix):
        parser.error("--context and --prefix go together")
    if args.prefix and not PREFIX.match(args.prefix):
        parser.error("--prefix must be upper-case letters and digits, e.g. INV")

    for rel in EXAMPLE_PATHS:
        shutil.rmtree(root / rel, ignore_errors=True)
        print(f"removed  {rel}/")

    pkg = root / "src" / args.package
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(f'"""{args.package}: one subpackage per bounded context (see specs/)."""\n')
    print(f"created  src/{args.package}/")

    if args.context:
        ctx = pkg / args.context
        ctx.mkdir(exist_ok=True)
        (ctx / "__init__.py").write_text(f'"""{args.context} bounded context. Spec: specs/{args.context}/."""\n')
        spec = root / "specs" / args.context / f"{args.context}.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(SPEC_SKELETON.format(title=args.context.replace("_", " ").capitalize(),
                                             context=args.context, prefix=args.prefix))
        for d in ("tests/spec", "tests/adversary"):
            (root / d / args.context).mkdir(parents=True, exist_ok=True)
            (root / d / args.context / ".gitkeep").touch()
        print(f"created  src/{args.package}/{args.context}/, specs/{args.context}/{args.context}.md, "
              f"tests/{{spec,adversary}}/{args.context}/")

    pyproject = root / "pyproject.toml"
    text = pyproject.read_text()
    text = re.sub(r'(?m)^name = ".*"$', f'name = "{args.package.replace("_", "-")}"', text, count=1)
    text = re.sub(r'(?m)^description = ".*"$', 'description = ""', text, count=1)
    pyproject.write_text(text)
    print("updated  pyproject.toml")

    print("\nNext: commit this, then write your first clauses and run /tdd-cycle in Claude Code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
