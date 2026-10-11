#!/usr/bin/env python
"""Full pipeline through order_check, stopping before order_send:

MT5 -> strategy -> risk -> execution validation -> order_check -> STOP.

NOT YET IMPLEMENTED -- depends on execution/ and mt5/ (see PROJECT_STATUS.md
'Implementation sequence', and the DRY_RUN mode definition in config/trading.yaml)."""
from __future__ import annotations

import sys


def main() -> None:
    raise NotImplementedError(
        "scripts/dry_run.py is not implemented yet. "
        "See PROJECT_STATUS.md 'Implementation sequence' steps 4-8."
    )


if __name__ == "__main__":
    sys.exit(main())
