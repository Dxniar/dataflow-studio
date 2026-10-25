"""Reusable preview, cards, and form components."""

import json
from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk

from dataflow.gui import theme as t
from dataflow.gui.controller import preview_data
from dataflow.gui.icons import icon


class BoundEntry(ctk.CTkEntry):
    """Release the StringVar trace that CustomTkinter 5.2 leaves after destruction."""

    def destroy(self):
        if self._textvariable_callback_name and self._textvariable is not None:
            self._textvariable.trace_remove("write", self._textvariable_callback_name)
            self._textvariable_callback_name = ""
        super().destroy()


def label(parent, text, *, size=14, color=t.TEXT, bold=False, **kwargs):
    return ctk.CTkLabel(
        parent,
        text=text,
        text_color=color,
        font=(t.FONT, size, "bold" if bold else "normal"),
        **kwargs,
    )


def button(parent, text, command, *, primary=False, variant="secondary", **kwargs):
    height = kwargs.pop("height", 36)
    ghost = variant == "ghost"
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        height=height,
        corner_radius=6,
        font=(t.FONT, 12, "bold" if primary else "normal"),
        fg_color=t.PRIMARY if primary else "transparent" if ghost else t.SURFACE_HOVER,
        hover_color=t.PRIMARY_HOVER if primary else t.SURFACE_HOVER,
        text_color=t.BG if primary else t.TEXT,
        border_width=0 if primary or ghost else 1,
        border_color=t.BORDER,
        **kwargs,
    )


def card(parent, **kwargs):
    defaults = {
        "fg_color": t.SURFACE,
        "corner_radius": 9,
        "border_width": 1,
        "border_color": t.BORDER,
    }
    defaults.update(kwargs)
    return ctk.CTkFrame(parent, **defaults)


class MetricCard(ctk.CTkFrame):
    def __init__(self, parent, title, value="—", accent=t.TEXT):
        super().__init__(parent, fg_color="transparent", corner_radius=7)
        label(self, title, size=11, color=t.MUTED, height=18).pack(
            anchor="w",
            padx=16,
            pady=(8, 0),
        )
        self.value = label(self, value, size=22, bold=True, color=accent, height=28)
        self.value.pack(anchor="w", padx=16, pady=(0, 7))

    def set(self, value):
        self.value.configure(text=str(value))


class DataPreview(ctk.CTkFrame):
    """Scrollable table capped at 100 records, with total/missing counts."""

    def __init__(self, parent, title="Data preview", height=230):
        super().__init__(
            parent, fg_color=t.PANEL, corner_radius=9, border_color=t.BORDER, border_width=1
        )
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=8)
        label(
            header,
            title,
            size=13,
            bold=True,
            height=22,
            image=icon("table", t.MUTED, 16),
            compound="left",
            padx=5,
        ).pack(side="left")
        self.meta = label(
            header, "Upload a CSV or XLSX file to begin", size=11, color=t.MUTED, height=22
        )
        self.meta.pack(side="right")
        style = ttk.Style()
        style.theme_use("clam")
        style.layout("DataFlow.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "DataFlow.Treeview",
            background=t.PANEL,
            foreground=t.TEXT,
            fieldbackground=t.PANEL,
            borderwidth=0,
            relief="flat",
            rowheight=33,
            font=(t.FONT, 11),
        )
        style.configure(
            "DataFlow.Treeview.Heading",
            background=t.SURFACE,
            foreground=t.MUTED,
            relief="flat",
            font=(t.FONT, 10, "bold"),
            borderwidth=0,
            padding=(10, 10),
        )
        style.map(
            "DataFlow.Treeview",
            background=[("selected", "#214337")],
            foreground=[("selected", t.TEXT)],
        )
        style.map("DataFlow.Treeview.Heading", background=[("active", t.SURFACE_HOVER)])
        self.table = ttk.Treeview(
            self, style="DataFlow.Treeview", show="tree headings", selectmode="browse"
        )
        self.table.heading("#0", text="#", anchor="center")
        self.table.column("#0", width=44, minwidth=44, stretch=False, anchor="center")
        self.table.grid(row=1, column=0, sticky="nsew", padx=(1, 0))
        vertical = ctk.CTkScrollbar(
            self,
            orientation="vertical",
            command=self.table.yview,
            width=13,
            fg_color=t.PANEL,
            button_color=t.SUBTLE,
            button_hover_color=t.MUTED,
        )
        vertical.grid(row=1, column=1, sticky="ns", padx=(0, 3))
        horizontal = ctk.CTkScrollbar(
            self,
            orientation="horizontal",
            command=self.table.xview,
            height=13,
            fg_color=t.PANEL,
            button_color=t.SUBTLE,
            button_hover_color=t.MUTED,
        )
        horizontal.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 4))
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.tag_configure("alternate", background="#141E2A")
        self.table.tag_configure("missing", foreground=t.WARNING)
        self.table.tag_configure("row", foreground=t.TEXT)
        self.empty_state = ctk.CTkFrame(self, fg_color=t.PANEL, corner_radius=0)
        label(self.empty_state, "", image=icon("table", t.SUBTLE, 32), height=45).pack()
        label(self.empty_state, "Your data will appear here", size=14, bold=True).pack(pady=(5, 3))
        label(
            self.empty_state, "Add a CSV or Excel file to get started.", size=12, color=t.MUTED
        ).pack()
        self.configure(height=height)
        self.grid_propagate(False)

    def show(self, frame):
        self.table.delete(*self.table.get_children())
        if frame is None:
            self.table.configure(columns=[], show="headings")
            self.meta.configure(text="No data loaded")
            self.empty_state.place(relx=0.5, rely=0.54, anchor="center")
            return
        self.empty_state.place_forget()
        self.table.configure(show="tree headings")
        preview = preview_data(frame)
        identifiers = [f"column_{index}" for index in range(len(preview["columns"]))]
        self.table.configure(columns=identifiers)
        font = tkfont.Font(font=(t.FONT, 11))
        for index, (identifier, name) in enumerate(
            zip(identifiers, preview["columns"], strict=True)
        ):
            self.table.heading(identifier, text=name, anchor="w")
            sample = [str(row[index]) for row in preview["rows"][:30]]
            width = max(font.measure(name), *(font.measure(value) for value in sample), 70) + 28
            self.table.column(
                identifier, width=min(290, width), minwidth=80, anchor="w", stretch=True
            )
        for index, row in enumerate(preview["rows"]):
            tags = ("alternate",) if index % 2 else ()
            self.table.insert("", "end", text=str(index + 1), values=row, tags=tags)
        self.meta.configure(
            text=f"{len(preview['rows']):,} / {preview['total_rows']:,} rows  ·  {preview['missing']:,} missing",
            text_color=t.WARNING if preview["missing"] else t.MUTED,
        )


def entry(parent, placeholder="", width=180):
    return BoundEntry(
        parent,
        placeholder_text=placeholder,
        width=width,
        height=35,
        corner_radius=6,
        border_width=1,
        fg_color=t.BG,
        border_color=t.BORDER,
        text_color=t.TEXT,
        font=(t.FONT, 12),
    )


def option(parent, values, *, variable=None, command=None, width=180):
    return ctk.CTkOptionMenu(
        parent,
        values=values,
        variable=variable,
        command=command,
        width=width,
        height=35,
        corner_radius=6,
        fg_color=t.PANEL,
        button_color=t.PANEL,
        button_hover_color=t.SURFACE_HOVER,
        text_color=t.TEXT,
        font=(t.FONT, 12),
        dropdown_font=(t.FONT, 12),
        dropdown_fg_color=t.SURFACE,
        dropdown_hover_color=t.SURFACE_HOVER,
        dropdown_text_color=t.TEXT,
    )


class WorkflowCard(ctk.CTkFrame):
    """Readable operation summary with an optional JSON inspection window."""

    NAMES = {
        "trim_whitespace": "Trim whitespace",
        "drop_empty_rows": "Remove empty rows",
        "normalize_columns": "Normalize column names",
        "standardize_values": "Standardize values",
        "fill_missing": "Fill missing values",
        "convert_types": "Convert data types",
        "drop_duplicates": "Remove duplicates",
        "rename_columns": "Rename columns",
        "drop_columns": "Drop columns",
        "select_columns": "Select columns",
        "reorder_columns": "Reorder columns",
        "filters": "Filter rows",
        "sort_by": "Sort rows",
    }

    def __init__(self, parent, *, on_reset=None, height=120):
        super().__init__(
            parent, fg_color=t.SURFACE, corner_radius=9, border_width=1, border_color=t.BORDER
        )
        self.config_data = {}
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 4))
        self.title = label(top, "Workflow · 0 steps", size=12, bold=True)
        self.title.pack(side="left")
        button(top, "View JSON", self._show_json, variant="ghost", width=75, height=28).pack(
            side="right"
        )
        if on_reset:
            button(top, "Reset", on_reset, variant="ghost", width=52, height=28).pack(side="right")
        self.summary = ctk.CTkTextbox(
            self,
            height=min(height, 90),
            fg_color="transparent",
            text_color=t.MUTED,
            font=(t.FONT, 12),
            wrap="word",
            border_width=0,
            scrollbar_button_color=t.BORDER,
        )
        self.summary.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        self.render({})

    def render(self, config):
        self.config_data = dict(config)
        active = [(key, config[key]) for key in self.NAMES if config.get(key)]
        rows = []
        for key, value in active:
            detail = ""
            if key == "drop_duplicates" and config.get("deduplicate_by"):
                detail = " · " + ", ".join(config["deduplicate_by"])
            elif isinstance(value, (dict, list)):
                unit = "rule" if key == "filters" else "column"
                detail = f" · {len(value)} {unit}{'' if len(value) == 1 else 's'}"
            rows.append(f"✓  {self.NAMES[key]}{detail}")
        self.title.configure(
            text=f"Workflow  ·  {len(active)} {'step' if len(active) == 1 else 'steps'}"
        )
        self.summary.configure(state="normal", text_color=t.MUTED)
        self.summary.delete("1.0", "end")
        self.summary.insert(
            "1.0",
            "    ·    ".join(rows)
            if rows
            else "Choose operations to build your workflow. Changes appear here before you run.",
        )
        self.summary.configure(state="disabled")

    def show_error(self, message):
        self.title.configure(text="Workflow needs attention")
        self.summary.configure(state="normal", text_color=t.ERROR)
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", message)
        self.summary.configure(state="disabled")

    def _show_json(self):
        window = ctk.CTkToplevel(self)
        window.title("Workflow configuration")
        window.geometry("640x520")
        window.transient(self.winfo_toplevel())
        window.configure(fg_color=t.BG)
        label(window, "Workflow configuration", size=18, bold=True).pack(
            anchor="w", padx=22, pady=(18, 12)
        )
        text = ctk.CTkTextbox(
            window, fg_color=t.PANEL, text_color=t.TEXT, font=("Consolas", 12), corner_radius=8
        )
        text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        text.insert("1.0", json.dumps(self.config_data, indent=2, ensure_ascii=False))
        text.configure(state="disabled")
