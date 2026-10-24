"""Reusable preview, cards, and form components."""

from tkinter import ttk

import customtkinter as ctk

from dataflow.gui import theme as t
from dataflow.gui.controller import preview_data


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


def button(parent, text, command, *, primary=False, **kwargs):
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        height=38,
        corner_radius=8,
        font=(t.FONT, 13, "bold"),
        fg_color=t.PRIMARY if primary else t.SURFACE,
        hover_color=t.PRIMARY_HOVER if primary else t.SURFACE_HOVER,
        text_color=t.BG if primary else t.TEXT,
        **kwargs,
    )


def card(parent, **kwargs):
    return ctk.CTkFrame(parent, fg_color=t.SURFACE, corner_radius=12, **kwargs)


class MetricCard(ctk.CTkFrame):
    def __init__(self, parent, title, value="—", accent=t.TEXT):
        super().__init__(parent, fg_color=t.SURFACE, corner_radius=12)
        label(self, title.upper(), size=11, color=t.MUTED).pack(
            anchor="w",
            padx=18,
            pady=(14, 0),
        )
        self.value = label(self, value, size=29, bold=True, color=accent)
        self.value.pack(anchor="w", padx=18, pady=(2, 14))

    def set(self, value):
        self.value.configure(text=str(value))


class DataPreview(ctk.CTkFrame):
    """Scrollable table capped at 100 records, with total/missing counts."""

    def __init__(self, parent, title="Data preview", height=230):
        super().__init__(parent, fg_color=t.SURFACE, corner_radius=12)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=10)
        label(header, title, size=14, bold=True).pack(side="left")
        self.meta = label(header, "Upload a CSV or XLSX file to begin", size=11, color=t.MUTED)
        self.meta.pack(side="right")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "DataFlow.Treeview",
            background=t.SURFACE,
            foreground=t.TEXT,
            fieldbackground=t.SURFACE,
            borderwidth=0,
            rowheight=29,
            font=(t.FONT, 10),
        )
        style.configure(
            "DataFlow.Treeview.Heading",
            background=t.SIDEBAR,
            foreground=t.MUTED,
            relief="flat",
            font=(t.FONT, 10, "bold"),
            padding=(6, 8),
        )
        style.map("DataFlow.Treeview", background=[("selected", "#1D4F4B")])
        self.table = ttk.Treeview(self, style="DataFlow.Treeview", show="headings")
        self.table.grid(row=1, column=0, sticky="nsew", padx=(10, 0))
        vertical = ttk.Scrollbar(self, orient="vertical", command=self.table.yview)
        vertical.grid(row=1, column=1, sticky="ns", padx=(0, 10))
        horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.tag_configure("alternate", background="#223047")
        self.table.tag_configure("missing", foreground="#FBBF24")
        self.configure(height=height)
        self.grid_propagate(False)

    def show(self, frame):
        self.table.delete(*self.table.get_children())
        if frame is None:
            self.table.configure(columns=[])
            self.meta.configure(text="No data loaded")
            return
        preview = preview_data(frame)
        identifiers = [f"column_{index}" for index in range(len(preview["columns"]))]
        self.table.configure(columns=identifiers)
        for identifier, name in zip(identifiers, preview["columns"], strict=True):
            self.table.heading(identifier, text=name, anchor="w")
            self.table.column(identifier, width=max(120, min(210, len(name) * 9 + 25)), anchor="w")
        for index, row in enumerate(preview["rows"]):
            tags = ("alternate",) if index % 2 else ()
            self.table.insert("", "end", values=row, tags=tags)
        self.meta.configure(
            text=f"{len(preview['rows']):,} of {preview['total_rows']:,} rows  ·  "
            f"{preview['missing']:,} missing",
        )


def entry(parent, placeholder="", width=180):
    return BoundEntry(
        parent,
        placeholder_text=placeholder,
        width=width,
        height=36,
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
        height=36,
        fg_color=t.BG,
        button_color=t.BORDER,
        button_hover_color=t.SURFACE_HOVER,
        text_color=t.TEXT,
        font=(t.FONT, 12),
        dropdown_font=(t.FONT, 12),
    )
