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

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DSUComfyCG Manager")
    
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
