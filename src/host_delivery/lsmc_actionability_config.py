"""Read-only host policy access; no broker, strategy or delivery imports."""
import math
from pathlib import Path

import yaml

KEY = "lsmc_min_remaining_reward_fraction"
HOST_POLICY = Path("config/local/actionability_policy.yaml")


def remaining_fraction(root):
    """Require the owner-set value in the host policy; never borrow a tracked value."""
    try:
        raw = yaml.safe_load((Path(root) / HOST_POLICY).read_text(encoding="utf-8"))
        value = raw[KEY]
        if (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and 0 < value <= 1):
            return value
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError):
        pass
    return None
