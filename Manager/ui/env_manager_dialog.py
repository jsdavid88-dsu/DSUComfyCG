import os
import re
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QMessageBox, QComboBox, QInputDialog, QAbstractItemView,
    QWidget, QMenu
)
from PySide6.QtCore import Qt
from core.checker import ENVIRONMENTS, ACTIVE_ENV_ID, add_environment, remove_environment, update_environment_memo, BASE_DIR

class EnvManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Environment Manager")
        self.resize(950, 500)
        self.setStyleSheet("""
            QDialog { background-color: #f3f4f6; color: #1e293b; font-family: 'Inter', 'Segoe UI', Arial, sans-serif; }
            QLabel { font-size: 15px; font-weight: bold; color: #0f172a; }
            QTableWidget {
                background-color: #ffffff;
                color: #334155;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: transparent;
                font-size: 13px;
                outline: none;
            }
            QTableWidget::item { padding: 4px 16px; border-bottom: 1px solid #f1f5f9; }
            QTableWidget::item:selected { background-color: #f0fdfa; color: #0f172a; }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #64748b;
                padding: 12px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                font-weight: bold;
                text-align: left;
            }
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                padding: 8px 16px;
                border-radius: 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #f1f5f9; }
            QPushButton#primary { background-color: #10b981; color: white; border: none; }
            QPushButton#primary:hover { background-color: #059669; }
            QPushButton#danger { background-color: #ef4444; color: white; border: none; }
            QPushButton#danger:hover { background-color: #dc2626; }
            QLineEdit, QComboBox {
                background-color: #ffffff; color: #1e293b; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px; font-size: 13px;
            }
        """)
        
        self.layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Manage ComfyUI Instances"))
        header_layout.addStretch()
        
        add_btn = QPushButton("➕ Add New Environment")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_environment)
        header_layout.addWidget(add_btn)
        self.layout.addLayout(header_layout)
        
        # Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Type", "Path", "Memo", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 300)
        self.table.verticalHeader().setDefaultSectionSize(56)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.itemChanged.connect(self._on_item_changed)
        self.layout.addWidget(self.table)
        
        # Bottom controls
        bottom_layout = QHBoxLayout()
        
        del_btn = QPushButton("🗑️ Remove Selected")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._remove_selected)
        bottom_layout.addWidget(del_btn)
        
        bottom_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)
        
        self.layout.addLayout(bottom_layout)
        
        self.refresh_table()

    def refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        
        for env_id, edata in ENVIRONMENTS.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            id_item = QTableWidgetItem(env_id)
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, id_item)
            
            name_item = QTableWidgetItem(edata.get("name", ""))
            self.table.setItem(row, 1, name_item)
            
            type_item = QTableWidgetItem(edata.get("type", ""))
            self.table.setItem(row, 2, type_item)
            
            path_item = QTableWidgetItem(edata.get("path", ""))
            path_item.setFlags(path_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 3, path_item)
            
            memo_item = QTableWidgetItem(edata.get("memo", ""))
            self.table.setItem(row, 4, memo_item)
            
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 4, 4, 4)
            action_layout.setSpacing(6)
            
            base_style = """
                QPushButton { background-color: transparent; color: #475569; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 12px; }
                QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            """
            
            # 1. Install Action
            install_btn = QPushButton()
            if os.path.exists(os.path.join(edata.get("path", ""), "main.py")):
                install_btn.setText("Installed")
                install_btn.setEnabled(False)
                install_btn.setStyleSheet("QPushButton { background-color: transparent; color: #94a3b8; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 12px; }")
            else:
                install_btn.setText("Install")
                install_btn.setStyleSheet("""
                    QPushButton { background-color: #f0fdfa; color: #0d9488; border: 1px solid #5eead4; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 12px; }
                    QPushButton:hover { background-color: #ccfbf1; }
                """)
                install_btn.clicked.connect(lambda _, eid=env_id: self._install_env(eid))
            
            # 2. Open Folder
            open_btn = QPushButton("Open")
            open_btn.setStyleSheet(base_style)
            open_btn.clicked.connect(lambda _, p=edata.get("path", ""): self._open_folder(p))
            
            # 3. Duplicate
            dup_btn = QPushButton("Copy")
            dup_btn.setStyleSheet(base_style)
            dup_btn.clicked.connect(lambda _, eid=env_id: self._duplicate_env_action(eid))
            
            # 4. Delete
            del_btn = QPushButton("Delete")
            del_btn.setStyleSheet("""
                QPushButton { background-color: transparent; color: #ef4444; border: 1px solid #fca5a5; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 12px; }
                QPushButton:hover { background-color: #fef2f2; }
            """)
            del_btn.clicked.connect(lambda _, eid=env_id: self._delete_env_inline(eid))
            
            action_layout.addWidget(install_btn)
            action_layout.addWidget(open_btn)
            action_layout.addWidget(dup_btn)
            action_layout.addWidget(del_btn)
            action_layout.addStretch()
            
            empty_item = QTableWidgetItem()
            empty_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 5, empty_item)
            self.table.setCellWidget(row, 5, action_widget)
            self.table.setRowHeight(row, 56)
            
        self.table.blockSignals(False)

    def _install_env(self, target_env_id):
        from core.checker import set_active_env, install_comfyui
        import core.checker
        original_env_id = core.checker.ACTIVE_ENV_ID
        
        reply = QMessageBox.question(
            self, "Install ComfyUI",
            f"Install ComfyUI into environment '{target_env_id}'?\n\nThis will clone the repository. Git must be installed.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            set_active_env(target_env_id)
            # Temporarily disable this window so user can't click things
            self.setEnabled(False)
            success, msg = install_comfyui()
            set_active_env(original_env_id)
            self.setEnabled(True)
            
            if success:
                QMessageBox.information(self, "Success", "ComfyUI Installed successfully!")
                self.refresh_table()
            else:
                QMessageBox.warning(self, "Failed", msg)

    def _open_folder(self, path):
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Not Found", f"Directory does not exist yet:\n{path}")
            return
        import sys
        import subprocess
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open folder: {str(e)}")

    def _delete_env_inline(self, env_id):
        if env_id == "env_default":
            QMessageBox.warning(self, "Deny", "Cannot remove the default environment.")
            return
            
        from core.checker import remove_environment
        btn = QMessageBox.question(self, "Confirm", f"Remove environment '{env_id}'?\nNote: This will not delete the folder on disk.", QMessageBox.Yes | QMessageBox.No)
        if btn == QMessageBox.Yes:
            success, msg = remove_environment(env_id)
            if success:
                self.refresh_table()
            else:
                QMessageBox.warning(self, "Error", msg)

    def _duplicate_env_action(self, env_id):
        from core.checker import duplicate_environment
        success, msg = duplicate_environment(env_id)
        if success:
            QMessageBox.information(self, "Duplicated", msg)
            self.refresh_table()
        else:
            QMessageBox.warning(self, "Failed", msg)

    def _on_item_changed(self, item):
        column_map = {1: "name", 2: "type", 4: "memo"}
        if item.column() in column_map:
            env_id = self.table.item(item.row(), 0).text()
            new_val = item.text().strip()
            from core.checker import update_environment_field
            update_environment_field(env_id, column_map[item.column()], new_val)

    def _add_environment(self):
        # Dialog for Name, Type
        import string
        import random
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        
        dlg = QDialog(self)
        dlg.setWindowTitle("New Environment")
        fl = QFormLayout(dlg)
        
        name_input = QLineEdit()
        fl.addRow("Environment Name:", name_input)
        
        type_combo = QComboBox()
        type_combo.addItems(["sandbox", "production"])
        fl.addRow("Type:", type_combo)
        
        memo_input = QLineEdit()
        fl.addRow("Memo:", memo_input)
        
        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bbox.accepted.connect(dlg.accept)
        bbox.rejected.connect(dlg.reject)
        fl.addRow(bbox)
        
        if dlg.exec():
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "Error", "Name cannot be empty.")
                return
                
            env_type = type_combo.currentText()
            memo = memo_input.text()
            
            # Generate safe ID and path
            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
            env_id = f"env_{safe_name.lower()}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=4))}"
            
            path = os.path.join(BASE_DIR, "envs", safe_name).replace("\\", "/")
            
            success, msg = add_environment(env_id, name, env_type, path, memo)
            if success:
                self.refresh_table()
            else:
                QMessageBox.warning(self, "Error", msg)

    def _remove_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
            
        env_id = self.table.item(row, 0).text()
        if env_id == "env_default":
            QMessageBox.warning(self, "Deny", "Cannot remove the default environment.")
            return
            
        btn = QMessageBox.question(self, "Confirm", f"Remove environment {env_id} from registry?\nNote: This will not delete the folder on disk.", QMessageBox.Yes | QMessageBox.No)
        if btn == QMessageBox.Yes:
            success, msg = remove_environment(env_id)
            if success:
                self.refresh_table()
            else:
                QMessageBox.warning(self, "Error", msg)
