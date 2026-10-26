"""Explicit import schema and locale settings, applied before reading records."""

from pathlib import Path

import customtkinter as ctk

from dataflow.core.importing import ImportOptions
from dataflow.core.io import list_sheets, read_columns
from dataflow.gui import theme as t
from dataflow.gui.components import button, entry, label, option

TYPE_LABELS = {
    "Auto": None,
    "Text": "string",
    "Integer": "integer",
    "Decimal": "float",
    "Date": "datetime",
    "Boolean": "boolean",
}


class ImportDialog(ctk.CTkToplevel):
    def __init__(self, app, *, paths=None, path=None):
        super().__init__(app)
        self.app = app
        self.paths = list(paths or [])
        self.path = Path(path) if path else None
        self.title("Import settings")
        self.geometry("850x720")
        self.minsize(720, 500)
        self.configure(fg_color=t.BG)
        self.transient(app)
        self.types = {}
        self.formats = {}
        self.headers_valid = self.path is None
        self._header_signature = None
        self._sheet_index = (
            app.current_file.sheet
            if app.current_file
            and self.path == app.current_file.path
            and type(app.current_file.sheet) is int
            else None
        )
        self.encoding = ctk.StringVar(value=app.encoding_var.get())
        self.delimiter = ctk.StringVar(value=app.delimiter_var.get())
        self.sheet = ctk.StringVar(
            value=str(app.current_file.sheet)
            if app.current_file and self.path == app.current_file.path
            else "0"
        )
        self.decimal = ctk.StringVar(value=app.import_options.get("decimal", "."))
        self.thousands = ctk.StringVar(value=app.import_options.get("thousands") or "None")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        label(self, "Import data safely", size=22, bold=True).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 6)
        )
        label(
            self,
            "Use Text for IDs to keep leading zeroes. Auto uses type inference.",
            size=12,
            color=t.MUTED,
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 14))
        body = ctk.CTkScrollableFrame(self, fg_color=t.PANEL, corner_radius=8)
        body.grid(row=2, column=0, sticky="nsew", padx=20)
        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=12)
        for column in range(3):
            controls.grid_columnconfigure(column, weight=1)
        specs = [
            ("CSV encoding", ["utf-8-sig", "utf-8", "cp1251", "latin-1", "utf-16"], self.encoding),
            ("CSV delimiter", [",", ";", "\\t", "|"], self.delimiter),
            ("Decimal separator", [".", ","], self.decimal),
            ("Thousands separator", ["None", ".", ",", " "], self.thousands),
        ]
        for index, (title, values, variable) in enumerate(specs):
            field = ctk.CTkFrame(controls, fg_color="transparent")
            field.grid(row=index // 3, column=index % 3, sticky="ew", padx=(0, 12), pady=(0, 12))
            label(field, title, size=11, color=t.MUTED).pack(anchor="w", pady=(0, 5))
            option(
                field,
                values,
                variable=variable,
                command=self.refresh_columns
                if title in {"CSV encoding", "CSV delimiter"}
                else None,
                width=185,
            ).pack(fill="x")
        self.sheet_menu = option(
            controls, ["0"], variable=self.sheet, command=self.refresh_columns, width=185
        )
        self.sheet_menu.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(17, 12))
        button(controls, "Refresh columns", self.refresh_columns, width=165).grid(
            row=1, column=2, sticky="ew", padx=(0, 12), pady=(17, 12)
        )
        label(
            body,
            self.path.name if self.path else "Add a file to choose column types.",
            size=13,
            bold=True,
        ).pack(anchor="w", padx=12, pady=(5, 10))
        self.columns_panel = ctk.CTkFrame(body, fg_color="transparent")
        self.columns_panel.pack(fill="x", padx=12)
        label(body, "Safety limits", size=13, bold=True).pack(anchor="w", padx=12, pady=(18, 5))
        label(
            body,
            "Imports that exceed a limit stop with an error. Large files remain in memory.",
            size=11,
            color=t.MUTED,
        ).pack(anchor="w", padx=12)
        limits = ctk.CTkFrame(body, fg_color="transparent")
        limits.pack(fill="x", padx=12, pady=(8, 12))
        self.limits = {}
        for index, (key, title) in enumerate(
            [
                ("max_file_mb", "File size (MB)"),
                ("max_table_mb", "Table memory (MB)"),
                ("max_rows", "Rows"),
                ("max_cells", "Cells"),
            ]
        ):
            field = ctk.CTkFrame(limits, fg_color="transparent")
            field.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 20), pady=(0, 8))
            label(field, title, size=11, color=t.MUTED).pack(anchor="w")
            control = entry(field)
            control.insert(0, str(app.import_options[key]))
            control.pack(fill="x", pady=(3, 0))
            self.limits[key] = control
            limits.grid_columnconfigure(index % 2, weight=1)
        self.error = label(self, "", size=11, color=t.ERROR, wraplength=790, justify="left")
        self.error.grid(row=3, column=0, sticky="ew", padx=24, pady=(7, 0))
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=24, pady=(7, 18))
        button(actions, "Cancel", self.destroy, width=90).pack(side="left")
        button(
            actions,
            "Import files" if self.paths else "Save & reload" if self.path else "Save settings",
            self.apply,
            primary=True,
            width=160,
        ).pack(side="right")
        self.refresh_columns()
        self.after(100, self._focus_dialog)

    def _focus_dialog(self):
        if self.winfo_exists():
            self.lift()
            self.grab_set()

    def _signature(self):
        return (
            self.encoding.get(),
            self.delimiter.get(),
            self.sheet.get(),
            *(item.get() for item in self.limits.values()),
        )

    def refresh_columns(self, *_):
        if self.path is None:
            return
        try:
            discovery = ImportOptions.from_dict(
                {
                    **self.app.import_options,
                    **{key: int(control.get()) for key, control in self.limits.items()},
                }
            )
            if self.path.suffix.lower() == ".xlsx":
                names = list_sheets(self.path, import_options=discovery)
                self.sheet_menu.configure(values=names, state="normal")
                if self._sheet_index is not None and 0 <= self._sheet_index < len(names):
                    self.sheet.set(names[self._sheet_index])
                    self._sheet_index = None
                elif self.sheet.get() not in names:
                    self.sheet.set(names[0])
                selected = self.sheet.get()
            else:
                self.sheet_menu.configure(state="disabled")
                selected = 0
            names = read_columns(
                self.path,
                sheet=selected,
                encoding=self.encoding.get(),
                delimiter="\t" if self.delimiter.get() == "\\t" else self.delimiter.get(),
                import_options=discovery,
            )
            previous = {name: variable.get() for name, variable in self.types.items()}
            formats = {name: control.get() for name, control in self.formats.items()}
            self.types, self.formats = {}, {}
            for child in self.columns_panel.winfo_children():
                child.destroy()
            for name in names:
                row = ctk.CTkFrame(self.columns_panel, fg_color="transparent")
                row.pack(fill="x", pady=(0, 7))
                label(row, name, size=12, width=255, anchor="w").pack(
                    side="left", fill="x", expand=True
                )
                current = next(
                    (
                        title
                        for title, kind in TYPE_LABELS.items()
                        if kind == self.app.import_options["column_types"].get(name)
                    ),
                    "Auto",
                )
                variable = ctk.StringVar(value=previous.get(name, current))
                self.types[name] = variable
                option(row, list(TYPE_LABELS), variable=variable, width=120).pack(
                    side="left", padx=10
                )
                date_format = entry(row, "Date format (ISO default)", width=200)
                date_format.insert(
                    0, formats.get(name, self.app.import_options["date_formats"].get(name, ""))
                )
                date_format.pack(side="right")
                self.formats[name] = date_format
            self.headers_valid = True
            self._header_signature = self._signature()
            self.error.configure(text="")
        except Exception as error:
            self.headers_valid = False
            self.error.configure(text=str(error))

    def apply(self):
        try:
            if self.path is not None and self._header_signature != self._signature():
                self.refresh_columns()
            if not self.headers_valid:
                raise ValueError("Refresh the columns successfully before importing.")
            columns = {
                name: TYPE_LABELS[var.get()]
                for name, var in self.types.items()
                if TYPE_LABELS[var.get()]
            }
            formats = {
                name: control.get().strip()
                for name, control in self.formats.items()
                if columns.get(name) == "datetime" and control.get().strip()
            }
            if self.path is None:
                columns = dict(self.app.import_options["column_types"])
                formats = dict(self.app.import_options["date_formats"])
            data = {
                **self.app.import_options,
                "column_types": columns,
                "date_formats": formats,
                "decimal": self.decimal.get(),
                "thousands": None if self.thousands.get() == "None" else self.thousands.get(),
                **{key: int(control.get()) for key, control in self.limits.items()},
            }
            self.app.import_options = ImportOptions.from_dict(data).to_dict()
            self.app.encoding_var.set(self.encoding.get())
            self.app.delimiter_var.set(self.delimiter.get())
            self.app._persist_workspace()
            app, paths, selected = self.app, self.paths, self.sheet.get()
            self.destroy()
            if paths:
                entries = (
                    [{"path": str(self.path), "sheet": selected}]
                    if self.path.suffix.lower() == ".xlsx"
                    else None
                )
                app.load_paths(paths, restore_entries=entries)
            elif app.current_file:
                if app.current_file.sheets:
                    app._select_sheet(selected)
                else:
                    app.reload_current()
            else:
                app.set_status("Import settings saved. Add files when ready.", success=True)
        except Exception as error:
            if self.winfo_exists():
                self.error.configure(text=str(error))
