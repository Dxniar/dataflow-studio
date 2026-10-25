"""Desktop workspaces composed from shared controls and application actions."""

from __future__ import annotations

import copy
import json
import logging

import customtkinter as ctk

from dataflow.core.validation import missing_count
from dataflow.gui import theme as t
from dataflow.gui.components import (
    BoundEntry,
    DataPreview,
    MetricCard,
    WorkflowCard,
    card,
    entry,
    label,
    option,
)
from dataflow.gui.icons import icon


def _body(parent):
    body = ctk.CTkFrame(parent, fg_color="transparent")
    body.grid(row=0, column=0, sticky="nsew")
    body.grid_columnconfigure(0, weight=1)
    return body


def _subtitle(parent, text):
    label(parent, text, size=12, color=t.MUTED, anchor="w").pack(anchor="w", pady=(0, 16))


def _metrics(parent, items):
    """One quiet summary bar instead of competing elevated cards."""
    row = card(parent)
    for index, (title, value, accent) in enumerate(items):
        row.grid_columnconfigure(index * 2, weight=1, uniform="metrics")
        MetricCard(row, title, value, accent).grid(
            row=0, column=index * 2, sticky="ew", padx=8, pady=6
        )
        if index < len(items) - 1:
            ctk.CTkFrame(row, width=1, height=30, fg_color=t.BORDER, corner_radius=0).grid(
                row=0, column=index * 2 + 1, padx=3
            )
    return row


def _pipeline(parent, app, height=120):
    panel = WorkflowCard(parent, on_reset=lambda: app.apply_config({}), height=height)
    app.workflow_preview = panel
    try:
        panel.render(app.collect_config())
    except Exception:
        panel.render(app.config_data)
    return panel


def _workflow_actions(parent, app):
    actions = ctk.CTkFrame(parent, fg_color="transparent")
    app.action(actions, "Load", app.load_config, variant="ghost", width=59, height=34).pack(
        side="left", padx=(0, 3)
    )
    app.action(actions, "Save", app.save_config, variant="ghost", width=59, height=34).pack(
        side="left"
    )
    app.action(
        actions,
        "Run workflow",
        app.run_processing,
        primary=True,
        width=139,
        height=36,
        image=icon("play", color=t.BG, size=15),
        compound="left",
    ).pack(side="right", padx=(8, 0))
    app.action(actions, "Run batch", app.run_batch, width=96, height=36).pack(side="right")
    return actions


def dashboard(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(1, weight=1)
    _metrics(
        body,
        [
            ("Files", len(app.files), t.TEXT),
            ("Source rows", f"{sum(len(item.frame) for item in app.files):,}", t.TEXT),
            (
                "Missing values",
                f"{sum(missing_count(item.frame) for item in app.files):,}",
                t.WARNING,
            ),
            ("Latest result", f"{len(app.result.processed):,}" if app.result else "—", t.PRIMARY),
        ],
    ).grid(row=0, column=0, sticky="ew", pady=(0, 16))
    workspace = ctk.CTkFrame(body, fg_color="transparent")
    workspace.grid(row=1, column=0, sticky="nsew")
    workspace.grid_columnconfigure(1, weight=1)
    workspace.grid_rowconfigure(0, weight=1)
    files = card(workspace, width=250)
    files.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
    files.grid_propagate(False)
    files.grid_columnconfigure(0, weight=1)
    files.grid_rowconfigure(1, weight=1)
    head = ctk.CTkFrame(files, fg_color="transparent")
    head.grid(row=0, column=0, sticky="ew", padx=16, pady=(15, 12))
    label(head, "Files", size=14, bold=True).pack(side="left")
    label(head, str(len(app.files)), size=11, color=t.MUTED).pack(side="left", padx=9)
    app.action(head, "+", app.choose_files, width=28, height=28, variant="ghost").pack(side="right")
    if app.files:
        listing = ctk.CTkScrollableFrame(
            files,
            fg_color="transparent",
            width=220,
            corner_radius=0,
            scrollbar_button_color=t.SUBTLE,
            scrollbar_button_hover_color=t.MUTED,
        )
        listing.grid(row=1, column=0, sticky="nsew", padx=7, pady=(0, 8))
        for index, item in enumerate(app.files):
            selected = index == app.selected_index
            row = ctk.CTkFrame(
                listing,
                fg_color=t.PRIMARY_SOFT if selected else "transparent",
                border_width=1,
                border_color=t.BORDER,
                corner_radius=7,
            )
            row.pack(fill="x", pady=(0, 8))
            top = ctk.CTkFrame(row, fg_color="transparent")
            top.pack(fill="x", padx=8, pady=(8, 0))
            name = item.path.name
            display = name if len(name) <= 23 else name[:17] + "…" + item.path.suffix
            app.action(
                top,
                display,
                lambda value=index: app.select_file(value),
                variant="ghost",
                width=160,
                height=28,
                anchor="w",
                image=icon("file", color=t.PRIMARY if selected else t.MUTED, size=16),
                compound="left",
            ).pack(side="left", fill="x", expand=True)
            app.action(
                top,
                "×",
                lambda value=index: app.remove_file(value),
                variant="ghost",
                width=23,
                height=25,
            ).pack(side="right")
            label(
                row,
                f"{'XLSX' if item.sheets else 'CSV'}   ·   {len(item.frame):,} rows   ·   {len(item.frame.columns)} columns",
                size=11,
                color=t.MUTED,
            ).pack(anchor="w", padx=13, pady=(1, 10))
    else:
        empty = ctk.CTkFrame(files, fg_color="transparent")
        empty.grid(row=1, column=0, sticky="new", padx=18, pady=25)
        label(empty, "No files yet", size=14, bold=True).pack(anchor="w", pady=(0, 8))
        label(
            empty,
            "Add a CSV or Excel file to preview your records.",
            size=12,
            color=t.MUTED,
            wraplength=190,
            justify="left",
        ).pack(anchor="w")
        app.action(empty, "Add files", app.choose_files, height=34, width=130).pack(
            anchor="w", pady=(16, 0)
        )
    app.action(
        files,
        "Build a workflow",
        lambda: app.show_page("Data Cleaning"),
        width=180,
        height=36,
        image=icon("arrow_right", color=t.MUTED, size=15),
        compound="right",
    ).grid(row=2, column=0, sticky="ew", padx=14, pady=(5, 14))
    preview = DataPreview(workspace, "Data preview", height=420)
    preview.grid(row=0, column=1, sticky="nsew")
    preview.show(app.current_frame)


def cleaning(app, parent):
    body = _body(parent)
    body.grid_columnconfigure(0, weight=0)
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(0, weight=1)
    controls = ctk.CTkScrollableFrame(
        body,
        width=282,
        fg_color=t.PANEL,
        corner_radius=9,
        border_width=1,
        border_color=t.BORDER,
        scrollbar_button_color=t.SUBTLE,
        scrollbar_button_hover_color=t.MUTED,
    )
    controls.grid(row=0, column=0, sticky="ns", padx=(0, 16))
    label(controls, "Cleaning rules", size=15, bold=True).pack(anchor="w", padx=14, pady=(14, 5))
    label(controls, "Choose what changes in your table.", size=12, color=t.MUTED).pack(
        anchor="w", padx=14, pady=(0, 16)
    )
    options = [
        ("trim_whitespace", "Trim whitespace", "Clean up spaces around text."),
        ("drop_empty_rows", "Remove empty rows", "Keep only rows with a value."),
        ("normalize_columns", "Normalize headers", "Use consistent column names."),
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
            border_color=t.SUBTLE,
            font=(t.FONT, 13),
            checkbox_width=19,
            checkbox_height=19,
            corner_radius=4,
            height=27,
        ).pack(anchor="w", padx=14, pady=(5, 0))
        label(controls, hint, size=11, color=t.MUTED, wraplength=225, justify="left").pack(
            anchor="w", padx=42, pady=(0, 10)
        )
    ctk.CTkFrame(controls, height=1, fg_color=t.BORDER).pack(fill="x", padx=14, pady=(8, 16))
    label(controls, "Duplicate key columns", size=12, bold=True).pack(
        anchor="w", padx=14, pady=(0, 7)
    )
    BoundEntry(
        controls,
        textvariable=app.dedupe_var,
        height=35,
        fg_color=t.BG,
        border_color=t.BORDER,
        placeholder_text="e.g. customer_id",
    ).pack(fill="x", padx=14)
    label(
        controls,
        "Comma-separated. Leave empty to compare all columns. Use new names after header normalization.",
        size=11,
        color=t.MUTED,
        justify="left",
        wraplength=245,
    ).pack(anchor="w", padx=14, pady=(6, 18))
    ctk.CTkFrame(controls, height=1, fg_color=t.BORDER).pack(fill="x", padx=14, pady=(0, 16))
    label(controls, "Fill missing values", size=13, bold=True).pack(
        anchor="w", padx=14, pady=(0, 10)
    )
    fill_column = entry(controls, "Column name")
    fill_column.pack(fill="x", padx=14, pady=(0, 7))
    fill_value = entry(controls, "Replacement, e.g. Unknown or 0")
    fill_value.pack(fill="x", padx=14)

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

    app.action(controls, "+ Add fill rule", add_fill, width=244, height=34).pack(
        padx=14, pady=(10, 16)
    )
    right = ctk.CTkFrame(body, fg_color="transparent")
    right.grid(row=0, column=1, sticky="nsew")
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(0, weight=1)
    preview = DataPreview(right, "Original data", height=300)
    preview.grid(row=0, column=0, sticky="nsew", pady=(0, 14))
    preview.show(app.current_frame)
    _pipeline(right, app, height=124).grid(row=1, column=0, sticky="ew", pady=(0, 12))
    _workflow_actions(right, app).grid(row=2, column=0, sticky="ew")


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
    controls = ctk.CTkScrollableFrame(
        body,
        width=282,
        fg_color=t.PANEL,
        corner_radius=9,
        border_width=1,
        border_color=t.BORDER,
        scrollbar_button_color=t.SUBTLE,
        scrollbar_button_hover_color=t.MUTED,
    )
    controls.grid(row=0, column=0, sticky="ns", padx=(0, 16))
    label(controls, "Add a transformation", size=15, bold=True).pack(
        anchor="w", padx=14, pady=(14, 5)
    )
    label(
        controls,
        "Build your workflow one rule at a time.",
        size=12,
        color=t.MUTED,
        wraplength=245,
        justify="left",
    ).pack(anchor="w", padx=14, pady=(0, 16))
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
    operation = option(controls, names, width=250)
    operation.pack(padx=14, pady=(0, 18))
    column_title = label(controls, "Column", size=12, bold=True)
    column_title.pack(anchor="w", padx=14, pady=(0, 7))
    column = entry(controls, "e.g. full_name")
    column.pack(fill="x", padx=14, pady=(0, 15))
    dynamic = ctk.CTkFrame(controls, fg_color="transparent")
    dynamic.pack(fill="x", padx=14)
    value_field = ctk.CTkFrame(dynamic, fg_color="transparent")
    value_title = label(value_field, "New column name", size=12, bold=True)
    value_title.pack(anchor="w", pady=(0, 7))
    value = entry(value_field, "e.g. customer_name")
    value.pack(fill="x")
    condition_field = ctk.CTkFrame(dynamic, fg_color="transparent")
    label(condition_field, "Condition", size=12, bold=True).pack(anchor="w", pady=(0, 7))
    condition = option(
        condition_field,
        [
            "equals",
            "not_equals",
            "contains",
            "greater_than",
            "less_than",
            "is_empty",
            "is_not_empty",
        ],
        width=250,
    )
    condition.pack(fill="x")
    type_field = ctk.CTkFrame(dynamic, fg_color="transparent")
    label(type_field, "Convert to", size=12, bold=True).pack(anchor="w", pady=(0, 7))
    target_type = option(
        type_field, ["string", "integer", "float", "datetime", "boolean"], width=250
    )
    target_type.pack(fill="x")
    order_field = ctk.CTkFrame(dynamic, fg_color="transparent")
    ascending = ctk.BooleanVar(value=app.config_data.get("sort_ascending", True))
    ctk.CTkCheckBox(
        order_field,
        text="Sort ascending",
        variable=ascending,
        text_color=t.TEXT,
        fg_color=t.PRIMARY,
        border_color=t.SUBTLE,
        checkbox_width=19,
        checkbox_height=19,
        corner_radius=4,
        font=(t.FONT, 12),
    ).pack(anchor="w")

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
            app.set_status(f"Added {name.lower()} rule. Review the workflow, then run.")
        except Exception as error:
            app.fail(error)

    app.action(controls, "+ Add to workflow", add_rule, primary=True, width=250, height=35).pack(
        padx=14, pady=(3, 14)
    )
    hint = label(controls, "", size=11, color=t.MUTED, justify="left", wraplength=245)
    hint.pack(anchor="w", padx=14, pady=(0, 18))

    def show_fields(name):
        for field in (value_field, condition_field, type_field, order_field):
            field.pack_forget()
        column_title.configure(
            text="Columns, separated by commas"
            if name in {"Drop columns", "Select columns", "Reorder columns", "Sort rows"}
            else "Column"
        )
        if name in {"Rename column", "Standardize values", "Filter rows"}:
            value_title.configure(
                text={
                    "Rename column": "New column name",
                    "Standardize values": "Value mapping",
                    "Filter rows": "Match value",
                }[name]
            )
            value.configure(
                placeholder_text={
                    "Rename column": "e.g. customer_name",
                    "Standardize values": '{"NY": "New York"}',
                    "Filter rows": "e.g. Almaty or 100",
                }[name]
            )
            value_field.pack(fill="x", pady=(0, 15))
        if name == "Filter rows":
            condition_field.pack(fill="x", pady=(0, 15))
        if name == "Convert type":
            type_field.pack(fill="x", pady=(0, 15))
        if name == "Sort rows":
            order_field.pack(fill="x", pady=(0, 16))
        hint.configure(
            text={
                "Rename column": "Filters and sorting use the new column name after renaming.",
                "Drop columns": "Remove only the columns you list here.",
                "Select columns": "Keep only these columns, in the order you enter.",
                "Reorder columns": "List every column in your preferred order.",
                "Convert type": "Values must be compatible with the selected type.",
                "Standardize values": 'Use an exact mapping, e.g. {"NY": "New York"}.',
                "Filter rows": "All filter rules must match. Empty/not-empty conditions do not need a value.",
                "Sort rows": "The first column is the primary sort key.",
            }[name]
        )

    operation.configure(command=show_fields)
    show_fields(operation.get())
    right = ctk.CTkFrame(body, fg_color="transparent")
    right.grid(row=0, column=1, sticky="nsew")
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(0, weight=1)
    preview = DataPreview(right, "Source preview", height=300)
    preview.grid(row=0, column=0, sticky="nsew", pady=(0, 14))
    preview.show(app.current_frame)
    _pipeline(right, app, height=124).grid(row=1, column=0, sticky="ew", pady=(0, 12))
    _workflow_actions(right, app).grid(row=2, column=0, sticky="ew")


def _show_operations(app, operations):
    window = ctk.CTkToplevel(app)
    window.title("Applied operations")
    window.geometry("420x360")
    window.configure(fg_color=t.BG)
    window.transient(app)
    label(window, "Applied operations", size=18, bold=True).pack(anchor="w", padx=22, pady=(22, 6))
    label(window, "The steps used for this result.", size=12, color=t.MUTED).pack(
        anchor="w", padx=22, pady=(0, 14)
    )
    listing = ctk.CTkScrollableFrame(window, fg_color=t.PANEL, corner_radius=8)
    listing.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    for index, operation in enumerate(operations, 1):
        label(listing, f"{index:02d}   {operation}", size=13, anchor="w").pack(
            fill="x", padx=12, pady=7
        )
    if not operations:
        label(listing, "No transformations were selected.", color=t.MUTED).pack(padx=12, pady=14)
    window.after(100, window.lift)


def comparison(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(2, weight=1)
    result = app.result
    if result is None:
        empty = card(body)
        empty.grid(row=0, column=0, sticky="ew")
        label(empty, "Review your changes here", size=18, bold=True).pack(
            anchor="w", padx=22, pady=(22, 7)
        )
        label(
            empty,
            "Run a cleaning or transformation workflow to compare it with the original.",
            size=13,
            color=t.MUTED,
        ).pack(anchor="w", padx=22, pady=(0, 18))
        app.action(
            empty,
            "Build a workflow",
            lambda: app.show_page("Data Cleaning"),
            primary=True,
            width=165,
            height=36,
        ).pack(anchor="w", padx=22, pady=(0, 22))
        return
    summary = result.summary()
    _metrics(
        body,
        [
            ("Original rows", f"{summary['original_rows']:,}", t.TEXT),
            ("Processed rows", f"{summary['processed_rows']:,}", t.PRIMARY),
            ("Duplicates removed", f"{summary['duplicates_removed']:,}", t.TEXT),
            ("Files processed", summary["files_processed"], t.TEXT),
        ],
    ).grid(row=0, column=0, sticky="ew", pady=(0, 12))
    status = ctk.CTkFrame(body, fg_color="transparent")
    status.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    label(
        status,
        "Completed",
        size=12,
        color=t.PRIMARY,
        bold=True,
        image=icon("check", color=t.PRIMARY, size=15),
        compound="left",
    ).pack(side="left")
    label(
        status,
        f"{result.elapsed_seconds:.3f}s   ·   {summary['processed_columns']} columns   ·   {summary['missing_after']} missing values",
        size=12,
        color=t.MUTED,
    ).pack(side="right")
    previews = ctk.CTkFrame(body, fg_color="transparent")
    previews.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
    previews.grid_columnconfigure((0, 1), weight=1, uniform="compare")
    previews.grid_rowconfigure(0, weight=1)
    for index, (title, frame) in enumerate(
        [("Original", result.original), ("Processed", result.processed)]
    ):
        preview = DataPreview(previews, title, height=350)
        preview.grid(row=0, column=index, sticky="nsew", padx=(0, 7) if index == 0 else (7, 0))
        preview.show(frame)
    details = ctk.CTkFrame(body, fg_color="transparent")
    details.grid(row=3, column=0, sticky="ew", pady=(0, 12))
    names = "  ·  ".join(result.operations[:4]) or "No transformations"
    if len(result.operations) > 4:
        names += f"  ·  +{len(result.operations) - 4} more"
    label(details, names, size=11, color=t.MUTED, anchor="w").pack(side="left")
    app.action(
        details,
        f"View {len(result.operations)} steps",
        lambda: _show_operations(app, result.operations),
        variant="ghost",
        width=110,
        height=27,
    ).pack(side="right")
    actions = ctk.CTkFrame(body, fg_color="transparent")
    actions.grid(row=4, column=0, sticky="ew")
    app.action(
        actions,
        "Export result",
        app.export_result,
        primary=True,
        width=155,
        height=36,
        image=icon("download", color=t.BG, size=16),
        compound="left",
    ).pack(side="left", padx=(0, 8))
    app.action(actions, "Run batch", app.run_batch, width=105, height=36).pack(side="left")
    label(
        actions,
        f"Saved: {app.last_export.name}" if app.last_export else "Ready to export",
        size=12,
        color=t.PRIMARY if app.last_export else t.MUTED,
    ).pack(side="right")


def merge(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(1, weight=1)
    controls = card(body)
    controls.grid(row=0, column=0, sticky="ew", pady=(0, 16))
    label(controls, "Combine workspace files", size=15, bold=True).pack(
        anchor="w", padx=18, pady=(16, 5)
    )
    label(
        controls, "Append rows and align the columns across your files.", size=12, color=t.MUTED
    ).pack(anchor="w", padx=18, pady=(0, 13))
    row = ctk.CTkFrame(controls, fg_color="transparent")
    row.pack(fill="x", padx=18, pady=(0, 13))
    label(row, "Column alignment", size=12, color=t.MUTED).pack(side="left", padx=(0, 12))
    option(row, ["union", "strict", "intersection"], variable=app.merge_mode_var, width=155).pack(
        side="left", padx=(0, 10)
    )
    app.action(
        row,
        "Merge files",
        app.run_merge,
        primary=True,
        width=140,
        height=36,
        image=icon("merge", color=t.BG, size=16),
        compound="left",
    ).pack(side="left")
    if app.files:
        sets = [set(item.frame.columns) for item in app.files]
        same = all(value == sets[0] for value in sets)
        shared = set.intersection(*sets)
        info = f"{len(app.files)} files   ·   {len(shared)} shared columns   ·   {'Matching column sets' if same else 'Different column sets'}"
    else:
        same, info = False, "Add at least two files to compare their columns."
    label(row, info, size=11, color=t.PRIMARY if same else t.MUTED).pack(side="right")
    label(
        controls,
        "Union keeps all columns. Strict requires matching columns. Intersection keeps shared columns.\nExcel inputs use the active worksheet name.",
        size=11,
        color=t.MUTED,
        justify="left",
    ).pack(anchor="w", padx=18, pady=(0, 15))
    preview = DataPreview(body, "Active source file", height=360)
    preview.grid(row=1, column=0, sticky="nsew")
    preview.show(app.current_frame)


def convert(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(1, weight=1)
    controls = card(body)
    controls.grid(row=0, column=0, sticky="ew", pady=(0, 16))
    row = ctk.CTkFrame(controls, fg_color="transparent")
    row.pack(fill="x", padx=18, pady=16)
    text = ctk.CTkFrame(row, fg_color="transparent")
    text.pack(side="left")
    label(text, "Export in another format", size=15, bold=True).pack(anchor="w")
    label(text, "Use the source table and selected Excel sheet.", size=12, color=t.MUTED).pack(
        anchor="w", pady=(2, 0)
    )
    app.action(
        row,
        "Convert & save",
        app.run_conversion,
        primary=True,
        width=160,
        height=36,
        image=icon("convert", color=t.BG, size=16),
        compound="left",
    ).pack(side="right")
    option(row, ["csv", "xlsx"], variable=app.output_format_var, width=110).pack(
        side="right", padx=(10, 12)
    )
    label(row, "Save as", size=12, color=t.MUTED).pack(side="right", padx=(14, 0))
    preview = DataPreview(body, "Source data", height=400)
    preview.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
    preview.show(app.current_frame)
    label(
        body,
        "CSV encoding and delimiter follow Settings. Excel exports contain table values only.",
        size=11,
        color=t.MUTED,
        anchor="w",
    ).grid(row=2, column=0, sticky="ew")


def history(app, parent):
    body = _body(parent)
    body.grid_rowconfigure(1, weight=1)
    head = ctk.CTkFrame(body, fg_color="transparent")
    head.grid(row=0, column=0, sticky="ew", pady=(0, 14))
    label(head, f"{len(app.history)} events", size=13, bold=True).pack(side="left")
    label(head, "Current session", size=12, color=t.MUTED).pack(side="right")
    listing = ctk.CTkScrollableFrame(
        body,
        fg_color=t.PANEL,
        corner_radius=9,
        border_width=1,
        border_color=t.BORDER,
        scrollbar_button_color=t.SUBTLE,
        scrollbar_button_hover_color=t.MUTED,
    )
    listing.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
    if not app.history:
        label(listing, "No activity yet", size=16, bold=True).pack(
            anchor="w", padx=22, pady=(24, 7)
        )
        label(
            listing, "Imports, workflows and exports will appear here.", size=12, color=t.MUTED
        ).pack(anchor="w", padx=22, pady=(0, 24))
    for event in reversed(app.history):
        row = ctk.CTkFrame(listing, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=15, pady=(0, 1))
        head = ctk.CTkFrame(row, fg_color="transparent")
        head.pack(fill="x", pady=(14, 4))
        is_error = "error" in event["action"].lower()
        label(
            head, event["action"], size=13, bold=True, color=t.ERROR if is_error else t.TEXT
        ).pack(side="left")
        label(head, event["time"], size=11, color=t.MUTED).pack(side="right")
        label(
            row, event["detail"], size=12, color=t.MUTED, wraplength=820, justify="left", anchor="w"
        ).pack(fill="x", pady=(0, 14))
        ctk.CTkFrame(row, height=1, fg_color=t.BORDER, corner_radius=0).pack(fill="x")
    if app.last_batch is not None:
        app.action(
            body,
            "Export batch report",
            lambda: _export_report(app),
            width=180,
            height=34,
            image=icon("download", color=t.MUTED, size=15),
            compound="left",
        ).grid(row=2, column=0, sticky="w")


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
            app.set_status(f"Batch report saved: {path}")
        except Exception as error:
            app.fail(error)


def settings(app, parent):
    body = ctk.CTkScrollableFrame(
        parent,
        fg_color="transparent",
        corner_radius=0,
        scrollbar_button_color=t.SUBTLE,
        scrollbar_button_hover_color=t.MUTED,
    )
    body.grid(row=0, column=0, sticky="nsew")
    _subtitle(body, "Preferences for this workspace session.")
    panel = card(body)
    panel.pack(fill="x", pady=(0, 16))
    row = ctk.CTkFrame(panel, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=18)
    text = ctk.CTkFrame(row, fg_color="transparent")
    text.pack(side="left")
    label(text, "Appearance", size=14, bold=True).pack(anchor="w")
    label(text, "Choose a dark workspace theme.", size=12, color=t.MUTED).pack(
        anchor="w", pady=(3, 0)
    )
    option(
        row, ["Midnight", "Graphite"], variable=app.theme_var, command=app.change_theme, width=170
    ).pack(side="right")
    panel = card(body)
    panel.pack(fill="x", pady=(0, 16))
    label(panel, "Files & export", size=14, bold=True).pack(anchor="w", padx=20, pady=(18, 14))
    label(panel, "Default export folder", size=12, color=t.MUTED).pack(
        anchor="w", padx=20, pady=(0, 7)
    )
    directory = ctk.CTkFrame(panel, fg_color="transparent")
    directory.pack(fill="x", padx=20, pady=(0, 20))
    BoundEntry(
        directory, textvariable=app.output_dir_var, height=35, fg_color=t.BG, border_color=t.BORDER
    ).pack(side="left", fill="x", expand=True, padx=(0, 10))
    app.action(directory, "Browse", app.choose_output_dir, width=90, height=35).pack(side="right")
    fields = ctk.CTkFrame(panel, fg_color="transparent")
    fields.pack(fill="x", padx=20, pady=(0, 4))
    fields.grid_columnconfigure((0, 1), weight=1, uniform="settings")
    options = [
        ("CSV encoding", ["utf-8-sig", "utf-8", "cp1251", "latin-1", "utf-16"], app.encoding_var),
        ("CSV delimiter", [",", ";", "\\t", "|"], app.delimiter_var),
        ("If a filename exists", ["unique", "error"], app.collision_var),
        ("Batch output format", ["csv", "xlsx"], app.output_format_var),
    ]
    for index, (title, values, variable) in enumerate(options):
        field = ctk.CTkFrame(fields, fg_color="transparent")
        field.grid(row=index // 2, column=index % 2, padx=(0, 20), pady=(0, 15), sticky="ew")
        label(field, title, size=12, color=t.MUTED).pack(anchor="w", pady=(0, 6))
        option(field, values, variable=variable, width=220).pack(anchor="w")
    label(
        panel,
        "Unique creates a new filename. Error keeps the existing file and stops the export.",
        size=11,
        color=t.MUTED,
        wraplength=700,
        justify="left",
    ).pack(anchor="w", padx=20, pady=(0, 14))
    app.action(
        panel, "Reload active file with these settings", app.reload_current, width=290, height=34
    ).pack(anchor="w", padx=20, pady=(0, 12))
    label(
        panel,
        "Import settings apply when a file is loaded again. Batch and merge use the active worksheet name for all Excel files.",
        size=11,
        color=t.MUTED,
        wraplength=700,
        justify="left",
    ).pack(anchor="w", padx=20, pady=(0, 18))
    panel = card(body)
    panel.pack(fill="x", pady=(0, 16))
    row = ctk.CTkFrame(panel, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=(18, 12))
    label(row, "Activity logging", size=14, bold=True).pack(side="left")
    option(
        row,
        ["DEBUG", "INFO", "WARNING", "ERROR"],
        variable=app.log_level_var,
        command=lambda value: logging.getLogger("dataflow").setLevel(value),
        width=170,
    ).pack(side="right")
    label(
        panel,
        "Logs contain operation details, never table cells. Activity history lasts for this session.",
        size=12,
        color=t.MUTED,
        wraplength=700,
        justify="left",
    ).pack(anchor="w", padx=20, pady=(0, 10))
    label(
        panel,
        f"Log file: {app.log_path}"
        if app.log_path
        else "The local log is unavailable. Check folder permissions.",
        size=11,
        color=t.SUBTLE,
        wraplength=700,
        justify="left",
    ).pack(anchor="w", padx=20, pady=(0, 18))


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
