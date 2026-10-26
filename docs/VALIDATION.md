# Validation record

## 1.2.0 workflow reliability

Dates: 26–27 October 2026. Implemented typed import, data validation, persistent local workspaces and cooperative cancellation/recovery. The prior 1.1 record below is retained as historical evidence.

Meaningful new automated cases cover lexical IDs, locale numbers/dates, source changes during parsing, resource guards before header/sheet discovery, validation and rejected-row exports, malformed/corrupt/future-version workspace state, progress/cancellation, and resumable batches. Independent reviews found and corrected stale GUI validation results, lost inherited recovery checkpoints and invalid saved-run shapes.

`scripts/gui_production_smoke.py` exercises actual Tk controls and shared workers in two isolated Python processes. Its first process imports explicit types, validates/exports actual XLSX, processes data, cancels after a durable first-file checkpoint, retries pending/failed sources, then exits abruptly during another batch. The second process restores preferences/history/rules, explicitly reloads files, recovers the interrupted batch and checks successful output/source SHA-256 hashes. The complete source workflow passed before final packaging; final check results are recorded below when executed.

The Windows Computer Use screenshot bridge was unavailable during this revision. Functional native GUI checks are separate from visual screenshot inspection; no new screenshot-based visual approval is claimed. The existing screenshots/video describe the 1.1 design.

### Executed 1.2 checks

| Check | Observed result |
| --- | --- |
| Full pytest suite | 266 passed |
| Ruff lint and formatting | Passed |
| Legacy native GUI smoke | All 9 pages and 10 workflows passed; source hashes unchanged |
| Two-process production GUI smoke | Passed with clean process exits; typed IDs/locale/dates, exact rejected XLSX, cancel/retry, repair/retry and hard-stop recovery checked |
| PyInstaller Windows build | Completed successfully |
| Packaged EXE startup | Process remained alive after startup and initialized an isolated SQLite workspace |
| Independent whole-branch review | Both confirmed P2 findings fixed and scoped re-review cleared |

The packaged EXE startup check is distinct from the complete source-application GUI scenario. No screenshot-based visual approval or complete packaged-EXE interaction test is claimed. Generated evidence is under `artifacts/`; it contains only synthetic QA fixtures. Remote CI status is available from [GitHub Actions](https://github.com/Dxniar/dataflow-studio/actions/workflows/ci.yml).

## Historical 1.1.0 validation

Date: 25 October 2026. Environment: Windows 11 x64, Python 3.12.0.

Historical release: **1.1.0**, with the redesigned desktop workspace. Local tests and the real desktop smoke were rerun for that revision. The desktop check also forces garbage collection in a worker after page changes and verifies that destroyed Tk variables were reclaimed on the main thread.

## Executed local checks

| Check | Observed result |
| --- | --- |
| `python -m pytest -q` | 103 passed, including forced-color CLI rendering |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | All checked files formatted |
| `python scripts/run_demo.py` | Passed assertions for cleanup, conversion, merging, batch and unchanged processing inputs |
| README CLI examples | All 8 file-command examples exited 0; global and six subcommand help checks passed |
| CLI source protection | Separate SHA-256 comparison confirmed all input files unchanged |
| `python scripts/gui_smoke.py` | Real Tk window passed all eight pages and ten workflow checks, including usable Dashboard/comparison preview sizes |
| `python -m build --no-isolation` | Wheel and source distribution built successfully |
| `python scripts/build_windows.py` | PyInstaller portable Windows folder built successfully |
| Windows EXE launch | Native DataFlow Studio window observed from `dist/DataFlowStudio/DataFlowStudio.exe` |

The GUI smoke run verified CSV/XLSX loading, worksheet switching, shared processing, before/after metrics, actual XLSX readback, source overwrite rejection and control recovery, conversion, two-file batch, merge, themes and unchanged source hashes. The deliberate overwrite attempt is an expected error-path check. The portable EXE received a launch smoke check; the automated workflow checks ran against the Python source application.

## Demonstrated results

- Original rows: **153**; processed rows: **132**.
- Duplicates removed: **18**; entirely empty rows removed: **3**.
- Missing cells: **39 → 0**; columns: **6 → 6**.
- Batch: **2 processed**, **0 failed**.
- These values describe checked-in synthetic fixtures, not business impact or performance guarantees.

## Review

An independent source review checked configuration order, immutable input frames, export collision protection, formula-looking text, partial batch failures, CLI semantics and main-thread GUI updates. Its two findings (an inactive GUI log setting and imprecise type-inference documentation) were resolved and reviewed again. Native visual checks additionally found and corrected preview clipping on smaller windows.

## Media

Five screenshots were captured from the running application/window recording. The MP4 is approximately 60 seconds, 1920×1080, H.264, 15 fps, with English captions, no audio and no watermark. It records a deterministic playback of real GUI actions calling the same processing/export services. It is an edited, captioned screen recording; no result values or UI states were fabricated. All included table records are synthetic.

The local verification files under `artifacts/` contain detailed JSON evidence and recording logs. They are generated, machine-specific artifacts and are excluded from Git.

## Remote CI

The 1.1.0 [run 40178137674](https://github.com/Dxniar/dataflow-studio/actions/runs/40178137674) completed successfully for commit `47ab04085bcf161495f8cac703ace76fd8c07d8c`: all seven jobs passed, including all six OS/Python test combinations and the Windows build. Final screenshot and documentation updates preserve that tested runtime code.

Historical 1.0 validation: [run 40139251864](https://github.com/Dxniar/dataflow-studio/actions/runs/40139251864) passed all seven jobs for commit `0a90edcb555eced6076f7c07a2d46314da5f8967`. [GitHub Actions](https://github.com/Dxniar/dataflow-studio/actions/workflows/ci.yml) remains the live source for remote status.

## Practical limits

The Windows app is unsigned and must retain its `_internal` directory. Whole files are processed in memory. pandas can infer types on import, and workbook formatting/formulas are not preserved. See [limitations](LIMITATIONS.md).
