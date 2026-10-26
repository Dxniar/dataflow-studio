"""Saved batch history validates checkpoint shape before display or retry."""

import pytest


@pytest.mark.parametrize("errors", [1, ["untrusted-entry"]])
def test_history_rejects_malformed_batch_errors_without_crashing(errors):
    from dataflow.gui.workspace import batch_checkpoint

    job = {
        "checkpoint": {
            "successes": [],
            "errors": errors,
            "pending": [],
            "cancelled": False,
        }
    }
    assert batch_checkpoint(job) is None


@pytest.mark.parametrize("checkpoint", [{}, [], 0])
def test_present_invalid_checkpoint_does_not_fall_back_to_fresh_pending(checkpoint):
    from dataflow.gui.workspace import batch_checkpoint

    assert batch_checkpoint({"checkpoint": checkpoint, "payload": {"paths": ["a.csv"]}}) is None


def test_history_preserves_valid_batch_checkpoint_for_rendering():
    from dataflow.gui.workspace import batch_checkpoint

    checkpoint = {
        "successes": [{"input": "done.csv", "output": "done_processed.csv", "summary": {}}],
        "errors": [{"input": "failed.csv", "error": "Input file is unavailable."}],
        "pending": ["pending.csv"],
        "cancelled": True,
    }
    assert batch_checkpoint({"checkpoint": checkpoint}) == checkpoint
