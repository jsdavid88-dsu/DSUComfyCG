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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DSUComfyCG Manager")
    
    window = ManagerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
