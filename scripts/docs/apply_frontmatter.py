"""Add DOCS-LIVE-2 front-matter to every in-scope Markdown file that lacks it (idempotent).

    python scripts/docs/apply_frontmatter.py [--check]

Only prepends a front-matter block; the existing content is left byte-for-byte unchanged
(dated docs/status evidence included). Excluded files (doc_classes.EXCLUDED) are skipped.
--check exits 1 when an in-scope file has no front-matter.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from doc_classes import classify, default_frontmatter, is_excluded  # noqa: E402
from frontmatter import add, split  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def in_scope(root: str = ROOT):
    out = subprocess.run(["git", "ls-files", "-z", "*.md"], cwd=root, capture_output=True, check=True).stdout
    for p in sorted(x for x in out.decode().split("\0") if x):
        if ("/" not in p or p.startswith("docs/")) and not is_excluded(p):
            yield p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    added, missing = 0, []
    for rel in in_scope():
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        if split(text)[0] is not None:
            continue
        cls = classify(rel)
        if cls is None:
            missing.append(rel)
            continue
        if args.check:
            missing.append(rel)
            continue
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(add(text, default_frontmatter(cls)))
        added += 1
    print(f"front-matter added={added} missing={len(missing)}")
    for rel in missing:
        print(f"  MISSING {rel}")
    return 1 if (args.check and missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
