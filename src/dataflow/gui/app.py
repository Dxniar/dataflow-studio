"""CustomTkinter desktop shell; business operations are delegated to the core."""

from __future__ import annotations

import gc
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
import pandas as pd

from dataflow.core.configuration import PipelineConfig
from dataflow.core.io import list_sheets, read_table, write_table
from dataflow.core.processor import batch_process, merge_files
from dataflow.gui import theme as t
from dataflow.gui.components import button, label, option
from dataflow.gui.controller import TaskRunner, run_pipeline, save_workflow, workflow_text
from dataflow.gui.icons import icon
from dataflow.gui.pages import build_page
from dataflow.utils.logging_config import configure_gui_logging

logger = logging.getLogger("dataflow.gui")


@dataclass
class LoadedFile:
    path: Path
    frame: pd.DataFrame
    sheets: list[str]
    sheet: str | int = 0


class DataFlowApp(ctk.CTk):
    """Desktop application with main-thread UI updates and queued background work."""

    PAGE_NAMES = (
        "Dashboard",
        "Data Cleaning",
        "Transform Data",
        "Merge Files",
        "Convert Files",
        "Before / After",
        "History & Logs",
        "Settings",
    )

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        super().__init__()
        self.title("DataFlow Studio — Excel & CSV Automation")
        # Screen dimensions are physical pixels; CTk geometry uses scaled units.
        scale = self._get_window_scaling()
        available_width = int(self.winfo_screenwidth() / scale) - 60
        available_height = int(self.winfo_screenheight() / scale) - 100
        width, height = min(1440, available_width), min(900, available_height)
        self.geometry(f"{width}x{height}")
        self.minsize(min(1100, width), min(720, height))
        self.configure(fg_color=t.BG)
        self.files: list[LoadedFile] = []
        self.selected_index = 0
        self.result = None
        self.last_batch = None
        self.last_export: Path | None = None
        self.last_error: str | None = None
        self.history: list[dict] = []
        self.config_data: dict = {}
        self.runner = TaskRunner()
        self._on_success: Callable | None = None
        self._actions: list = []
        self._closed = False
        self.page_name = "Dashboard"
        self.clean_vars = {
            name: ctk.BooleanVar(value=False)
            for name in (
                "drop_duplicates",
                "drop_empty_rows",
                "trim_whitespace",
                "normalize_columns",
            )
        }
        self.dedupe_var = ctk.StringVar(value="")
        self.dedupe_var.trace_add("write", lambda *_: self.refresh_workflow_preview())
        self.encoding_var = ctk.StringVar(value="utf-8-sig")
        self.delimiter_var = ctk.StringVar(value=",")
        self.output_dir_var = ctk.StringVar(
            value=str(Path.home() / "Documents" / "DataFlow Exports")
        )
        self.collision_var = ctk.StringVar(value="unique")
        self.output_format_var = ctk.StringVar(value="csv")
        self.merge_mode_var = ctk.StringVar(value="union")
        self.theme_var = ctk.StringVar(value="Midnight")
        self.log_level_var = ctk.StringVar(value="INFO")
        try:
            self.log_path = configure_gui_logging()
        except OSError:
            self.log_path = None
        self._status_text = "Ready  ·  Your data stays on your computer"
        self._status_color = t.MUTED
        self._build_shell()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(70, self._poll_tasks)

    @property
    def busy(self):
        return self.runner.busy

    @property
    def current_frame(self):
        return self.files[self.selected_index].frame if self.files else None

    @property
    def current_file(self):
        return self.files[self.selected_index] if self.files else None

    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = ctk.CTkFrame(self, fg_color=t.SIDEBAR, width=202, corner_radius=0, border_width=0)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sidebar.grid_propagate(False)
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(23, 28))
        mark = ctk.CTkLabel(
            brand,
            text="",
            image=icon("brand", t.PRIMARY, 27),
            width=37,
            height=37,
            corner_radius=8,
            fg_color=t.PRIMARY_SOFT,
        )
        mark.pack(side="left", padx=(0, 10))
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left")
        label(brand_text, "DataFlow", size=19, bold=True, height=24).pack(anchor="w")
        label(brand_text, "STUDIO", size=9, color=t.MUTED, height=15).pack(anchor="w")
        self.nav_buttons = {}
        self.nav_icons = {
            "Dashboard": "table",
            "Data Cleaning": "clean",
            "Transform Data": "transform",
            "Merge Files": "merge",
            "Convert Files": "convert",
            "Before / After": "compare",
            "History & Logs": "history",
            "Settings": "settings",
        }
        groups = [
            ("WORKSPACE", ["Dashboard", "Before / After", "History & Logs"]),
            ("DATA TOOLS", ["Data Cleaning", "Transform Data", "Merge Files", "Convert Files"]),
        ]
        for title, names in groups:
            label(sidebar, title, size=9, color=t.SUBTLE, bold=True, height=18).pack(
                anchor="w", padx=23, pady=(4, 8)
            )
            for name in names:
                nav = ctk.CTkButton(
                    sidebar,
                    text=name,
                    anchor="w",
                    image=icon(self.nav_icons[name], t.MUTED),
                    compound="left",
                    height=36,
                    width=178,
                    corner_radius=6,
                    border_spacing=12,
                    fg_color="transparent",
                    hover_color=t.SURFACE_HOVER,
                    text_color=t.MUTED,
                    font=(t.FONT, 12),
                    command=lambda value=name: self.show_page(value),
                )
                nav.pack(padx=12, pady=2)
                self.nav_buttons[name] = nav
            ctk.CTkFrame(sidebar, fg_color="transparent", height=14).pack()
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=12, pady=16)
        nav = ctk.CTkButton(
            footer,
            text="Settings",
            anchor="w",
            image=icon("settings", t.MUTED),
            compound="left",
            height=35,
            width=178,
            corner_radius=6,
            border_spacing=12,
            fg_color="transparent",
            hover_color=t.SURFACE_HOVER,
            text_color=t.MUTED,
            font=(t.FONT, 12),
            command=lambda: self.show_page("Settings"),
        )
        nav.pack(fill="x", pady=(0, 16))
        self.nav_buttons["Settings"] = nav
        ctk.CTkFrame(footer, height=1, fg_color=t.BORDER).pack(fill="x", padx=8, pady=(0, 12))
        label(footer, "●  On-device workspace", size=10, color=t.MUTED, height=20).pack(
            anchor="w", padx=10
        )
        label(footer, "Files stay on your computer", size=9, color=t.SUBTLE, height=18).pack(
            anchor="w", padx=10
        )
        self.content = ctk.CTkFrame(self, fg_color=t.BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=24, pady=(18, 0))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(self.content, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        heading = ctk.CTkFrame(top, fg_color="transparent")
        heading.pack(side="left")
        self.page_title = label(heading, "", size=25, bold=True, height=34)
        self.page_title.pack(anchor="w")
        self.page_hint = label(heading, "", size=11, color=t.MUTED, height=20)
        self.page_hint.pack(anchor="w", pady=(2, 0))
        upload = button(
            top,
            "Add files",
            self.choose_files,
            primary=True,
            width=130,
            image=icon("upload", t.BG, 16),
            compound="left",
        )
        upload.pack(side="right")
        self.upload_button = upload
        self.file_bar = ctk.CTkFrame(
            self.content, fg_color=t.PANEL, corner_radius=7, border_width=1, border_color=t.BORDER
        )
        self.file_bar.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        label(self.file_bar, "", image=icon("file", t.MUTED, 17), width=20).pack(
            side="left", padx=(14, 7), pady=8
        )
        self.file_menu = option(
            self.file_bar, ["No file selected"], command=self._select_label, width=255
        )
        self.file_menu.pack(side="left", padx=0, pady=6)
        ctk.CTkFrame(self.file_bar, fg_color=t.BORDER, width=1, height=22).pack(
            side="left", padx=12
        )
        self.sheet_menu = option(
            self.file_bar, ["CSV / first sheet"], command=self._select_sheet, width=150
        )
        self.sheet_menu.pack(side="left", padx=8)
        self.source_note = label(self.file_bar, "CSV + XLSX", size=11, color=t.MUTED)
        self.source_note.pack(side="right", padx=16)
        self.page = ctk.CTkFrame(self.content, fg_color="transparent")
        self.page.grid(row=2, column=0, sticky="nsew")
        self.page.grid_columnconfigure(0, weight=1)
        self.page.grid_rowconfigure(0, weight=1)
        status = ctk.CTkFrame(self, fg_color=t.BG, height=45, corner_radius=0)
        status.grid(row=1, column=1, sticky="ew", padx=24, pady=(7, 10))
        self.status_label = label(
            status, self._status_text, size=11, color=self._status_color, anchor="w"
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        self.progress = ctk.CTkProgressBar(
            status,
            mode="determinate",
            width=105,
            height=3,
            progress_color=t.PRIMARY,
            fg_color=t.BORDER,
        )
        self.progress.pack(side="right", padx=(12, 0))
        self.progress.set(0)
        self._refresh_file_bar()
        self.show_page(self.page_name)

    def show_page(self, name):
        if name not in self.PAGE_NAMES:
            raise ValueError(f"Unknown page: {name}")
        self.page_name = name
        self.workflow_preview = None
        self._actions = [self.upload_button]
        for widget in self.page.winfo_children():
            widget.destroy()
        # Destroyed Tk controls can retain Python callback cycles. Reclaim their
        # variables here on Tk's thread before a worker happens to trigger GC.
        gc.collect()
        self.page_title.configure(text=name)
        hints = {
            "Dashboard": "Your files and data, in one workspace.",
            "Data Cleaning": "Choose the changes your data needs.",
            "Transform Data": "Shape columns and records with reusable rules.",
            "Merge Files": "Bring compatible tables together.",
            "Convert Files": "Move between CSV and Excel formats.",
            "Before / After": "Review every change before exporting.",
            "History & Logs": "Your session activity and exported files.",
            "Settings": "Make this workspace your own.",
        }
        self.page_hint.configure(text=hints[name])
        self.upload_button.configure(
            fg_color=t.PRIMARY if name == "Dashboard" else t.SURFACE_HOVER,
            text_color=t.BG if name == "Dashboard" else t.TEXT,
            image=icon("upload", t.BG if name == "Dashboard" else t.MUTED, 16),
        )
        for title, nav in self.nav_buttons.items():
            nav.configure(
                fg_color=t.PRIMARY_SOFT if name == title else "transparent",
                text_color=t.TEXT if name == title else t.MUTED,
                image=icon(self.nav_icons[title], t.PRIMARY if name == title else t.MUTED),
            )
        build_page(self, self.page, name)
        self._set_busy(self.busy)

    def action(self, parent, text, callback, *, primary=False, **kwargs):
        widget = button(parent, text, callback, primary=primary, **kwargs)
        self._actions.append(widget)
        return widget

    def set_status(self, message, *, error=False, success=False):
        self._status_text = message
        self._status_color = t.ERROR if error else t.PRIMARY if success else t.MUTED
        self.status_label.configure(text=message, text_color=self._status_color)

    def fail(self, error):
        self.last_error = str(error)
        self.set_status(str(error), error=True)
        self.history.append({"time": self._time(), "action": "Error", "detail": str(error)})
        logger.error("GUI operation failed (%s)", type(error).__name__)

    @staticmethod
    def _time():
        return datetime.now().strftime("%H:%M:%S")

    def _set_busy(self, busy):
        for widget in self._actions:
            if widget.winfo_exists():
                widget.configure(state="disabled" if busy else "normal")
        self.file_menu.configure(state="disabled" if busy or not self.files else "normal")
        self.sheet_menu.configure(
            state="disabled"
            if busy or not self.current_file or not self.current_file.sheets
            else "normal"
        )
        if busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(0)

    def _submit(self, name, work, on_success):
        if self.busy:
            return False
        self.last_error = None
        self._on_success = on_success
        self.runner.submit(name, work)
        self._set_busy(True)
        self.set_status(f"{name}…")
        return True

    def _poll_tasks(self):
        if self._closed:
            return
        outcome = self.runner.poll()
        if outcome is not None:
            self._set_busy(False)
            if outcome.error:
                self.fail(outcome.error)
            elif self._on_success:
                try:
                    self._on_success(outcome.value)
                except Exception as error:
                    self.fail(error)
            self._on_success = None
        self.after(70, self._poll_tasks)

    def _import_options(self):
        delimiter = self.delimiter_var.get()
        return {
            "encoding": self.encoding_var.get(),
            "delimiter": "\t" if delimiter == "\\t" else delimiter,
        }

    def choose_files(self):
        paths = filedialog.askopenfilenames(
            title="Upload CSV or Excel files", filetypes=[("Data files", "*.csv *.xlsx")]
        )
        if paths:
            self.load_paths(paths)

    def load_paths(self, paths):
        """Add files asynchronously; loaded originals are retained for comparison."""
        options = self._import_options()
        existing = {item.path.resolve() for item in self.files}
        paths = [Path(path) for path in paths if Path(path).resolve() not in existing]
        if not paths:
            self.set_status("These files are already in the workspace.")
            return False

        def load():
            loaded, errors = [], []
            for path in paths:
                try:
                    sheets = list_sheets(path) if path.suffix.lower() == ".xlsx" else []
                    sheet = sheets[0] if sheets else 0
                    loaded.append(
                        LoadedFile(path, read_table(path, sheet=sheet, **options), sheets, sheet)
                    )
                except Exception as error:
                    errors.append(f"{path.name}: {error}")
            return loaded, errors

        def finish(payload):
            loaded, errors = payload
            if loaded:
                self.selected_index = len(self.files)
                self.files.extend(loaded)
                self.result = None
                self._refresh_file_bar()
                self.show_page(self.page_name)
                self.history.append(
                    {
                        "time": self._time(),
                        "action": "Import",
                        "detail": f"{len(loaded)} files loaded",
                    }
                )
            if errors:
                self.fail("; ".join(errors))
            else:
                self.set_status(
                    f"Loaded {len(loaded)} file(s). Choose operations to build your workflow.",
                    success=True,
                )

        return self._submit("Loading files", load, finish)

    def _refresh_file_bar(self):
        values = [f"{index + 1}. {item.path.name}" for index, item in enumerate(self.files)]
        self.file_menu.configure(values=values or ["No file selected"])
        self.file_menu.set(values[self.selected_index] if values else "No file selected")
        current = self.current_file
        self.sheet_menu.configure(
            values=current.sheets if current and current.sheets else ["CSV / first sheet"]
        )
        self.sheet_menu.set(
            str(current.sheet) if current and current.sheets else "CSV / first sheet"
        )
        self.source_note.configure(
            text=f"{len(current.frame):,} rows · {len(current.frame.columns)} columns"
            if current
            else "CSV + XLSX"
        )

    def _select_label(self, value):
        self.select_file(int(value.split(".", 1)[0]) - 1)

    def select_file(self, index):
        if self.busy:
            return
        self.selected_index = index
        self.result = None
        self._refresh_file_bar()
        self.show_page(self.page_name)

    def _select_sheet(self, sheet):
        if not self.current_file or not self.current_file.sheets:
            return
        current = self.current_file
        options = self._import_options()

        def finish(frame):
            current.frame, current.sheet = frame, sheet
            self.result = None
            self._refresh_file_bar()
            self.show_page(self.page_name)
            self.set_status(f"Loaded worksheet {sheet}", success=True)

        self._submit(
            "Reading worksheet", lambda: read_table(current.path, sheet=sheet, **options), finish
        )

    def apply_config(self, config_dict):
        self.config_data = PipelineConfig.from_dict(config_dict).to_dict()
        for key, variable in self.clean_vars.items():
            variable.set(self.config_data.get(key, False))
        self.dedupe_var.set(", ".join(self.config_data.get("deduplicate_by") or []))
        self.show_page(self.page_name)

    def collect_config(self):
        config = dict(self.config_data)
        for key, variable in self.clean_vars.items():
            config[key] = variable.get()
        config["deduplicate_by"] = [
            part.strip() for part in self.dedupe_var.get().split(",") if part.strip()
        ] or None
        return PipelineConfig.from_dict(config).to_dict()

    def refresh_workflow_preview(self):
        preview = getattr(self, "workflow_preview", None)
        if preview is None or not preview.winfo_exists():
            return
        try:
            config = self.collect_config()
            if hasattr(preview, "render"):
                preview.render(config)
                return
            content = workflow_text(config)
        except Exception as error:
            if hasattr(preview, "show_error"):
                preview.show_error(str(error))
                return
            content = f"Configuration needs attention:\n{error}"
        preview.configure(state="normal")
        preview.delete("1.0", "end")
        preview.insert("1.0", content)
        preview.configure(state="disabled")

    def remove_file(self, index):
        """Remove a workspace entry without deleting or modifying its source."""
        if self.busy:
            return False
        self.files.pop(index)
        self.selected_index = min(self.selected_index, max(0, len(self.files) - 1))
        self.result = None
        self._refresh_file_bar()
        self.show_page(self.page_name)
        self.set_status("File removed from workspace. The source file is unchanged.")
        return True

    def reload_current(self):
        if self.current_file is None:
            self.fail(ValueError("Upload a file before reloading."))
            return False
        current, options = self.current_file, self._import_options()

        def finish(frame):
            current.frame = frame
            self.result = None
            self._refresh_file_bar()
            self.show_page(self.page_name)
            self.set_status("Active file reloaded using the current CSV settings.", success=True)

        return self._submit(
            "Reloading active file",
            lambda: read_table(current.path, sheet=current.sheet, **options),
            finish,
        )

    def run_processing(self):
        if self.current_frame is None:
            self.fail(ValueError("Upload a file before running a workflow."))
            return False
        try:
            config = self.collect_config()
        except Exception as error:
            self.fail(error)
            return False
        frame, source = self.current_frame, str(self.current_file.path)

        def process():
            result = run_pipeline(frame, config)
            result.source_paths = [source]
            return result

        return self._submit("Processing selected operations", process, self._accept_result)

    def _accept_result(self, result):
        self.result = result
        self.last_export = None
        summary = result.summary()
        self.history.append(
            {
                "time": self._time(),
                "action": "Processing",
                "detail": f"{summary['original_rows']:,} → {summary['processed_rows']:,} rows · "
                f"{result.elapsed_seconds:.3f}s · "
                + ", ".join(result.operations or ["No operations selected"]),
            }
        )
        self.show_page("Before / After")
        self.set_status(
            "Completed successfully. Review the result, then export when ready.", success=True
        )

    def run_merge(self):
        if len(self.files) < 2:
            self.fail(ValueError("Upload at least two files to merge."))
            return False
        paths = [item.path for item in self.files]
        options = self._import_options()
        mode = self.merge_mode_var.get()
        sheet = self.current_file.sheet
        return self._submit(
            "Merging files",
            lambda: merge_files(paths, mode=mode, sheet=sheet, **options),
            self._accept_result,
        )

    def export_result(self, path=None):
        if self.result is None:
            self.fail(ValueError("Run a workflow or merge files before exporting."))
            return False
        if path is None:
            path = filedialog.asksaveasfilename(
                title="Export processed data",
                initialdir=self.output_dir_var.get(),
                initialfile="processed_data.csv",
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx")],
            )
        if not path:
            return False
        result = self.result
        options = self._import_options()
        collision = self.collision_var.get()

        def finish(output):
            self.last_export = output
            self.history.append({"time": self._time(), "action": "Export", "detail": str(output)})
            self.show_page(self.page_name)
            self.set_status(f"Exported successfully: {output}", success=True)

        return self._submit(
            "Exporting result",
            lambda: write_table(
                result.processed,
                path,
                collision=collision,
                source_paths=result.source_paths,
                **options,
            ),
            finish,
        )

    def run_conversion(self, path=None):
        if self.current_frame is None:
            self.fail(ValueError("Upload a file to convert."))
            return False
        output_format = self.output_format_var.get()
        current = self.current_file
        if path is None:
            path = filedialog.asksaveasfilename(
                title="Convert current file",
                initialdir=self.output_dir_var.get(),
                initialfile=f"{current.path.stem}_converted.{output_format}",
                defaultextension=f".{output_format}",
                filetypes=[(output_format.upper(), f"*.{output_format}")],
            )
        if not path:
            return False
        options, collision = self._import_options(), self.collision_var.get()

        def finish(output):
            self.last_export = output
            self.history.append(
                {"time": self._time(), "action": "Conversion", "detail": str(output)}
            )
            self.set_status(f"Converted successfully: {output}", success=True)
            self.show_page(self.page_name)

        return self._submit(
            "Converting file",
            lambda: write_table(
                current.frame, path, collision=collision, source_paths=[current.path], **options
            ),
            finish,
        )

    def run_batch(self, output_dir=None):
        if not self.files:
            self.fail(ValueError("Upload files before running a batch."))
            return False
        try:
            config = PipelineConfig.from_dict(self.collect_config())
        except Exception as error:
            self.fail(error)
            return False
        if output_dir is None:
            output_dir = filedialog.askdirectory(
                title="Choose batch output folder", initialdir=self.output_dir_var.get()
            )
        if not output_dir:
            return False
        paths, options = [item.path for item in self.files], self._import_options()
        output_format, sheet = self.output_format_var.get(), self.current_file.sheet
        collision = self.collision_var.get()

        def finish(result):
            self.last_batch = result
            self.history.append(
                {
                    "time": self._time(),
                    "action": "Batch",
                    "detail": f"{len(result.successes)} succeeded · {len(result.errors)} failed · {output_dir}",
                }
            )
            for item in result.successes:
                self.history.append(
                    {"time": self._time(), "action": "Batch export", "detail": str(item["output"])}
                )
            for item in result.errors:
                self.history.append(
                    {
                        "time": self._time(),
                        "action": "Batch error",
                        "detail": f"{item['input']}: {item['error']}",
                    }
                )
            self.show_page("History & Logs")
            self.set_status(
                f"Batch complete: {len(result.successes)} succeeded, {len(result.errors)} failed.",
                success=not result.errors,
                error=bool(result.errors),
            )

        return self._submit(
            "Processing batch",
            lambda: batch_process(
                paths,
                config,
                output_dir,
                output_format=output_format,
                sheet=sheet,
                collision=collision,
                **options,
            ),
            finish,
        )

    def choose_output_dir(self):
        path = filedialog.askdirectory(
            title="Default export folder", initialdir=self.output_dir_var.get()
        )
        if path:
            self.output_dir_var.set(path)

    def load_config(self, path=None):
        path = path or filedialog.askopenfilename(
            title="Load workflow configuration", filetypes=[("JSON workflow", "*.json")]
        )
        if path:
            try:
                self.apply_config(PipelineConfig.from_json(path).to_dict())
                self.set_status(f"Loaded workflow: {Path(path).name}", success=True)
            except Exception as error:
                self.fail(error)

    def save_config(self, path=None):
        path = path or filedialog.asksaveasfilename(
            title="Save workflow configuration",
            defaultextension=".json",
            filetypes=[("JSON workflow", "*.json")],
        )
        if path:
            try:
                save_workflow(self.collect_config(), path)
                self.set_status(f"Saved workflow: {path}", success=True)
            except Exception as error:
                self.fail(error)

    def change_theme(self, value):
        t.BG = "#0D1219" if value == "Midnight" else "#15171D"
        t.SIDEBAR = "#10161F" if value == "Midnight" else "#1D2029"
        self.configure(fg_color=t.BG)
        for widget in self.winfo_children():
            widget.destroy()
        self._build_shell()

    def _close(self):
        # Tk is only destroyed on its owning thread; background work owns no widgets.
        if self.busy:
            self.set_status("An operation is running. Wait for it to finish before closing.")
            return
        self._closed = True
        self.destroy()


def main():
    DataFlowApp().mainloop()
