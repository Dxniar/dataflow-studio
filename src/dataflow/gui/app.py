"""CustomTkinter desktop shell; business operations are delegated to the core."""

from __future__ import annotations

import gc
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pandas as pd

from dataflow.core.configuration import PipelineConfig
from dataflow.core.errors import DataFlowError
from dataflow.core.importing import ImportOptions
from dataflow.core.io import list_sheets, read_table, write_table
from dataflow.core.jobs import JobCancelled
from dataflow.core.processor import BatchResult, batch_process, merge_files
from dataflow.core.quality import ValidationRules, validate_data
from dataflow.gui import theme as t
from dataflow.gui.components import button, label, option
from dataflow.gui.controller import TaskRunner, run_pipeline, save_workflow, workflow_text
from dataflow.gui.icons import icon
from dataflow.gui.pages import build_page
from dataflow.gui.workspace import CheckpointSaveError, DesktopWorkspace, batch_checkpoint
from dataflow.services.instance import WorkspaceLease
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
        "Data Validation",
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
        self._save_after = None
        self._active_job_id = None
        self.last_batch_job_id = None
        self.quality_report = None
        self.import_options = ImportOptions().to_dict()
        self.validation_rules = ValidationRules().to_dict()
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
        self.workspace = DesktopWorkspace()
        self.history = self.workspace.history
        self.saved_recent_files = self.workspace.state.get("recent_files", [])
        self._restore_preferences()
        try:
            self.log_path = configure_gui_logging()
        except OSError:
            self.log_path = None
        self._status_text = "Ready  ·  Your data stays on your computer"
        self._status_color = t.MUTED
        self._build_shell()
        if self.workspace.warning:
            self.set_status(self.workspace.warning, error=True)
        for variable in self.preference_variables().values():
            variable.trace_add("write", lambda *_: self._schedule_save())
        for variable in self.clean_vars.values():
            variable.trace_add("write", lambda *_: self._schedule_save())
        self.dedupe_var.trace_add("write", lambda *_: self._schedule_save())
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
            "Data Validation": "check",
            "Merge Files": "merge",
            "Convert Files": "convert",
            "Before / After": "compare",
            "History & Logs": "history",
            "Settings": "settings",
        }
        groups = [
            ("WORKSPACE", ["Dashboard", "Before / After", "History & Logs"]),
            (
                "DATA TOOLS",
                [
                    "Data Cleaning",
                    "Transform Data",
                    "Data Validation",
                    "Merge Files",
                    "Convert Files",
                ],
            ),
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
                    height=33,
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
        self.import_button = button(top, "Import settings", self.edit_import_settings, width=125)
        self.import_button.pack(side="right", padx=(0, 8))
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
        self.cancel_button = button(status, "Cancel", self.cancel_job, width=72, height=28)
        self.cancel_button.pack(side="right", padx=(8, 0))
        self.cancel_button.configure(state="disabled")
        self._refresh_file_bar()
        self.show_page(self.page_name)

    def show_page(self, name):
        if name not in self.PAGE_NAMES:
            raise ValueError(f"Unknown page: {name}")
        self.page_name = name
        self.workflow_preview = None
        self._actions = [self.upload_button, self.import_button]
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
            "Data Validation": "Check records and export the rows that need attention.",
            "Merge Files": "Bring compatible tables together.",
            "Convert Files": "Move between CSV and Excel formats.",
            "Before / After": "Review every change before exporting.",
            "History & Logs": "Saved activity, job checkpoints and exported files.",
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
        return datetime.now().isoformat(timespec="seconds")

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
        self.cancel_button.configure(state="normal" if busy else "disabled")

    def _submit(self, name, work, on_success, *, kind=None, payload=None, job_id=None):
        if self.busy:
            return False
        self.last_error = None
        self._persist_workspace()
        self._active_job_id = job_id or self.workspace.create_job(kind or name, payload or {})
        recorded = self.workspace.update_job(self._active_job_id, "running")
        if kind == "batch" and not recorded:
            self._active_job_id = None
            self.fail(
                ValueError(
                    "Cannot start a recoverable batch while the local workspace is unavailable."
                )
            )
            return False
        self._on_success = on_success
        self.runner.submit(name, work)
        self._set_busy(True)
        self.set_status(f"{name}…")
        return True

    def _poll_tasks(self):
        if self._closed:
            return
        events = self.runner.poll_progress()
        if events and self.busy:
            event = events[-1]
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(event.fraction)
            if not self.runner.control.cancelled:
                self.set_status(f"{event.stage}: {event.completed}/{event.total}  {event.message}")
        outcome = self.runner.poll()
        if outcome is not None:
            self._set_busy(False)
            if isinstance(outcome.error, CheckpointSaveError):
                self.workspace.unsafe_jobs.add(self._active_job_id)
                self.workspace.update_job(
                    self._active_job_id, "interrupted", error=str(outcome.error)
                )
                self.fail(outcome.error)
            elif isinstance(outcome.error, JobCancelled):
                self.workspace.update_job(self._active_job_id, "cancelled")
                self.history.append(
                    {"time": self._time(), "action": "Cancelled", "detail": outcome.name}
                )
                self.set_status("Cancelled safely. Previously completed outputs are kept.")
            elif outcome.error:
                self.workspace.update_job(self._active_job_id, "failed", error=str(outcome.error))
                self.fail(outcome.error)
            elif self._on_success:
                try:
                    status = "completed"
                    checkpoint = None
                    if isinstance(outcome.value, BatchResult):
                        checkpoint = outcome.value.to_dict()
                        status = (
                            "cancelled"
                            if outcome.value.cancelled
                            else "failed"
                            if outcome.value.errors
                            else "completed"
                        )
                    self.workspace.update_job(self._active_job_id, status, checkpoint=checkpoint)
                    self._on_success(outcome.value)
                except Exception as error:
                    self.fail(error)
            self._on_success = None
            self._active_job_id = None
            self._persist_workspace()
        self.after(70, self._poll_tasks)

    def _import_options(self):
        delimiter = self.delimiter_var.get()
        return {
            "encoding": self.encoding_var.get(),
            "delimiter": "\t" if delimiter == "\\t" else delimiter,
        }

    def preference_variables(self):
        return {
            "encoding": self.encoding_var,
            "delimiter": self.delimiter_var,
            "output_dir": self.output_dir_var,
            "collision": self.collision_var,
            "output_format": self.output_format_var,
            "merge_mode": self.merge_mode_var,
            "theme": self.theme_var,
            "log_level": self.log_level_var,
        }

    def _restore_preferences(self):
        state = self.workspace.state
        choices = {
            "encoding": {"utf-8-sig", "utf-8", "cp1251", "latin-1", "utf-16"},
            "delimiter": {",", ";", "\\t", "|"},
            "collision": {"unique", "error"},
            "output_format": {"csv", "xlsx"},
            "merge_mode": {"union", "strict", "intersection"},
            "theme": {"Midnight", "Graphite"},
            "log_level": {"DEBUG", "INFO", "WARNING", "ERROR"},
        }
        settings = state.get("settings", {})
        if isinstance(settings, dict):
            for name, variable in self.preference_variables().items():
                value = settings.get(name)
                if isinstance(value, str) and (
                    (name == "output_dir" and value.strip()) or value in choices.get(name, set())
                ):
                    variable.set(value)
        try:
            self.config_data = PipelineConfig.from_dict(state.get("workflow", {})).to_dict()
            self.import_options = ImportOptions.from_dict(state.get("import_options", {})).to_dict()
            self.validation_rules = ValidationRules.from_dict(
                state.get("validation_rules", {})
            ).to_dict()
        except ValueError:
            self.workspace.warning = "Saved configuration needs attention. Defaults were restored; source files are unchanged."
        for key, variable in self.clean_vars.items():
            variable.set(self.config_data.get(key, False))
        self.dedupe_var.set(", ".join(self.config_data.get("deduplicate_by") or []))
        self.saved_recent_files = [
            item
            for item in (
                self.saved_recent_files if isinstance(self.saved_recent_files, list) else []
            )
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and type(item.get("sheet", 0)) in (str, int)
        ][:30]
        self.last_batch_job_id = state.get("last_batch_job_id")
        if not isinstance(self.last_batch_job_id, str):
            self.last_batch_job_id = None
        if self.theme_var.get() == "Graphite":
            t.BG, t.SIDEBAR = "#15171D", "#1D2029"
        else:
            t.BG, t.SIDEBAR = "#0D1219", "#10161F"
        self.configure(fg_color=t.BG)

    def _schedule_save(self):
        if self._save_after is not None:
            self.after_cancel(self._save_after)
        self._save_after = self.after(300, self._persist_workspace)

    def _persist_workspace(self):
        self._save_after = None
        try:
            payload = {
                "settings": {name: var.get() for name, var in self.preference_variables().items()},
                "workflow": self.collect_config(),
                "import_options": self.import_options,
                "validation_rules": self.validation_rules,
                "recent_files": [
                    {"path": str(item.path.resolve()), "sheet": item.sheet} for item in self.files
                ]
                if self.files
                else self.saved_recent_files,
                "last_batch_job_id": self.last_batch_job_id,
            }
            self.workspace.save(payload)
        except (ValueError, OSError):
            # An incomplete edit is not a valid replacement for the last saved workflow.
            logger.warning("Workspace snapshot skipped while configuration is incomplete")

    def restore_workspace(self):
        if self.busy:
            return False
        if not self.saved_recent_files:
            self.set_status("No saved files to restore. Add files to start a workspace.")
            return False
        return self.load_paths(
            [item["path"] for item in self.saved_recent_files],
            restore_entries=self.saved_recent_files,
        )

    def edit_import_settings(self):
        if self.busy:
            return
        from dataflow.gui.import_dialog import ImportDialog

        ImportDialog(self, path=self.current_file.path if self.current_file else None)

    def cancel_job(self):
        if self.runner.cancel():
            self.workspace.update_job(self._active_job_id, "cancel_requested")
            self.cancel_button.configure(state="disabled")
            self.set_status(
                "Cancelling safely after the current step. Completed outputs will be kept."
            )

    def choose_files(self):
        paths = filedialog.askopenfilenames(
            title="Upload CSV or Excel files", filetypes=[("Data files", "*.csv *.xlsx")]
        )
        if paths:
            from dataflow.gui.import_dialog import ImportDialog

            existing = {item.path.resolve(): index for index, item in enumerate(self.files)}
            new_paths = [path for path in paths if Path(path).resolve() not in existing]
            if not new_paths:
                self.select_file(existing[Path(paths[0]).resolve()])
                self.edit_import_settings()
            else:
                ImportDialog(self, paths=new_paths, path=new_paths[0])

    def load_paths(self, paths, *, restore_entries=None):
        """Add files asynchronously; loaded originals are retained for comparison."""
        options = self._import_options()
        existing = {item.path.resolve() for item in self.files}
        unique_paths = []
        for value in paths:
            path = Path(value).resolve()
            if path not in existing:
                existing.add(path)
                unique_paths.append(path)
        paths = unique_paths
        if not paths:
            self.set_status("These files are already in the workspace.")
            return False

        def load():
            loaded, errors = [], []
            restored = {str(Path(item["path"]).resolve()): item for item in (restore_entries or [])}
            for index, path in enumerate(paths):
                self.runner.control.checkpoint()
                try:
                    sheets = (
                        list_sheets(path, import_options=self.import_options)
                        if path.suffix.lower() == ".xlsx"
                        else []
                    )
                    sheet = restored.get(str(path.resolve()), {}).get(
                        "sheet", sheets[0] if sheets else 0
                    )
                    loaded.append(
                        LoadedFile(
                            path,
                            read_table(
                                path,
                                sheet=sheet,
                                import_options=self.import_options,
                                control=self.runner.control,
                                **options,
                            ),
                            sheets,
                            sheet,
                        )
                    )
                except JobCancelled:
                    raise
                except Exception as error:
                    errors.append(f"{path.name}: {error}")
                self.runner.control.report("Loading files", index + 1, len(paths))
            return loaded, errors

        def finish(payload):
            loaded, errors = payload
            if loaded:
                self.selected_index = len(self.files)
                self.files.extend(loaded)
                self.result = None
                self.quality_report = None
                self.saved_recent_files = [
                    {"path": str(item.path.resolve()), "sheet": item.sheet} for item in self.files
                ]
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

        return self._submit(
            "Loading files", load, finish, payload={"paths": [str(path) for path in paths]}
        )

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
        self.quality_report = None
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
            self.quality_report = None
            self._refresh_file_bar()
            self.show_page(self.page_name)
            self.set_status(f"Loaded worksheet {sheet}", success=True)

        self._submit(
            "Reading worksheet",
            lambda: read_table(
                current.path,
                sheet=sheet,
                import_options=self.import_options,
                control=self.runner.control,
                **options,
            ),
            finish,
        )

    def apply_config(self, config_dict):
        self.config_data = PipelineConfig.from_dict(config_dict).to_dict()
        for key, variable in self.clean_vars.items():
            variable.set(self.config_data.get(key, False))
        self.dedupe_var.set(", ".join(self.config_data.get("deduplicate_by") or []))
        self.show_page(self.page_name)
        self._schedule_save()

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
        self.quality_report = None
        self.saved_recent_files = [
            {"path": str(item.path.resolve()), "sheet": item.sheet} for item in self.files
        ]
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
            self.quality_report = None
            self._refresh_file_bar()
            self.show_page(self.page_name)
            self.set_status("Active file reloaded using the current CSV settings.", success=True)

        return self._submit(
            "Reloading active file",
            lambda: read_table(
                current.path,
                sheet=current.sheet,
                import_options=self.import_options,
                control=self.runner.control,
                **options,
            ),
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
            result = run_pipeline(frame, config, control=self.runner.control)
            result.source_paths = [source]
            return result

        return self._submit(
            "Processing selected operations",
            process,
            self._accept_result,
            payload={"source": source, "workflow": config, "import_options": self.import_options},
        )

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
            lambda: merge_files(
                paths,
                mode=mode,
                sheet=sheet,
                import_options=self.import_options,
                control=self.runner.control,
                **options,
            ),
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
                control=self.runner.control,
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
                current.frame,
                path,
                collision=collision,
                source_paths=[current.path],
                control=self.runner.control,
                **options,
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
        payload = {
            "paths": [str(item.path.resolve()) for item in self.files],
            "config": config.to_dict(),
            "output_dir": str(Path(output_dir).resolve()),
            "output_format": self.output_format_var.get(),
            "sheet": self.current_file.sheet,
            "collision": self.collision_var.get(),
            "io_options": self._import_options(),
            "import_options": self.import_options,
        }
        return self._begin_batch(payload)

    def _begin_batch(self, payload, *, job_id=None, resume_from=None):
        if self.busy:
            return False
        try:
            config = PipelineConfig.from_dict(payload["config"])
            imports = ImportOptions.from_dict(payload.get("import_options", {}))
            paths = [Path(path) for path in payload["paths"]]
            output_dir = Path(payload["output_dir"])
            options = dict(payload["io_options"])
            output_format, sheet, collision = (
                payload["output_format"],
                payload["sheet"],
                payload["collision"],
            )
            if resume_from is not None:
                resume_from = BatchResult.from_dict(resume_from)
                if not resume_from.errors and not resume_from.pending:
                    self.set_status("This batch has no failed or unfinished files.", success=True)
                    return False
        except (ValueError, TypeError, KeyError):
            self.fail(
                ValueError(
                    "Saved batch options are invalid. Start a new batch with current settings."
                )
            )
            return False
        initial_checkpoint = (
            resume_from.to_dict()
            if resume_from is not None
            else {
                "successes": [],
                "errors": [],
                "pending": list(dict.fromkeys(str(path) for path in paths)),
                "cancelled": False,
            }
        )
        payload = {**payload, "resume_from": initial_checkpoint}
        job_id = job_id or self.workspace.create_job("batch", payload)
        if not job_id or not self.workspace.update_job(
            job_id, "pending", checkpoint=initial_checkpoint
        ):
            self.fail(
                ValueError(
                    "Cannot save a batch checkpoint. Check local workspace permissions or available disk space."
                )
            )
            return False
        self.last_batch_job_id = job_id
        self.last_batch = None

        def checkpoint(result):
            if not self.workspace.update_job(job_id, "running", checkpoint=result.to_dict()):
                self.workspace.unsafe_jobs.add(job_id)
                raise CheckpointSaveError(
                    "Cannot save the latest checkpoint. Batch stopped; completed outputs are kept. Review existing outputs before recovery."
                )

        def finish(result):
            self.last_batch = result
            self.history.append(
                {
                    "time": self._time(),
                    "action": "Batch cancelled" if result.cancelled else "Batch",
                    "detail": f"{len(result.successes)} succeeded · {len(result.errors)} failed · {len(result.pending)} pending · {output_dir}",
                }
            )
            self.show_page("History & Logs")
            self.set_status(
                f"Batch {'cancelled safely' if result.cancelled else 'complete'}: {len(result.successes)} succeeded, {len(result.errors)} failed, {len(result.pending)} pending.",
                success=not result.errors and not result.cancelled,
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
                import_options=imports,
                control=self.runner.control,
                checkpoint_callback=checkpoint,
                resume_from=resume_from,
                **options,
            ),
            finish,
            kind="batch",
            payload=payload,
            job_id=job_id,
        )

    def retry_batch(self, job_id=None):
        job = self.workspace.get_job(job_id or self.last_batch_job_id)
        if not job or job["kind"] != "batch":
            self.fail(ValueError("No saved batch is available. Run a batch first."))
            return False
        checkpoint = batch_checkpoint(job)
        if checkpoint is None:
            self.fail(
                ValueError(
                    "Saved checkpoint is invalid. Start a new batch; existing outputs are unchanged."
                )
            )
            return False
        if job["status"] == "interrupted" or job["id"] in self.workspace.unsafe_jobs:
            # Publication and SQLite checkpoints are separate transactions. After a
            # hard stop an existing destination is ambiguous, so recovery must not
            # create another numbered output. Persist this policy in a new job.
            payload = {**job["payload"], "collision": "error"}
            return self._begin_batch(payload, resume_from=checkpoint)
        return self._begin_batch(job["payload"], job_id=job["id"], resume_from=checkpoint)

    def apply_validation_rules(self, rules):
        self.validation_rules = ValidationRules.from_dict(rules).to_dict()
        self.quality_report = None
        self._schedule_save()
        self.show_page("Data Validation")

    def run_validation(self):
        if self.current_frame is None:
            self.fail(ValueError("Add a file before checking data."))
            return False
        frame = self.current_frame
        rules = ValidationRules.from_dict(self.validation_rules)

        def finish(report):
            self.quality_report = report
            summary = report.summary()
            self.history.append(
                {
                    "time": self._time(),
                    "action": "Validation",
                    "detail": f"{summary['valid_rows']} valid · {summary['invalid_rows']} rejected · {len(summary['schema_errors'])} schema errors",
                }
            )
            self.show_page("Data Validation")
            self.set_status("Data check complete. Source data is unchanged.", success=True)

        return self._submit(
            "Checking data",
            lambda: validate_data(frame, rules, control=self.runner.control),
            finish,
            payload={"source": str(self.current_file.path), "rules": rules.to_dict()},
        )

    def export_problems(self, path=None):
        if self.quality_report is None:
            self.fail(ValueError("Check data before exporting rejected rows."))
            return False
        path = path or filedialog.asksaveasfilename(
            title="Export rejected rows",
            initialdir=self.output_dir_var.get(),
            initialfile="rejected_rows.csv",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx")],
        )
        if not path:
            return False
        frame = self.quality_report.problem_rows
        options, collision = self._import_options(), self.collision_var.get()
        sources = [item.path for item in self.files]

        def finish(output):
            self.history.append(
                {"time": self._time(), "action": "Validation export", "detail": str(output)}
            )
            self.set_status(f"Rejected rows exported: {output}", success=True)

        return self._submit(
            "Exporting rejected rows",
            lambda: write_table(
                frame,
                path,
                collision=collision,
                source_paths=sources,
                control=self.runner.control,
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
        if self._save_after is not None:
            self.after_cancel(self._save_after)
        self._persist_workspace()
        self._closed = True
        self.destroy()


def main():
    try:
        with WorkspaceLease():
            DataFlowApp().mainloop()
    except DataFlowError as error:
        notification = ctk.CTk()
        notification.withdraw()
        messagebox.showerror("DataFlow Studio", str(error), parent=notification)
        notification.destroy()
