import os
import re
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QMessageBox, QComboBox, QInputDialog, QAbstractItemView,
    QWidget, QMenu, QTextEdit
)
from PySide6.QtCore import Qt
from core.checker import ENVIRONMENTS, ACTIVE_ENV_ID, add_environment, remove_environment, BASE_DIR

def _resolve_env_path(path):
    """Resolve environment relative path against BASE_DIR."""
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)

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
            
            # 1. Install or Update Action
            install_btn = QPushButton()
            if os.path.exists(os.path.join(_resolve_env_path(edata.get("path", "")), "main.py")):
                install_btn.setText("Update")
                install_btn.setStyleSheet("""
                    QPushButton { background-color: #f0fdfa; color: #0d9488; border: 1px solid #5eead4; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 12px; }
                    QPushButton:hover { background-color: #ccfbf1; }
                """)
                install_btn.clicked.connect(lambda _, eid=env_id: self._update_env(eid, install_btn))
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
            open_btn.clicked.connect(lambda _, p=_resolve_env_path(edata.get("path", "")): self._open_folder(p))
            
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
            
            # 5. Advanced Addons
            addons_btn = QPushButton("Advanced ⚙️")
            addons_btn.setStyleSheet("""
                QPushButton { background-color: #f3f4f6; color: #475569; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 12px; }
                QPushButton:hover { background-color: #e2e8f0; }
            """)
            addons_btn.clicked.connect(lambda _, eid=env_id: self._open_addons_dialog(eid))

            action_layout.addWidget(install_btn)
            action_layout.addWidget(open_btn)
            action_layout.addWidget(dup_btn)
            action_layout.addWidget(del_btn)
            action_layout.addWidget(addons_btn)
            action_layout.addStretch()
            
            empty_item = QTableWidgetItem()
            empty_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 5, empty_item)
            self.table.setCellWidget(row, 5, action_widget)
            self.table.setRowHeight(row, 56)
            
        self.table.blockSignals(False)

    def _install_env(self, target_env_id):
        from ui.install_dialog import InstallDialog
        dlg = InstallDialog(self)
        name = target_env_id.replace("env_", "")
        dlg.env_name_input.setText(name)
        dlg.exec()
        self.refresh_table()

    def _update_env(self, env_id, btn):
        from core.checker import set_active_env, update_comfyui, update_all_custom_nodes
        import core.checker

        reply = QMessageBox.question(
            self, f"Update Environment",
            f"Update ComfyUI and custom nodes in '{env_id}'?\n\nThis will run git pull for ComfyUI and all nodes.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        original_env_id = core.checker.ACTIVE_ENV_ID
        set_active_env(env_id)

        btn.setEnabled(False)
        btn.setText("Updating...")

        from PySide6.QtCore import QThread, Signal

        class EnvUpdateWorker(QThread):
            finished_signal = Signal(bool, str, int, int)

            def run(self):
                c_success, c_msg = update_comfyui()
                s_count, f_count, _ = update_all_custom_nodes()
                self.finished_signal.emit(c_success, c_msg, s_count, f_count)

        def _on_update_done(c_success, c_msg, s_count, f_count):
            set_active_env(original_env_id)
            btn.setEnabled(True)
            btn.setText("Update")
            msg = f"ComfyUI Update: {'Success' if c_success else 'Failed'}\nNodes Update: {s_count} succeeded, {f_count} failed"
            if not c_success:
                msg += f"\n\nError: {c_msg}"
            QMessageBox.information(self, "Update Complete", msg)

        self._env_update_worker = EnvUpdateWorker()
        self._env_update_worker.finished_signal.connect(_on_update_done)
        self._env_update_worker.start()

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
        from ui.install_dialog import InstallDialog
        dlg = InstallDialog(self)
        dlg.exec()
        self.refresh_table()

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

    def _open_addons_dialog(self, env_id):
        dialog = AdvancedAddonsDialog(env_id, self)
        dialog.exec()

class AdvancedAddonsDialog(QDialog):
    def __init__(self, env_id, parent=None):
        super().__init__(parent)
        self.env_id = env_id
        self.setWindowTitle(f"Advanced Add-ons - {env_id}")
        self.setMinimumWidth(500)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"Manage High-Performance Backends\nEnvironment: {self.env_id}")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1e293b;")
        layout.addWidget(title)
        
        desc = QLabel("These add-ons require Python 3.12 and PyTorch 2.8+ (cu128).")
        desc.setStyleSheet("color: #64748b; margin-bottom: 10px;")
        layout.addWidget(desc)

        # Container for the add-on rows
        addons_container = QWidget()
        v_layout = QVBoxLayout(addons_container)
        v_layout.setSpacing(10)
        
        addons = [
            ("sageattention", "SageAttention (v2 & v3)", "Replaces standard attention backend, optimizing speed."),
            ("flashattention", "FlashAttention (v2.8.3)", "Replaces standard attention for massive speedups."),
            ("nunchaku", "Nunchaku", "Essential for certain customized rendering workflows."),
            ("onnxruntime-gpu", "ONNX Runtime GPU", "GPU Acceleration for ONNX models.")
        ]
        
        for addon_id, name, description in addons:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(10, 10, 10, 10)
            row_widget.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;")
            
            text_layout = QVBoxLayout()
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: #0f172a; border: none;")
            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet("color: #475569; font-size: 12px; border: none;")
            desc_lbl.setWordWrap(True)
            text_layout.addWidget(name_lbl)
            text_layout.addWidget(desc_lbl)
            
            install_btn = QPushButton("Install")
            install_btn.setStyleSheet("""
                QPushButton { background-color: #3b82f6; color: white; border-radius: 6px; padding: 6px 15px; font-weight: bold; }
                QPushButton:hover { background-color: #2563eb; }
                QPushButton:disabled { background-color: #94a3b8; }
            """)
            install_btn.setFixedWidth(100)
            install_btn.clicked.connect(lambda _, aid=addon_id, btn=install_btn: self._install_addon(aid, btn))
            
            row_layout.addLayout(text_layout)
            row_layout.addWidget(install_btn, alignment=Qt.AlignRight | Qt.AlignVCenter)
            v_layout.addWidget(row_widget)
            
        layout.addWidget(addons_container)
        
        # Log terminal
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(120)
        self.log_output.setStyleSheet("background-color: #1e293b; color: #10b981; font-family: Consolas, monospace; font-size: 11px; padding: 5px;")
        layout.addWidget(self.log_output)
        
        # Close button
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("padding: 8px 20px; border-radius: 6px; background-color: #e2e8f0; font-weight: bold;")
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _install_addon(self, addon_id, btn):
        from core.checker import ENVIRONMENTS
        env_data = ENVIRONMENTS.get(self.env_id)
        if not env_data:
            QMessageBox.warning(self, "Error", "Environment not found.")
            return
            
        comfy_path = _resolve_env_path(env_data.get("path", ""))
        if not os.path.exists(comfy_path):
            QMessageBox.warning(self, "Error", "ComfyUI is not installed in this environment yet.")
            return
            
        python_exe = os.path.join(comfy_path, "..", "python_embeded", "python.exe")
        if not os.path.exists(python_exe):
            # Fallback for standard environments
            python_exe = os.path.join(comfy_path, "venv", "Scripts", "python.exe")
            
        btn.setEnabled(False)
        btn.setText("Installing...")
        self.log_output.clear()
        self.log_output.append(f"Starting installation for {addon_id}...\nTarget: {python_exe}\n")
        
        # Run installation in a separate thread so UI doesn't freeze
        from PySide6.QtCore import QThread, Signal
        
        class InstallWorker(QThread):
            progress_signal = Signal(str)
            finished_signal = Signal(bool, str)
            
            def __init__(self, aid, py_path, c_path):
                super().__init__()
                self.aid = aid
                self.py_path = py_path
                self.c_path = c_path
                
            def run(self):
                from core.addons_installer import install_addon
                def _cb(msg):
                    self.progress_signal.emit(msg)
                success, msg = install_addon(self.aid, self.py_path, self.c_path, callback=_cb)
                self.finished_signal.emit(success, msg)
                
        self.worker = InstallWorker(addon_id, python_exe, comfy_path)
        self.worker.progress_signal.connect(self.log_output.append)
        
        def _on_finish(success, msg):
            self.log_output.append(f"\nResult: {msg}")
            btn.setText("Done" if success else "Failed")
            if not success:
                btn.setEnabled(True)
                btn.setText("Retry")
                
        self.worker.finished_signal.connect(_on_finish)
        self.worker.start()

