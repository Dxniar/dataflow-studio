from pathlib import Path


def test_desktop_state_survives_restart_without_loading_table_cells(tmp_path):
    from dataflow.gui.workspace import DesktopWorkspace

    first = DesktopWorkspace(tmp_path)
    payload = {
        "settings": {"encoding": "utf-8-sig", "theme": "Graphite"},
        "workflow": {"trim_whitespace": True},
        "import_options": {"column_types": {"id": "string"}},
        "validation_rules": {"required_columns": ["id"]},
        "recent_files": [{"path": str(tmp_path / "source.csv"), "sheet": 0}],
    }
    first.save(payload)
    first.history.append({"time": "2026-10-26T12:00:00", "action": "Import", "detail": "1 file"})
    restored = DesktopWorkspace(tmp_path)
    assert restored.state == payload
    assert restored.history[-1]["action"] == "Import"
    assert restored.history[-1]["detail"] == "1 file"
    assert not restored.warning


def test_desktop_job_is_recoverable_after_restart(tmp_path):
    from dataflow.gui.workspace import DesktopWorkspace

    first = DesktopWorkspace(tmp_path)
    job = first.create_job("batch", {"paths": ["a.csv", "b.csv"]})
    first.update_job(
        job, "running", checkpoint={"successes": [{"input": "a.csv"}], "pending": ["b.csv"]}
    )
    restored = DesktopWorkspace(tmp_path)
    found = restored.get_job(job)
    assert found["status"] == "interrupted"
    assert found["checkpoint"]["pending"] == ["b.csv"]


def test_desktop_readonly_future_store_exposes_warning_and_keeps_app_usable(tmp_path):
    import sqlite3

    from dataflow.gui.workspace import DesktopWorkspace

    database = Path(tmp_path) / "workspace.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=999")
    workspace = DesktopWorkspace(tmp_path)
    workspace.save({"settings": {}})
    workspace.history.append({"time": "now", "action": "Test", "detail": "still available"})
    assert workspace.history[-1]["detail"] == "still available"
    assert workspace.warning
    assert workspace.create_job("test", {}) is None
