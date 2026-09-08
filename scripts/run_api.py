#!/usr/bin/env python
"""Deterministic local dev-server launcher for src/api/app.py
(AG_AI_STUDIO_PREVIEW_VSCODE_RUNTIME_INTEGRATION_V1). Binds 127.0.0.1 by default --
never 0.0.0.0 -- so the backend is reachable only from this machine unless an operator
explicitly overrides AG_API_HOST, which this script does not encourage.

Usage:
    python scripts/run_api.py [--host 127.0.0.1] [--port 8000] [--reload]

Port 8000 was chosen because web/vite.config.ts and web/server.ts (the frontend dev
server) both already use port 3000 -- see docs/setup/AI_STUDIO_VSCODE_DEVELOPMENT.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1 -- do not use 0.0.0.0 without explicit owner authorization)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Auto-reload on source change (development only)")
    args = parser.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost"):
        print(
            f"WARNING: binding to {args.host!r}, not 127.0.0.1 -- this exposes the "
            "Demo execution API beyond this machine. Only do this with explicit owner "
            "authorization (AG_AI_STUDIO_PREVIEW_VSCODE_RUNTIME_INTEGRATION_V1 section 26).",
            file=sys.stderr,
        )

    import uvicorn

    uvicorn.run("api.app:app", host=args.host, port=args.port, reload=args.reload, app_dir=str(Path(__file__).resolve().parent.parent / "src"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
