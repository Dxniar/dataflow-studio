"""Durable metadata survives restarts without retaining table contents."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from dataflow.services.workspace import WorkspaceStore


def test_workspace_restart_roundtrip_and_default_locations(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFLOW_WORKSPACE_DIR", str(tmp_path))
    store = WorkspaceStore()
    payload = {
        "settings": {"theme": "dark"},
        "workflow": {"trim_whitespace": True},
        "import_options": {"column_types": {"id": "string"}},
        "quality_rules": {"required_columns": ["id"]},
        "recent_paths": ["input.csv"],
    }
    assert store.path == tmp_path / "workspace.sqlite3"
    assert store.load_workspace() == {}
    store.save_workspace(payload)
    assert WorkspaceStore(tmp_path).load_workspace() == payload
    monkeypatch.delenv("DATAFLOW_WORKSPACE_DIR")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    assert WorkspaceStore().path == tmp_path / "appdata" / "DataFlowStudio" / "workspace.sqlite3"


def test_history_order_limit_and_worker_callbacks(tmp_path):
    store = WorkspaceStore(tmp_path)
    store.append_history("import", "first", timestamp="2026-10-26T10:00:00Z")
    store.append_history("export", "second", timestamp="2026-10-26T10:01:00Z")
    assert store.history(limit=1) == [
        {"time": "2026-10-26T10:01:00Z", "action": "export", "detail": "second"}
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: store.append_history("step", str(i)), range(12)))
    assert len(WorkspaceStore(tmp_path).history()) == 14


def test_job_checkpoint_and_startup_interruption(tmp_path):
    store = WorkspaceStore(tmp_path)
    job = store.create_job("batch", {"inputs": ["one.csv", "two.csv"], "config": {}})
    store.update_job(job, "running", checkpoint={"pending": ["two.csv"], "successes": []})
    done = store.create_job("validation", {})
    store.update_job(done, "completed")
    cancelled = store.create_job("batch", {})
    store.update_job(cancelled, "cancel_requested")
    reopened = WorkspaceStore(tmp_path)
    result = reopened.get_job(job)
    assert result["status"] == "interrupted"
    assert result["checkpoint"] == {"pending": ["two.csv"], "successes": []}
    assert result["payload"]["inputs"] == ["one.csv", "two.csv"]
    assert set(result) == {
        "id",
        "kind",
        "status",
        "payload",
        "checkpoint",
        "error",
        "created_at",
        "updated_at",
    }
    assert reopened.get_job(cancelled)["status"] == "interrupted"
    assert reopened.get_job(done)["status"] == "completed"
    assert reopened.mark_interrupted() == 0
    assert reopened.get_job("missing") is None
    assert len(reopened.list_jobs(limit=2)) == 2


def test_corrupt_database_is_backed_up_uniquely(tmp_path):
    original = b"broken sqlite file secret-value"
    (tmp_path / "workspace.sqlite3").write_bytes(original)
    store = WorkspaceStore(tmp_path)
    assert store.warning and "secret-value" not in store.warning
    assert store.load_workspace() == {}
    backups = [p for p in tmp_path.iterdir() if p != store.path]
    assert len(backups) == 1 and backups[0].read_bytes() == original
    store.path.write_bytes(original)
    WorkspaceStore(tmp_path)
    assert len([p for p in tmp_path.iterdir() if p.name != "workspace.sqlite3"]) == 2


def test_future_schema_is_preserved_and_store_is_read_only(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=999")
        conn.execute("CREATE TABLE future (value TEXT)")
        conn.execute("INSERT INTO future VALUES ('keep')")
    original = path.read_bytes()
    store = WorkspaceStore(tmp_path)
    assert store.warning and store.load_workspace() == {}
    with pytest.raises(ValueError, match="unavailable"):
        store.save_workspace({"settings": {}})
    assert path.read_bytes() == original


def test_invalid_or_oversized_metadata_rejected_without_losing_saved_state(tmp_path):
    store = WorkspaceStore(tmp_path)
    store.save_workspace({"settings": {"theme": "dark"}})
    for bad in (
        {"dataframe": {"rows": [["secret"]]}},
        {"settings": {"x": float("nan")}},
        {"settings": {"x": "x" * 1_100_000}},
        {"settings": object()},
    ):
        with pytest.raises(ValueError):
            store.save_workspace(bad)
    assert store.load_workspace() == {"settings": {"theme": "dark"}}


def test_invalid_persisted_json_falls_back_safely(tmp_path):
    store = WorkspaceStore(tmp_path)
    store.save_workspace({"settings": {}})
    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE workspace SET payload = ?", ('{"settings":',))
    assert store.load_workspace() == {}
    assert store.warning


def test_invalid_job_checkpoint_does_not_allow_silent_retry(tmp_path):
    store = WorkspaceStore(tmp_path)
    job = store.create_job("batch", {"inputs": ["source.csv"]})
    store.update_job(job, "failed", checkpoint={"pending": ["source.csv"]})
    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE jobs SET checkpoint=? WHERE id=?", ('["not-an-object"]', job))
    assert store.get_job(job) is None
    assert store.list_jobs() == []
    assert store.warning


def test_checkpoints_are_retained_during_status_update(tmp_path):
    store = WorkspaceStore(tmp_path)
    job = store.create_job("batch", {})
    store.update_job(job, "running", checkpoint={"pending": ["one.csv"]})
    store.update_job(job, "cancel_requested")
    assert store.get_job(job)["checkpoint"] == {"pending": ["one.csv"]}
    with pytest.raises(ValueError):
        store.update_job("unknown", "completed")


def test_table_matrix_and_unrecognized_workspace_data_cannot_be_stored(tmp_path):
    store = WorkspaceStore(tmp_path)
    for payload in ({"data": [["private", 7]]}, {"settings": {"rows": [[1, 2]]}}):
        with pytest.raises(ValueError):
            store.save_workspace(payload)


def test_configuration_column_names_can_match_table_metadata_terms(tmp_path):
    store = WorkspaceStore(tmp_path)
    payload = {
        "import_options": {"column_types": {"records": "string", "cells": "string"}},
        "workflow": {"rename_columns": {"raw_data": "records"}},
        "validation_rules": {"allowed_values": {"records": ["A", "B"]}},
    }
    store.save_workspace(payload)
    assert WorkspaceStore(tmp_path).load_workspace() == payload


def test_malformed_sqlite_schema_does_not_abort_startup_or_modify_original(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=1")
        conn.execute("CREATE TABLE jobs (id TEXT)")
        conn.execute("INSERT INTO jobs VALUES ('preserve')")
    original = path.read_bytes()
    store = WorkspaceStore(tmp_path)
    assert store.warning
    assert store.load_workspace() == {} and store.list_jobs() == []
    with pytest.raises(ValueError):
        store.create_job("batch", {})
    assert path.read_bytes() == original
