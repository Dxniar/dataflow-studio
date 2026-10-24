"""Desktop pages composed from reusable widgets and application actions."""

from __future__ import annotations

import copy
import json
import logging

import customtkinter as ctk

from dataflow.core.validation import missing_count
from dataflow.gui import theme as t
from dataflow.gui.components import BoundEntry, DataPreview, MetricCard, card, entry, label, option
from dataflow.gui.controller import workflow_text


def _body(parent):
    body = ctk.CTkFrame(parent, fg_color="transparent")
    body.grid(row=0, column=0, sticky="nsew")
    body.grid_columnconfigure(0, weight=1)
    return body


def _subtitle(parent, text):
    label(parent, text, size=13, color=t.MUTED, anchor="w").pack(anchor="w", pady=(0, 14))


def _metrics(parent, items):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    for index, (title, value, accent) in enumerate(items):
        row.grid_columnconfigure(index, weight=1, uniform="metrics")
        metric = MetricCard(row, title, value, accent)
        metric.grid(
            row=0,
            column=index,
            sticky="ew",
            padx=(0 if index == 0 else 7, 0 if index == len(items) - 1 else 7),
        )
    return row


def _pipeline_text(app):
    try:
        config = app.collect_config()
    except Exception:
        config = app.config_data
    return workflow_text(config)


def _pipeline(parent, app, height=180):
    panel = card(parent)
    header = ctk.CTkFrame(panel, fg_color="transparent")
    header.pack(fill="x", padx=16, pady=(12, 8))
    label(header, "Workflow configuration", bold=True).pack(side="left")
    app.action(header, "Reset", lambda: app.apply_config({}), width=65).pack(side="right")
    text = ctk.CTkTextbox(
        panel,
        height=height,
        fg_color=t.BG,
        text_color=t.MUTED,
        font=("Consolas", 11),
        corner_radius=7,
    )
    text.pack(fill="both", expand=True, padx=14, pady=(0, 14))
    text.insert("1.0", _pipeline_text(app))
    text.configure(state="disabled")
    app.workflow_preview = text
    return panel


def _workflow_actions(parent, app):
    actions = ctk.CTkFrame(parent, fg_color="transparent")
    app.action(actions, "Run Workflow  →", app.run_processing, primary=True, width=165).pack(
        side="left", padx=(0, 10)
    )
    app.action(actions, "Run Batch", app.run_batch, width=110).pack(side="left", padx=(0, 10))
    app.action(actions, "Load JSON", app.load_config, width=100).pack(side="left", padx=(0, 10))
    app.action(actions, "Save JSON", app.save_config, width=100).pack(side="left")
    return actions


def dashboard(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(2, weight=1)
    hero = card(body)
    hero.grid(row=0, column=0, sticky="ew", pady=(0, 16))
    label(hero, "From messy spreadsheets to ready-to-use data.", size=22, bold=True).pack(
        anchor="w", padx=22, pady=(18, 5)
    )
    label(
        hero, "Clean, transform, merge and export — all in one local workspace.", color=t.MUTED
    ).pack(anchor="w", padx=22, pady=(0, 18))
    total_rows = sum(len(item.frame) for item in app.files)
    missing = sum(missing_count(item.frame) for item in app.files)
    metrics = _metrics(
        body,
        [
            ("Files loaded", len(app.files), t.TEXT),
            ("Source records", f"{total_rows:,}", t.TEXT),
            ("Missing values", f"{missing:,}", t.SECONDARY),
            (
                "Last result rows",
                f"{len(app.result.processed):,}" if app.result else "—",
                t.PRIMARY,
            ),
        ],
    )
    metrics.grid(row=1, column=0, sticky="ew", pady=(0, 16))
    lower = ctk.CTkFrame(body, fg_color="transparent")
    lower.grid(row=2, column=0, sticky="nsew")
    lower.grid_columnconfigure(1, weight=1)
    lower.grid_rowconfigure(0, weight=1)
    files_panel = card(lower, width=270)
    files_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
    files_panel.grid_propagate(False)
    files_panel.grid_columnconfigure(0, weight=1)
    files_panel.grid_rowconfigure(1, weight=1)
    head = ctk.CTkFrame(files_panel, fg_color="transparent")
    head.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
    label(head, "Workspace files", bold=True).pack(anchor="w")
    if app.files:
        listing = ctk.CTkScrollableFrame(files_panel, fg_color="transparent", width=230)
        listing.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        for index, item in enumerate(app.files):
            row = ctk.CTkFrame(listing, fg_color=t.BG, corner_radius=7)
            row.pack(fill="x", pady=4)
            label(row, item.path.name, size=12, anchor="w", wraplength=210).pack(
                anchor="w", padx=12, pady=(10, 0)
            )
            label(
                row,
                f"{'XLSX' if item.sheets else 'CSV'}  ·  {len(item.frame):,} rows  ·  {len(item.frame.columns)} columns",
                size=11,
                color=t.MUTED,
            ).pack(anchor="w", padx=12, pady=(0, 6))
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.pack(fill="x", padx=10, pady=(0, 10))
            app.action(
                actions, "Preview", lambda value=index: app.select_file(value), width=85
            ).pack(side="left")
            app.action(
                actions, "Remove", lambda value=index: app.remove_file(value), width=75
            ).pack(side="right")
    else:
        label(
            files_panel,
            "Upload CSV or XLSX files to preview your data and build a workflow.",
            color=t.MUTED,
        ).grid(row=1, column=0, sticky="nw", padx=18, pady=(0, 22))
    app.action(
        files_panel, "Start cleaning  →", lambda: app.show_page("Data Cleaning"), width=160
    ).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
    preview = DataPreview(lower, "Input data", height=240)
    preview.grid(row=0, column=1, sticky="nsew")
    preview.show(app.current_frame)


def cleaning(app, parent):
    body = _body(parent)
    body.grid_columnconfigure(1, weight=1)
    body.grid_columnconfigure(0, weight=0)
    body.grid_rowconfigure(0, weight=1)
    controls = ctk.CTkScrollableFrame(body, width=310, fg_color=t.SURFACE, corner_radius=12)
    controls.grid(row=0, column=0, sticky="ns", padx=(0, 18))
    label(controls, "Choose your operations", size=18, bold=True).pack(
        anchor="w", padx=14, pady=(12, 4)
    )
    label(controls, "Every change is opt-in.", size=12, color=t.MUTED).pack(
        anchor="w", padx=14, pady=(0, 16)
    )
    options = [
        ("trim_whitespace", "Trim whitespace", "Remove leading and trailing spaces."),
        ("drop_empty_rows", "Remove empty rows", "Remove rows where every cell is empty."),
        ("normalize_columns", "Normalize columns", "Use clean, consistent column names."),
        ("drop_duplicates", "Remove duplicates", "Keep the first matching record."),
    ]
    for key, name, hint in options:
        ctk.CTkCheckBox(
            controls,
            text=name,
            variable=app.clean_vars[key],
            command=app.refresh_workflow_preview,
            text_color=t.TEXT,
            fg_color=t.PRIMARY,
            hover_color=t.PRIMARY_HOVER,
            border_color=t.MUTED,
            font=(t.FONT, 13),
            checkbox_width=21,
            checkbox_height=21,
        ).pack(anchor="w", padx=14, pady=(9, 3))
        label(controls, hint, size=10, color=t.MUTED, wraplength=275, justify="left").pack(
            anchor="w", padx=44, pady=(0, 9)
        )
    label(controls, "Duplicate key columns", size=12, bold=True).pack(
        anchor="w", padx=14, pady=(12, 5)
    )
    BoundEntry(
        controls, textvariable=app.dedupe_var, height=36, fg_color=t.BG, border_color=t.BORDER
    ).pack(fill="x", padx=14)
    label(
        controls,
        "Comma-separated; leave blank for all columns.\nUse normalized names if normalization is enabled.",
        size=10,
        color=t.MUTED,
        justify="left",
        wraplength=275,
    ).pack(anchor="w", padx=14, pady=(5, 18))
    label(controls, "Fill missing values", size=14, bold=True).pack(
        anchor="w", padx=14, pady=(5, 8)
    )
    fill_column = entry(controls, "Column name")
    fill_column.pack(fill="x", padx=14, pady=4)
    fill_value = entry(controls, "Replacement (e.g. Unknown or 0)")
    fill_value.pack(fill="x", padx=14, pady=4)

    def add_fill():
        column = fill_column.get().strip()
        if not column:
            app.fail(ValueError("Enter the column to fill."))
            return
        try:
            config = app.collect_config()
            config.setdefault("fill_missing", {})[column] = _scalar(fill_value.get())
            app.apply_config(config)
            app.set_status(f"Added fill rule for {column}. Run the workflow to apply it.")
        except Exception as error:
            app.fail(error)

    app.action(controls, "+ Add fill rule", add_fill, width=260).pack(padx=14, pady=(8, 14))
    right = ctk.CTkFrame(body, fg_color="transparent")
    right.grid(row=0, column=1, sticky="nsew")
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(0, weight=1)
    preview = DataPreview(right, "Original data", height=250)
    preview.grid(row=0, column=0, sticky="nsew", pady=(0, 14))
    preview.show(app.current_frame)
    _pipeline(right, app, height=135).grid(row=1, column=0, sticky="ew", pady=(0, 14))
    _workflow_actions(right, app).grid(row=2, column=0, sticky="ew", pady=(0, 5))


def _scalar(value):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def transform(app, parent):
    body = _body(parent)
    body.grid_columnconfigure(0, weight=0)
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(0, weight=1)
    controls = ctk.CTkScrollableFrame(body, width=310, fg_color=t.SURFACE, corner_radius=12)
    controls.grid(row=0, column=0, sticky="ns", padx=(0, 18))
    label(controls, "Build a transformation", size=18, bold=True).pack(
        anchor="w", padx=14, pady=(14, 6)
    )
    label(controls, "Add a rule, then run your workflow.", size=12, color=t.MUTED).pack(
        anchor="w", padx=14, pady=(0, 18)
    )
    names = [
        "Rename column",
        "Drop columns",
        "Select columns",
        "Reorder columns",
        "Convert type",
        "Standardize values",
        "Filter rows",
        "Sort rows",
    ]
    operation = option(controls, names, width=274)
    operation.pack(padx=14, pady=(0, 15))
    label(controls, "Column / comma-separated columns", size=12, bold=True).pack(
        anchor="w", padx=14, pady=(0, 6)
    )
    column = entry(controls, "e.g. full_name or city, amount")
    column.pack(fill="x", padx=14, pady=(0, 14))
    label(controls, "Value / new name / value map", size=12, bold=True).pack(
        anchor="w", padx=14, pady=(0, 6)
    )
    value = entry(controls, 'e.g. customer_name or {"NY": "New York"}')
    value.pack(fill="x", padx=14, pady=(0, 14))
    label(controls, "Filter condition", size=12, bold=True).pack(anchor="w", padx=14, pady=(0, 6))
    condition = option(
        controls,
        [
            "equals",
            "not_equals",
            "contains",
            "greater_than",
            "less_than",
            "is_empty",
            "is_not_empty",
        ],
        width=274,
    )
    condition.pack(padx=14, pady=(0, 14))
    label(controls, "Target type", size=12, bold=True).pack(anchor="w", padx=14, pady=(0, 6))
    target_type = option(controls, ["string", "integer", "float", "datetime", "boolean"], width=274)
    target_type.pack(padx=14, pady=(0, 14))
    ascending = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(
        controls,
        text="Sort ascending",
        variable=ascending,
        text_color=t.TEXT,
        fg_color=t.PRIMARY,
        font=(t.FONT, 12),
    ).pack(anchor="w", padx=14, pady=8)

    def add_rule():
        try:
            config = copy.deepcopy(app.collect_config())
            name, raw_column, raw_value = operation.get(), column.get().strip(), value.get()
            columns = [part.strip() for part in raw_column.split(",") if part.strip()]
            if not columns:
                raise ValueError("Enter at least one column name.")
            if name == "Rename column":
                config.setdefault("rename_columns", {})[raw_column] = raw_value
            elif name in ("Drop columns", "Select columns", "Reorder columns"):
                key = {
                    "Drop columns": "drop_columns",
                    "Select columns": "select_columns",
                    "Reorder columns": "reorder_columns",
                }[name]
                config[key] = columns
            elif name == "Convert type":
                config.setdefault("convert_types", {})[raw_column] = target_type.get()
            elif name == "Standardize values":
                config.setdefault("standardize_values", {})[raw_column] = json.loads(raw_value)
            elif name == "Filter rows":
                config.setdefault("filters", []).append(
                    {"column": raw_column, "operator": condition.get(), "value": _scalar(raw_value)}
                )
            elif name == "Sort rows":
                config["sort_by"], config["sort_ascending"] = columns, ascending.get()
            app.apply_config(config)
            app.set_status(f"Added {name.lower()} rule. Review the configuration, then run.")
        except Exception as error:
            app.fail(error)

    app.action(controls, "+ Add to workflow", add_rule, primary=True, width=274).pack(
        padx=14, pady=(14, 12)
    )
    label(
        controls,
        'Value maps use JSON, for example:\n{"Almaty": "Алматы"}\n\nRules use the core\'s documented order.\nFilters and sorting use renamed columns.',
        size=11,
        color=t.MUTED,
        justify="left",
        wraplength=275,
    ).pack(anchor="w", padx=14, pady=(0, 16))
    right = ctk.CTkFrame(body, fg_color="transparent")
    right.grid(row=0, column=1, sticky="nsew")
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(1, weight=1)
    _pipeline(right, app, height=200).grid(row=0, column=0, sticky="ew", pady=(0, 14))
    preview = DataPreview(right, "Source preview", height=210)
    preview.grid(row=1, column=0, sticky="nsew", pady=(0, 14))
    preview.show(app.current_frame)
    _workflow_actions(right, app).grid(row=2, column=0, sticky="ew", pady=(0, 5))


def comparison(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(2, weight=1)
    result = app.result
    if result is None:
        empty = card(body)
        empty.grid(row=0, column=0, sticky="ew")
        label(empty, "Your results will appear here", size=24, bold=True).pack(
            anchor="w", padx=24, pady=(24, 8)
        )
        label(
            empty,
            "Choose cleaning or transformation operations, then run a workflow.",
            color=t.MUTED,
        ).pack(anchor="w", padx=24, pady=(0, 20))
        app.action(
            empty, "Build a workflow  →", lambda: app.show_page("Data Cleaning"), primary=True
        ).pack(anchor="w", padx=24, pady=(0, 24))
        return
    summary = result.summary()
    metrics = _metrics(
        body,
        [
            ("Original rows", f"{summary['original_rows']:,}", t.TEXT),
            ("Processed rows", f"{summary['processed_rows']:,}", t.PRIMARY),
            ("Duplicates removed", f"{summary['duplicates_removed']:,}", t.SECONDARY),
            ("Files processed", summary["files_processed"], t.TEXT),
        ],
    )
    metrics.grid(row=0, column=0, sticky="ew", pady=(0, 16))
    done = ctk.CTkFrame(body, fg_color="#13382E", corner_radius=10)
    done.grid(row=1, column=0, sticky="ew", pady=(0, 16))
    label(done, "✓  Completed successfully", color=t.PRIMARY, bold=True).pack(
        side="left", padx=18, pady=13
    )
    label(
        done,
        f"{result.elapsed_seconds:.3f}s  ·  {summary['processed_columns']} columns  ·  {summary['missing_after']} missing values",
        size=12,
        color=t.MUTED,
    ).pack(side="right", padx=18)
    previews = ctk.CTkFrame(body, fg_color="transparent")
    previews.grid(row=2, column=0, sticky="nsew", pady=(0, 16))
    previews.grid_columnconfigure((0, 1), weight=1, uniform="compare")
    previews.grid_rowconfigure(0, weight=1)
    for index, (title, frame) in enumerate(
        [("Original data", result.original), ("Processed data", result.processed)]
    ):
        preview = DataPreview(previews, title, height=285)
        preview.grid(row=0, column=index, sticky="nsew", padx=(0, 8) if index == 0 else (8, 0))
        preview.show(frame)
    detail = card(body)
    detail.grid(row=3, column=0, sticky="ew", pady=(0, 14))
    label(detail, "APPLIED OPERATIONS", size=10, color=t.MUTED, bold=True).pack(
        anchor="w", padx=18, pady=(13, 4)
    )
    label(
        detail,
        "  ·  ".join(result.operations) or "No transformations — original values preserved",
        size=12,
        wraplength=970,
        justify="left",
    ).pack(anchor="w", padx=18, pady=(0, 13))
    actions = ctk.CTkFrame(body, fg_color="transparent")
    actions.grid(row=4, column=0, sticky="ew", pady=(0, 5))
    app.action(actions, "Export Result  ↗", app.export_result, primary=True, width=170).pack(
        side="left", padx=(0, 12)
    )
    app.action(actions, "Run Batch", app.run_batch, width=120).pack(side="left")
    if app.last_export:
        label(actions, f"Saved: {app.last_export.name}", size=12, color=t.PRIMARY).pack(
            side="right"
        )
    else:
        label(actions, "Original files remain unchanged", size=11, color=t.MUTED).pack(side="right")


def merge(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(2, weight=1)
    controls = card(body)
    controls.grid(row=0, column=0, sticky="ew", pady=(0, 16))
    label(controls, "Combine records from all workspace files", size=21, bold=True).pack(
        anchor="w", padx=20, pady=(18, 5)
    )
    label(
        controls,
        "Union keeps every column · Strict requires matching schemas · Intersection keeps shared columns",
        size=12,
        color=t.MUTED,
    ).pack(anchor="w", padx=20, pady=(0, 14))
    row = ctk.CTkFrame(controls, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=(0, 18))
    option(row, ["union", "strict", "intersection"], variable=app.merge_mode_var).pack(
        side="left", padx=(0, 14)
    )
    app.action(row, "Merge Files  →", app.run_merge, primary=True, width=170).pack(side="left")
    label(row, "Uses the active worksheet name for every Excel file.", size=11, color=t.MUTED).pack(
        side="left", padx=16
    )
    schemas = card(body)
    schemas.grid(row=1, column=0, sticky="ew", pady=(0, 16))
    label(schemas, "Schema check", bold=True).pack(anchor="w", padx=18, pady=(12, 5))
    if app.files:
        sets = [set(item.frame.columns) for item in app.files]
        same = all(value == sets[0] for value in sets)
        shared = set.intersection(*sets)
        label(
            schemas,
            f"{len(app.files)} files  ·  {len(shared)} shared columns  ·  {'Matching column sets' if same else 'Different schemas — choose a suitable merge mode'}",
            size=12,
            color=t.PRIMARY if same else t.SECONDARY,
        ).pack(anchor="w", padx=18, pady=(0, 13))
    else:
        label(schemas, "Upload at least two files to compare schemas.", color=t.MUTED).pack(
            anchor="w", padx=18, pady=(0, 13)
        )
    preview = DataPreview(body, "Active source file", height=260)
    preview.grid(row=2, column=0, sticky="nsew", pady=(0, 5))
    preview.show(app.current_frame)


def convert(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(1, weight=1)
    controls = card(body)
    controls.grid(row=0, column=0, sticky="ew", pady=(0, 18))
    label(controls, "CSV ⇄ Excel", size=30, bold=True).pack(anchor="w", padx=22, pady=(18, 6))
    label(
        controls,
        "Export the active source table in a different format. Choose an Excel worksheet above.",
        color=t.MUTED,
    ).pack(anchor="w", padx=22, pady=(0, 12))
    row = ctk.CTkFrame(controls, fg_color="transparent")
    row.pack(fill="x", padx=22, pady=(0, 18))
    label(row, "Output format", size=12).pack(side="left", padx=(0, 14))
    option(row, ["csv", "xlsx"], variable=app.output_format_var, width=130).pack(
        side="left", padx=(0, 14)
    )
    app.action(row, "Convert & Save  ↗", app.run_conversion, primary=True, width=190).pack(
        side="left"
    )
    label(row, "Values only · Original files are protected", size=11, color=t.MUTED).pack(
        side="right"
    )
    preview = DataPreview(body, "Data to convert", height=320)
    preview.grid(row=1, column=0, sticky="nsew", pady=(0, 16))
    preview.show(app.current_frame)
    label(
        body,
        "CSV settings are shared with import/export. Workbook formatting, charts and macros are not preserved.",
        size=11,
        color=t.MUTED,
        anchor="w",
    ).grid(row=2, column=0, sticky="ew", pady=(0, 5))


def history(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(1, weight=1)
    label(
        body,
        "Session activity, output paths and processing errors",
        size=13,
        color=t.MUTED,
        anchor="w",
    ).grid(row=0, column=0, sticky="ew", pady=(0, 14))
    listing = ctk.CTkScrollableFrame(body, fg_color=t.SURFACE, corner_radius=12)
    listing.grid(row=1, column=0, sticky="nsew", pady=(0, 14))
    if not app.history:
        label(listing, "No activity yet. Import a file to begin.", color=t.MUTED).pack(
            anchor="w", padx=20, pady=20
        )
    for event in reversed(app.history):
        row = ctk.CTkFrame(listing, fg_color=t.BG, corner_radius=8)
        row.pack(fill="x", padx=10, pady=6)
        head = ctk.CTkFrame(row, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 3))
        label(
            head,
            event["action"],
            size=13,
            bold=True,
            color=t.ERROR if "error" in event["action"].lower() else t.PRIMARY,
        ).pack(side="left")
        label(head, event["time"], size=11, color=t.MUTED).pack(side="right")
        label(row, event["detail"], size=12, color=t.MUTED, wraplength=940, justify="left").pack(
            anchor="w", padx=14, pady=(0, 12)
        )
    app.action(body, "Export batch report (JSON)", lambda: _export_report(app), width=225).grid(
        row=2, column=0, sticky="w", pady=(0, 5)
    )


def _export_report(app):
    from pathlib import Path
    from tkinter import filedialog

    if app.last_batch is None:
        app.fail(ValueError("Run a batch before exporting its report."))
        return
    path = filedialog.asksaveasfilename(
        title="Export batch report", defaultextension=".json", filetypes=[("JSON report", "*.json")]
    )
    if path:
        try:
            with Path(path).open("x", encoding="utf-8") as stream:
                json.dump(
                    {"successes": app.last_batch.successes, "errors": app.last_batch.errors},
                    stream,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            app.set_status(f"Batch report saved: {path}", success=True)
        except Exception as error:
            app.fail(error)


def settings(app, parent):
    body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
    body.grid(row=0, column=0, sticky="nsew")
    _subtitle(
        body,
        "Settings apply to this session. Import changes take effect when files are loaded again.",
    )
    panel = card(body)
    panel.pack(fill="x", pady=(0, 16))
    label(panel, "Appearance", size=18, bold=True).pack(anchor="w", padx=22, pady=(18, 12))
    option(panel, ["Midnight", "Graphite"], variable=app.theme_var, command=app.change_theme).pack(
        anchor="w", padx=22, pady=(0, 18)
    )
    panel = card(body)
    panel.pack(fill="x", pady=(0, 16))
    label(panel, "Files & export", size=18, bold=True).pack(anchor="w", padx=22, pady=(18, 12))
    directory = ctk.CTkFrame(panel, fg_color="transparent")
    directory.pack(fill="x", padx=22, pady=(0, 16))
    BoundEntry(
        directory, textvariable=app.output_dir_var, height=36, fg_color=t.BG, border_color=t.BORDER
    ).pack(side="left", fill="x", expand=True, padx=(0, 12))
    app.action(directory, "Browse", app.choose_output_dir, width=100).pack(side="right")
    fields = ctk.CTkFrame(panel, fg_color="transparent")
    fields.pack(fill="x", padx=22, pady=(0, 18))
    for index, (title, values, variable) in enumerate(
        [
            (
                "CSV encoding",
                ["utf-8-sig", "utf-8", "cp1251", "latin-1", "utf-16"],
                app.encoding_var,
            ),
            ("CSV delimiter", [",", ";", "\\t", "|"], app.delimiter_var),
            ("Output name collision", ["unique", "error"], app.collision_var),
            ("Batch output", ["csv", "xlsx"], app.output_format_var),
        ]
    ):
        field = ctk.CTkFrame(fields, fg_color="transparent")
        field.grid(row=0, column=index, padx=(0, 18), sticky="w")
        label(field, title, size=11, color=t.MUTED).pack(anchor="w", pady=(0, 6))
        option(field, values, variable=variable, width=155).pack(anchor="w")
    label(
        panel,
        "unique creates a new filename; error refuses existing output paths. Source files are always protected.",
        size=11,
        color=t.MUTED,
    ).pack(anchor="w", padx=22, pady=(0, 18))
    app.action(panel, "Reload active file with these settings", app.reload_current, width=300).pack(
        anchor="w", padx=22, pady=(0, 18)
    )
    label(
        panel,
        "Batch and merge use the active worksheet name for every Excel file.\nSelect the intended common sheet before starting.",
        size=11,
        color=t.MUTED,
        justify="left",
    ).pack(anchor="w", padx=22, pady=(0, 18))
    panel = card(body)
    panel.pack(fill="x", pady=(0, 16))
    label(panel, "Logging", size=18, bold=True).pack(anchor="w", padx=22, pady=(18, 12))
    option(
        panel,
        ["DEBUG", "INFO", "WARNING", "ERROR"],
        variable=app.log_level_var,
        command=lambda value: logging.getLogger("dataflow").setLevel(value),
    ).pack(anchor="w", padx=22, pady=(0, 12))
    label(
        panel,
        "Logs record operation metadata. Table contents are not written to logs.\nHistory is kept in memory for the current session.",
        size=12,
        color=t.MUTED,
        justify="left",
    ).pack(anchor="w", padx=22, pady=(0, 18))
    label(
        panel,
        f"Local log: {app.log_path}"
        if app.log_path
        else "Local log unavailable: check folder permissions.",
        size=11,
        color=t.MUTED,
        wraplength=740,
        justify="left",
    ).pack(anchor="w", padx=22, pady=(0, 18))


def build_page(app, parent, name):
    {
        "Dashboard": dashboard,
        "Data Cleaning": cleaning,
        "Transform Data": transform,
        "Merge Files": merge,
        "Convert Files": convert,
        "Before / After": comparison,
        "History & Logs": history,
        "Settings": settings,
    }[name](app, parent)
