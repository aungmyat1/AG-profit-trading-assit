"""Read-only Large-SMC host policy check. Never attaches MT5 or sends a message."""
import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from host_delivery.lsmc_actionability_config import (  # noqa: E402
    KEY,
    remaining_fraction,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    value = remaining_fraction(args.root)
    if value is None:
        print(f"LSMC_CONFIG_MISSING key={KEY}")
        return 1
    print(f"PASS {KEY}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
