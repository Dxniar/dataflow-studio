"""Launch the desktop application with ``python -m dataflow``."""


def main() -> None:
    from dataflow.gui.app import main as launch_gui

    launch_gui()


if __name__ == "__main__":
    main()
