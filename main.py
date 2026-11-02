"""
    Entry point to the application
"""

import sys
from PySide6.QtWidgets import QApplication
from src.ui.ui_main_window import MainWindow


def main() -> None:
    """
        Launches a GUI application
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()