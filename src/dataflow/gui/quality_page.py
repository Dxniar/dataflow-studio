"""Readable source-validation controls and rejected-record preview."""

import csv
import json

import customtkinter as ctk

from dataflow.core.errors import DataFlowError
from dataflow.core.quality import ValidationRules
from dataflow.gui import theme as t
from dataflow.gui.components import DataPreview, card, entry, label, option

RULE_FIELDS = {
    "Required column": "required_columns",
    "Nonempty values": "required_values",
    "Unique values": "unique_columns",
    "Allowed values": "allowed_values",
    "Numeric range": "numeric_ranges",
    "Date range": "date_ranges",
}


def _allowed_values(text):
    if not text.strip():
        raise DataFlowError("Enter an allowed-values JSON array or comma-separated values.")
    try:
        if text.lstrip().startswith("["):
            values = json.loads(text)
        else:
            values = []
            for item in next(csv.reader([text], skipinitialspace=True, strict=True)):
                try:
                    value = json.loads(item.strip())
                except ValueError:
                    value = item.strip()
                values.append(value)
    except (ValueError, csv.Error, StopIteration):
        raise DataFlowError(
            "Allowed values must be a JSON array or comma-separated literals."
        ) from None
    return values


def add_validation_rule(rules, kind, column, first="", second="") -> dict:
    """Parse one form row, validate the whole ruleset and return a detached copy."""
    if kind not in RULE_FIELDS or not isinstance(column, str) or not column.strip():
        raise DataFlowError("Choose a rule type and enter a column name.")
    column = column.strip()
    result = ValidationRules.from_dict(rules).to_dict()
    field = RULE_FIELDS[kind]
    if kind in {"Required column", "Nonempty values", "Unique values"}:
        if column not in result[field]:
            result[field].append(column)
    elif kind == "Allowed values":
        result[field][column] = _allowed_values(first)
    else:
        bounds = {}
        for key, text in (("min", first.strip()), ("max", second.strip())):
            if not text:
                continue
            try:
                bounds[key] = json.loads(text) if kind == "Numeric range" else text
            except ValueError:
                raise DataFlowError("Numeric bounds must be finite numbers.") from None
        if not bounds:
            raise DataFlowError("Enter a minimum or maximum bound.")
        result[field][column] = bounds
    return ValidationRules.from_dict(result).to_dict()


def remove_validation_rule(rules, field, column) -> dict:
    result = ValidationRules.from_dict(rules).to_dict()
    if field not in result:
        raise DataFlowError("Choose an existing validation rule.")
    if isinstance(result[field], list):
        result[field] = [value for value in result[field] if value != column]
    else:
        result[field].pop(column, None)
    return ValidationRules.from_dict(result).to_dict()


def _rule_text(kind, column, value):
    text = f"{kind} · {column}"
    if kind == "Allowed values":
        text += "\n" + ", ".join(json.dumps(item, ensure_ascii=False) for item in value)
    elif kind in {"Numeric range", "Date range"}:
        text += "\n" + " · ".join(f"{key}: {bound}" for key, bound in value.items())
    return text if len(text) <= 180 else text[:177] + "…"


def build_quality_page(app, parent):
    """Build from application state; application actions own persistence/rerender."""
    body = ctk.CTkFrame(parent, fg_color="transparent")
    body.grid(row=0, column=0, sticky="nsew")
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(0, weight=1)

    controls = card(body, width=290)
    controls.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
    controls.grid_propagate(False)
    controls.grid_columnconfigure(0, weight=1)
    controls.grid_rowconfigure(0, weight=1)
    builder = ctk.CTkScrollableFrame(
        controls,
        fg_color="transparent",
        width=260,
        scrollbar_button_color=t.BORDER,
    )
    builder.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
    label(builder, "Validation rules", size=15, bold=True).pack(anchor="w", pady=(0, 4))
    label(
        builder,
        "Check source data without changing it.",
        size=11,
        color=t.MUTED,
        wraplength=240,
        justify="left",
    ).pack(anchor="w", pady=(0, 16))

    label(builder, "Rule type", size=11, color=t.MUTED).pack(anchor="w")
    kind_menu = option(builder, list(RULE_FIELDS), width=240)
    kind_menu.pack(fill="x", pady=(4, 10))
    label(builder, "Column name", size=11, color=t.MUTED).pack(anchor="w")
    column_entry = entry(builder, "Column to check", width=240)
    column_entry.pack(fill="x", pady=(4, 8))

    values_form = ctk.CTkFrame(builder, fg_color="transparent")
    first_label = label(values_form, "Values", size=11, color=t.MUTED)
    first_label.pack(anchor="w")
    first_entry = entry(values_form, "A, B, C", width=240)
    first_entry.pack(fill="x", pady=(4, 8))
    second_form = ctk.CTkFrame(values_form, fg_color="transparent")
    label(second_form, "Maximum (optional)", size=11, color=t.MUTED).pack(anchor="w")
    second_entry = entry(second_form, "Maximum", width=240)
    second_entry.pack(fill="x", pady=(4, 8))
    hint = label(values_form, "", size=10, color=t.MUTED, wraplength=240, justify="left")
    hint.pack(anchor="w", pady=(0, 6))

    def select_kind(selected):
        values_form.pack_forget()
        second_form.pack_forget()
        if selected == "Allowed values":
            first_label.configure(text="Allowed values")
            first_entry.configure(placeholder_text='["A", "B"] or A, B')
            hint.configure(text="JSON array or comma-separated literals.")
            values_form.pack(fill="x", before=add_button, pady=(2, 4))
        elif selected in {"Numeric range", "Date range"}:
            first_label.configure(text="Minimum (optional)")
            is_date = selected == "Date range"
            first_entry.configure(placeholder_text="2026-01-01" if is_date else "0")
            second_entry.configure(placeholder_text="2026-12-31" if is_date else "100")
            hint.configure(
                text="Use ISO dates: YYYY-MM-DD."
                if is_date
                else "Bounds are inclusive. Leave one blank if needed."
            )
            second_form.pack(fill="x", before=hint)
            values_form.pack(fill="x", before=add_button, pady=(2, 4))

    def add_rule():
        try:
            result = add_validation_rule(
                app.validation_rules,
                kind_menu.get(),
                column_entry.get(),
                first_entry.get(),
                second_entry.get(),
            )
            app.apply_validation_rules(result)
        except (DataFlowError, ValueError) as error:
            app.fail(error)

    add_button = app.action(builder, "Add rule", add_rule, primary=True, width=240)
    add_button.pack(fill="x", pady=(4, 16))
    kind_menu.configure(command=select_kind)

    saved_header = ctk.CTkFrame(builder, fg_color="transparent")
    saved_header.pack(fill="x", pady=(0, 8))
    label(saved_header, "Active checks", size=12, bold=True).pack(side="left")
    app.action(
        saved_header,
        "Reset",
        lambda: app.apply_validation_rules({}),
        variant="ghost",
        width=52,
        height=28,
    ).pack(side="right")
    rule_count = 0
    for kind, field in RULE_FIELDS.items():
        values = app.validation_rules.get(field, {})
        for column in values:
            rule_count += 1
            row = card(builder, fg_color=t.PANEL)
            row.pack(fill="x", pady=(0, 7))
            row.grid_columnconfigure(0, weight=1)
            value = values[column] if isinstance(values, dict) else None
            label(
                row,
                _rule_text(kind, column, value),
                size=11,
                wraplength=190,
                anchor="w",
                justify="left",
            ).grid(row=0, column=0, sticky="ew", padx=(10, 0), pady=9)

            def remove(field=field, column=column):
                try:
                    app.apply_validation_rules(
                        remove_validation_rule(app.validation_rules, field, column)
                    )
                except DataFlowError as error:
                    app.fail(error)

            app.action(row, "×", remove, variant="ghost", width=30, height=28).grid(
                row=0, column=1, sticky="ne", padx=4, pady=6
            )
    if not rule_count:
        label(
            builder, "No checks yet. Add a rule above.", size=11, color=t.MUTED, wraplength=240
        ).pack(anchor="w", pady=8)

    results = ctk.CTkFrame(body, fg_color="transparent")
    results.grid(row=0, column=1, sticky="nsew")
    results.grid_columnconfigure(0, weight=1)
    results.grid_rowconfigure(3, weight=1)
    report = app.quality_report
    summary = report.summary() if report is not None else {}
    metrics = card(results)
    metrics.grid(row=0, column=0, sticky="ew", pady=(0, 12))
    counts = [
        (
            "Source rows",
            summary.get("rows", len(app.current_frame) if app.current_frame is not None else "—"),
            t.TEXT,
        ),
        ("Valid", summary.get("valid_rows", "—"), t.PRIMARY),
        ("Rejected", summary.get("invalid_rows", "—"), t.WARNING),
        ("Schema errors", len(summary["schema_errors"]) if summary else "—", t.ERROR),
    ]
    for index, (title, count, color) in enumerate(counts):
        metrics.grid_columnconfigure(index, weight=1, uniform="quality_counts")
        metric = ctk.CTkFrame(metrics, fg_color="transparent")
        metric.grid(row=0, column=index, sticky="ew", padx=12, pady=12)
        label(metric, title, size=10, color=t.MUTED).pack(anchor="w")
        label(
            metric,
            f"{count:,}" if isinstance(count, int) else count,
            size=22,
            color=color,
            bold=True,
        ).pack(anchor="w")

    actions = ctk.CTkFrame(results, fg_color="transparent")
    actions.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    app.action(actions, "Check data", app.run_validation, primary=True, width=120).pack(side="left")
    app.action(actions, "Export rejected rows", app.export_problems, width=160).pack(side="right")
    details = "Source validation is read-only. Source record numbers count the header as 1."
    if summary.get("schema_errors"):
        details += "\n" + "\n".join(summary["schema_errors"])
    elif report is None:
        details += "\nChoose checks, then run Check data to see rejected records."
    label(
        results,
        details,
        size=11,
        color=t.WARNING if summary.get("schema_errors") else t.MUTED,
        wraplength=580,
        justify="left",
        anchor="w",
    ).grid(row=2, column=0, sticky="ew", pady=(0, 12))
    preview = DataPreview(
        results, "Rejected source records" if report is not None else "Source preview", height=330
    )
    preview.grid(row=3, column=0, sticky="nsew")
    preview.show(report.problem_rows if report is not None else app.current_frame)
    return body
