"""Build a portable Windows folder with CustomTkinter's bundled assets."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    if os.name != "nt":
        raise SystemExit("Build on Windows; PyInstaller is not a cross-compiler.")
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--name",
            "DataFlowStudio",
            "--collect-all",
            "customtkinter",
            "--hidden-import",
            "openpyxl",
            "--paths",
            str(root / "src"),
            str(root / "scripts" / "launch_gui.py"),
        ],
        cwd=root,
        check=True,
    )


if __name__ == "__main__":
    main()
