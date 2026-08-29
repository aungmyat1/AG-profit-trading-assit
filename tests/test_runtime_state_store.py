"""DUAL_DAYTRADING_RUNTIME_V1 spec section 40 (state store tests): atomic put/get,
restart = new store instance sees prior data, corrupt file fails closed rather than
silently resetting.
"""
from __future__ import annotations

import os

import pytest

from runtime_state.store import JsonKeyValueStore, StateStoreCorrupted


def test_put_and_get_round_trip(tmp_path):
    path = os.path.join(str(tmp_path), "state.json")
    store = JsonKeyValueStore(path)
    store.put("key1", {"a": 1})
    assert store.get("key1") == {"a": 1}


def test_missing_key_returns_none(tmp_path):
    store = JsonKeyValueStore(os.path.join(str(tmp_path), "state.json"))
    assert store.get("nope") is None


def test_new_store_instance_sees_prior_data_restart_simulation(tmp_path):
    path = os.path.join(str(tmp_path), "state.json")
    JsonKeyValueStore(path).put("key1", {"a": 1})
    reopened = JsonKeyValueStore(path)  # simulates a fresh process after restart
    assert reopened.get("key1") == {"a": 1}


def test_put_does_not_clobber_other_keys(tmp_path):
    path = os.path.join(str(tmp_path), "state.json")
    store = JsonKeyValueStore(path)
    store.put("key1", {"a": 1})
    store.put("key2", {"b": 2})
    assert store.all() == {"key1": {"a": 1}, "key2": {"b": 2}}


def test_remove_deletes_key(tmp_path):
    path = os.path.join(str(tmp_path), "state.json")
    store = JsonKeyValueStore(path)
    store.put("key1", {"a": 1})
    store.remove("key1")
    assert store.get("key1") is None


def test_corrupt_file_fails_closed_not_silently_reset(tmp_path):
    path = os.path.join(str(tmp_path), "state.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    store = JsonKeyValueStore(path)
    with pytest.raises(StateStoreCorrupted):
        store.load()


def test_non_object_json_fails_closed(tmp_path):
    path = os.path.join(str(tmp_path), "state.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("[1, 2, 3]")
    store = JsonKeyValueStore(path)
    with pytest.raises(StateStoreCorrupted):
        store.load()
