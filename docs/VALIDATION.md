# Validation record

Date: 25 October 2026. Environment: Windows 11 x64, Python 3.12.0.

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

[GitHub Actions](https://github.com/Dxniar/dataflow-studio/actions/workflows/ci.yml) is the live source for remote status. The workflow covers Windows/Linux, Python 3.11–3.13, lint, formatting, tests, reproducible demo, package builds and a Windows portable build. This record of local checks does not itself assert that a remote run passed.

## Practical limits

The Windows app is unsigned and must retain its `_internal` directory. Whole files are processed in memory. pandas can infer types on import, and workbook formatting/formulas are not preserved. See [limitations](LIMITATIONS.md).
