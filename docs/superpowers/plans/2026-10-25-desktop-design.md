# Desktop visual refresh

The user rejected the initial visual design. The existing detailed specification delegates ordinary design/engineering choices, so the revision proceeds directly against the existing desktop code. The engine and file-safety semantics remain binding.

## Visual direction
An understated data workspace: graphite/navy surfaces, restrained green actions, crisp line icons, compact navigation, and generous readable tables. Remove the oversized promotional banner, repeated elevated cards, white native scrollbars, technical-stack footer and dominant raw JSON preview.

## Ownership and interfaces
- Root: `theme.py`, `components.py`, new `icons.py`, `app.py` shell and refresh integration.
- Pages agent: `pages.py` only, full page layout refinement.
- Reviewer: read-only desktop UX/implementation review after visual capture.

Existing public app methods and all processing behavior stay compatible. `WorkflowCard(parent, *, on_reset=None, height=120)` provides `render(config_dict)`. Pages assign it to `app.workflow_preview`; root updates `refresh_workflow_preview()` to call `render`. Keep all existing component function names; new metric cards use one shared subtle surface rather than large tiles. `DataPreview.show(frame)` remains compatible.

## Tasks
- [ ] Compact shell, design tokens, line icons, table and workflow components.
- [ ] Dashboard, cleaning, transformation, comparison, utility/history/settings layouts.
- [ ] Real native screenshots, full existing tests and GUI smoke, fix layout regressions.
- [ ] Update deliverables to match the verified design.
