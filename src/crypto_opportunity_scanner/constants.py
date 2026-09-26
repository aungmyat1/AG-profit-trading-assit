"""Stable identity and storage constants for the bounded BTC observer."""

SYMBOL = "BTCUSDT"
VENUE = "BYBIT_LINEAR_PERP"
TIMEFRAME = "M5"
LOOKBACK_CANDLES = 720  # 60 hours; bounded margin for a complete prior UTC day.

STRATEGY_ID = "CRYPTO_PREVIOUS_DAY_SWEEP_OBSERVATION_V1"
STRATEGY_VERSION = "1.0.0"
STRATEGY_CLASSIFICATION = "RESEARCH / OBSERVATION"

DEFAULT_STORE_PATH = "state/crypto_opportunity_candidates_v1.json"\n