"""
DSUComfyCG Manager - Entry Point
"""

import sys
import os

# Add paths
MANAGER_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MANAGER_DIR)

from PySide6.QtWidgets import QApplication
from ui.manager_window import ManagerWindow
from core.checker import ENVIRONMENTS
from ui.env_manager_dialog import EnvManagerDialog

POPUP_STYLE = """
QMessageBox, QInputDialog, QFileDialog {
    background-color: #ffffff;
    color: #1e293b;
}
QMessageBox QLabel, QInputDialog QLabel, QFileDialog QLabel {
    color: #1e293b;
    font-size: 13px;
    background: transparent;
}
QMessageBox QPushButton, QInputDialog QPushButton, QFileDialog QPushButton {
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    padding: 6px 18px;
    border-radius: 8px;
    min-width: 80px;
    font-weight: bold;
}
QMessageBox QPushButton:hover, QInputDialog QPushButton:hover, QFileDialog QPushButton:hover {
    background-color: #f1f5f9;
}
QMessageBox QPushButton:default, QInputDialog QPushButton:default {
    background-color: #10b981;
    color: #ffffff;
    border: none;
}
QMessageBox QPushButton:default:hover, QInputDialog QPushButton:default:hover {
    background-color: #059669;
}
QInputDialog QLineEdit, QInputDialog QTextEdit {
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    padding: 6px;
    border-radius: 6px;
}
QToolTip {
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #334155;
    padding: 4px 8px;
    border-radius: 4px;
}
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DSUComfyCG Manager")
    app.setStyleSheet(POPUP_STYLE)

    window = ManagerWindow()
    window.show()
    
    # Auto-open Environment Manager if no environments are installed yet
    if not ENVIRONMENTS:
        env_dialog = EnvManagerDialog(window)
        env_dialog.exec()
        
        # After closing, ensure the active environment relies on the newly created one (if any)
        window._on_env_changed(window.env_combo.currentIndex())
        window.update_system_status()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
