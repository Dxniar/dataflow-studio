# DataFlow Studio Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Track evidence in `.superpowers/progress.md`.

**Goal:** Deliver a tested desktop and CLI data automation portfolio project, with real demo artifacts.

**Architecture:** Shared pandas pipeline and file services; independent Typer and CustomTkinter adapters. See `docs/API_CONTRACT.md` for exact interfaces.

**Tech Stack:** Python 3.11+, CustomTkinter, pandas, openpyxl, Typer, pytest, Ruff, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-10-24-dataflow-design.md` and user master prompt.

## Global constraints
- No default destructive operations or source overwrites.
- No arbitrary execution from JSON; do not log cell data.
- GUI widgets update only on the main thread.
- Synthetic data; truthful AI-assisted portfolio labeling.
- Every documented command and claim must be verified.

## Review focus
- Formula-looking strings must stay text in both exports.
- Invalid filter/conversion input must fail without modifying source data.
- Duplicate/normalized column collisions must fail clearly.
- Partial batch failures preserve successful outputs and report failures.
- Background error handling must always re-enable GUI actions.

## Task 1: Core engine
- [ ] Write failing tests for configuration, transformations, file safety, Unicode and batch failures.
- [ ] Implement `src/dataflow/core` using API contract.
- [ ] Run core tests and report evidence.

## Task 2: CLI adapter
- [ ] Write failing CLI tests using Typer runner, including equality with core.
- [ ] Implement clean, process, convert, merge, batch, inspect and GUI launcher.
- [ ] Run CLI tests and command help.

## Task 3: GUI adapter
- [ ] Write controller tests for core parity and error handling.
- [ ] Build pages/components/theme and worker queue; all primary controls functional.
- [ ] Verify controller tests and launch real application.

## Task 4: Reproducibility and distribution
- [ ] Add pyproject, CI, deterministic examples and demo workflow.
- [ ] Create README, architecture, limitations, usage and portfolio/video copy.
- [ ] Run full pytest/Ruff, demo commands and independent review; resolve findings.
- [ ] Capture real GUI screens, record demo if possible, build and smoke-test EXE.
- [ ] Audit publication contents, commit, publish if available, verify remote CI; create source ZIP.
