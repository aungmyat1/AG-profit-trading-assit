"""Persistent runtime state (DUAL_DAYTRADING_RUNTIME_V1 spec sections 3-6). One keyed
JSON file per entity type, following trade_management/claims.py's exact convention
(JSON dict keyed by id, atomic write via temp-file + os.replace) rather than
introducing a new database dependency -- no SQLite/Redis/Kafka exists anywhere in this
repo, and the spec's own preference order puts "reuse existing repo storage" first.
"""
from .store import JsonKeyValueStore, StateStoreCorrupted

__all__ = ["JsonKeyValueStore", "StateStoreCorrupted"]
