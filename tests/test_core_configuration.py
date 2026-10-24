"""Configuration rejects ambiguity before data or files are changed."""

import json

import pytest

from dataflow.core.configuration import PipelineConfig
from dataflow.core.errors import DataFlowError


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown_operation": True},
        {"trim_whitespace": "yes"},
        {"drop_duplicates": 1},
        {"deduplicate_by": "id"},
        {"deduplicate_by": []},
        {"fill_missing": {"id": [1]}},
        {"fill_missing": {"id": float("nan")}},
        {"standardize_values": {"city": []}},
        {"rename_columns": {"id": ""}},
        {"select_columns": ["id", "id"]},
        {"convert_types": {"id": "eval"}},
        {"filters": [{"column": "id", "operator": "eval", "value": 1}]},
        {"filters": [{"column": "id", "operator": "equals"}]},
        {"filters": [{"column": "id", "operator": "equals", "value": []}]},
        {"filters": [{"column": "id", "operator": "equals", "value": 1, "x": 2}]},
        {"sort_by": "id"},
        {"sort_ascending": "false"},
    ],
)
def test_invalid_options_fail(payload):
    with pytest.raises(DataFlowError):
        PipelineConfig.from_dict(payload)


def test_config_round_trip_and_owns_nested_values(tmp_path):
    options = {"fill_missing": {"city": "Алматы"}, "drop_duplicates": True}
    config = PipelineConfig.from_dict(options)
    options["fill_missing"]["city"] = "changed"
    copied = config.to_dict()
    copied["fill_missing"]["city"] = "also changed"
    assert config.fill_missing == {"city": "Алматы"}
    path = tmp_path / "pipeline.json"
    path.write_text(json.dumps(config.to_dict(), ensure_ascii=False), encoding="utf-8")
    assert PipelineConfig.from_json(path).to_dict() == config.to_dict()


@pytest.mark.parametrize("content", ["{", "[]", '{"drop_duplicates":true,"drop_duplicates":false}'])
def test_malformed_or_ambiguous_json_is_rejected(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DataFlowError):
        PipelineConfig.from_json(path)


def test_missing_configuration_has_friendly_error(tmp_path):
    with pytest.raises(DataFlowError):
        PipelineConfig.from_json(tmp_path / "missing.json")
