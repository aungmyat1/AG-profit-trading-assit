"""DOCS-LIVE-2 staleness report (warn-only).

    python scripts/docs/stale_check.py [--today YYYY-MM-DD] [--strict] [--json]

Lists, over docs/**/*.md and root *.md (excluding doc_classes.EXCLUDED):
  PAST_REVIEW_BY   review_by earlier than --today (default: today, UTC)
  NO_CLASS         no front-matter, or a class / state outside the allowed sets
  DUPLICATE_TOPIC  two or more files sharing the same H1 title or filename slug
Always exits 0 (warn-only) unless --strict, which exits 1 when anything is listed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_frontmatter import ROOT, in_scope  # noqa: E402
from doc_classes import CLASSES, STATES  # noqa: E402
from frontmatter import split  # noqa: E402

_H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.M)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _date(v):
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        return None


def report(today: dt.date, root: str = ROOT) -> dict:
    past, no_class, by_h1, by_slug = [], [], defaultdict(list), defaultdict(list)
    for rel in in_scope(root):
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            meta, body = split(f.read())
        if not meta or meta.get("class") not in CLASSES or meta.get("state") not in STATES:
            no_class.append(rel)
        elif meta.get("review_by") is not None:
            due = _date(meta["review_by"])
            if due is None or due < today:
                past.append({"path": rel, "review_by": str(meta["review_by"])})
        m = _H1.search(body)
        if m:
            by_h1[_norm(m.group(1))].append(rel)
        stem = os.path.splitext(os.path.basename(rel))[0]
        if stem.upper() != "README":
            by_slug[_norm(stem)].append(rel)
    dups = [{"key": f"h1:{k}", "paths": v} for k, v in sorted(by_h1.items()) if len(v) > 1]
    dups += [{"key": f"slug:{k}", "paths": v} for k, v in sorted(by_slug.items()) if len(v) > 1]
    return {"today": today.isoformat(), "past_review_by": past, "no_class": no_class, "duplicate_topics": dups}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    r = report(today)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        for x in r["past_review_by"]:
            print(f"PAST_REVIEW_BY {x['path']} (review_by {x['review_by']})")
        for p in r["no_class"]:
            print(f"NO_CLASS {p}")
        for d in r["duplicate_topics"]:
            print(f"DUPLICATE_TOPIC {d['key']}: {', '.join(d['paths'])}")
        print(f"STALE_CHECK past_review_by={len(r['past_review_by'])} no_class={len(r['no_class'])} "
              f"duplicate_topics={len(r['duplicate_topics'])} (warn-only)")
    found = r["past_review_by"] or r["no_class"] or r["duplicate_topics"]
    return 1 if (args.strict and found) else 0
if __name__ == "__main__":
    raise SystemExit(main())
