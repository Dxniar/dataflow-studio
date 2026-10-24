"""Open the real app with synthetic files ready for a manual demonstration."""

from pathlib import Path

from dataflow.gui.app import DataFlowApp

ROOT = Path(__file__).resolve().parents[1]


def main():
    app = DataFlowApp()
    app.output_dir_var.set(str(ROOT / "examples" / "output"))
    app.after(
        300,
        lambda: app.load_paths(
            [
                ROOT / "examples/input/customers_dirty.csv",
                ROOT / "examples/input/customers_dirty.xlsx",
            ]
        ),
    )
    app.mainloop()


if __name__ == "__main__":
    main()
