"""Deterministic Binance newClientOrderId generator (spec item 8). Never sent anywhere in
this phase -- there is no reachable submit path (see execution/adapter.py::
CryptoExecutionAdapter, execution/crypto_filter_refresh.py::submit_step). Pure function of
command identity; contains no credential material and never reads one.

Charset: Binance's own Futures "New Order" API documents newClientOrderId as matching
`^[\\.A-Z\\:/a-zA-Z0-9_-]{1,36}$` (alnum plus `.`, `:`, `/`, `_`, `-`), max length 36 --
recalled from this project's prior discovery of Binance's API conventions. This generator
uses only the conservative subset [A-Za-z0-9_-] (skips `.`, `:`, `/` -- no behavioral need
for them) and stays comfortably under the 36-char cap rather than exactly at it, so a
future minor format change (e.g. a slightly longer prefix) has headroom without ever
risking the documented limit.
"""
from __future__ import annotations

import hashlib
import re

# "AGX-" identifies this repo's own generated ids at a glance in exchange UIs/logs.
_PREFIX = "AGX-"
_DIGEST_LEN = 24  # hex chars taken from the sha256 digest
MAX_CLIENT_ORDER_ID_LEN = 36  # Binance's documented ceiling
_GENERATED_LEN = len(_PREFIX) + _DIGEST_LEN  # 28 -- well under the 36-char cap

_VALID_CHARS = re.compile(r"^[A-Za-z0-9_-]+$")


def generate_client_order_id(command_id: str, occurrence_id: str) -> str:
    """Stable for a given (command_id, occurrence_id) pair -- calling this twice with the
    same identity returns the same id (useful for idempotent retries of the SAME command),
    while different identities collide only with sha256-digest-collision probability."""
    if not command_id or not occurrence_id:
        raise ValueError("command_id and occurrence_id must both be non-empty")
    basis = f"{command_id}|{occurrence_id}".encode("utf-8")
    digest = hashlib.sha256(basis).hexdigest()[:_DIGEST_LEN]
    client_order_id = f"{_PREFIX}{digest}"
    assert len(client_order_id) == _GENERATED_LEN <= MAX_CLIENT_ORDER_ID_LEN
    assert _VALID_CHARS.match(client_order_id), f"generated id has an invalid character: {client_order_id!r}"
    return client_order_id
