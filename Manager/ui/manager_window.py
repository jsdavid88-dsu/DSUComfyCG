"""
DSUComfyCG Manager - Main Window UI (v6 - With Progress Bars)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QStatusBar, QMessageBox, QProgressBar,
    QGroupBox, QFrame, QApplication, QDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor

from core.checker import (
    scan_workflows, check_workflow_dependencies, get_system_status,
    install_node, run_comfyui, sync_workflows, fetch_node_db, NODE_DB,
    download_model, load_model_db, MODEL_DB
)


class StartupWorker(QThread):
    """Background worker for startup checks."""
    progress = Signal(str)
    finished = Signal(dict)
    
    def run(self):
        results = {
            "node_db_count": 0,
            "model_db_count": 0,
            "workflows_synced": 0,
            "workflows_skipped": 0,
            "total_workflows": 0
        }
        
        self.progress.emit("Loading NODE_DB...")
        fetch_node_db(force_refresh=False)
        results["node_db_count"] = len(NODE_DB)
        
        self.progress.emit("Loading MODEL_DB...")
        load_model_db()
        results["model_db_count"] = len(MODEL_DB)
        
        self.progress.emit("Syncing workflows...")
        synced, skipped = sync_workflows()
        results["workflows_synced"] = synced
        results["workflows_skipped"] = skipped
        
        workflows = scan_workflows()
        results["total_workflows"] = len(workflows)
        
        self.progress.emit("Ready!")
        self.finished.emit(results)


class NodeInstallWorker(QThread):
    """Background worker for node installation."""
    progress = Signal(str, int, int)  # message, current, total
    finished = Signal(bool, str)
    
    def __init__(self, urls):
        super().__init__()
        self.urls = urls
    
    def run(self):
        total = len(self.urls)
        for i, url in enumerate(self.urls):
            name = url.split('/')[-1]
            self.progress.emit(f"Installing {name}...", i + 1, total)
            success, msg = install_node(url)
            if not success:
                self.finished.emit(False, msg)
                return
        self.finished.emit(True, f"Installed {total} node(s)")


class ModelDownloadWorker(QThread):
    """Background worker for model download."""
    progress = Signal(str, int, int)  # message, downloaded_bytes, total_bytes
    finished = Signal(bool, str)
    
    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name
    
    def run(self):
        def progress_cb(downloaded, total):
            self.progress.emit(self.model_name, downloaded, total)
        
        success, msg = download_model(self.model_name, progress_cb)
        self.finished.emit(success, msg)


class ProgressDialog(QDialog):
    """Progress dialog for downloads."""
    def __init__(self, parent, title="Progress"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(450, 150)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        self.status_label = QLabel("Starting...")
        self.status_label.setStyleSheet("color: #00ffcc; font-size: 13px;")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #1a1a2e;
                border: 1px solid #3a3a5e;
                border-radius: 8px;
                height: 24px;
                text-align: center;
                color: #fff;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00ffcc, stop:1 #00ccff);
                border-radius: 7px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.detail_label)
        
        self.setStyleSheet("""
            QDialog {
                background: #0a0a1a;
                border: 2px solid #00ffcc;
                border-radius: 12px;
            }
        """)


class ManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DSUComfyCG Manager")
        self.resize(1100, 750)
        self.setMinimumSize(900, 650)
        
        self.setStyleSheet(self._get_stylesheet())
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        header = self._create_header()
        main_layout.addWidget(header)
        
        self.startup_frame = self._create_startup_frame()
        main_layout.addWidget(self.startup_frame)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, stretch=1)
        
        left_panel = self._create_workflow_panel()
        splitter.addWidget(left_panel)
        
        right_panel = self._create_dependency_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([350, 750])
        
        action_bar = self._create_action_bar()
        main_layout.addWidget(action_bar)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.pending_node_installs = []
        self.pending_model_downloads = []
        self.is_ready = False
        
        QTimer.singleShot(100, self.run_startup_checks)
    
    def _create_header(self):
        frame = QFrame()
        frame.setObjectName("headerFrame")
        layout = QHBoxLayout(frame)
        
        title = QLabel("DSUComfyCG Manager")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        layout.addStretch()
        
        self.system_info = QLabel()
        self.system_info.setObjectName("systemInfo")
        layout.addWidget(self.system_info)
        
        return frame
    
    def _create_startup_frame(self):
        frame = QFrame()
        frame.setObjectName("startupFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        
        self.startup_label = QLabel("Initializing...")
        self.startup_label.setObjectName("startupLabel")
        self.startup_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.startup_label)
        
        self.startup_progress = QProgressBar()
        self.startup_progress.setRange(0, 0)
        self.startup_progress.setObjectName("startupProgress")
        layout.addWidget(self.startup_progress)
        
        return frame
    
    def _create_workflow_panel(self):
        group = QGroupBox("Workflows")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        self.workflow_list = QListWidget()
        self.workflow_list.currentItemChanged.connect(self.on_workflow_selected)
        layout.addWidget(self.workflow_list)
        
        btn_layout = QHBoxLayout()
        
        sync_btn = QPushButton("Sync")
        sync_btn.setObjectName("smallBtn")
        sync_btn.clicked.connect(self.sync_workflows_ui)
        btn_layout.addWidget(sync_btn)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("smallBtn")
        refresh_btn.clicked.connect(self.refresh_workflows)
        btn_layout.addWidget(refresh_btn)
        
        layout.addLayout(btn_layout)
        
        return group
    
    def _create_dependency_panel(self):
        group = QGroupBox("Dependencies")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)
        
        # Nodes section
        nodes_header = QHBoxLayout()
        nodes_label = QLabel("Custom Nodes")
        nodes_label.setObjectName("sectionLabel")
        nodes_header.addWidget(nodes_label)
        nodes_header.addStretch()
        
        self.nodes_count = QLabel("")
        self.nodes_count.setObjectName("countLabel")
        nodes_header.addWidget(self.nodes_count)
        layout.addLayout(nodes_header)
        
        self.nodes_tree = QTreeWidget()
        self.nodes_tree.setHeaderLabels(["Package", "Status", ""])
        self.nodes_tree.setColumnWidth(0, 280)
        self.nodes_tree.setColumnWidth(1, 120)
        self.nodes_tree.setColumnWidth(2, 90)
        self.nodes_tree.setRootIsDecorated(False)
        layout.addWidget(self.nodes_tree)
        
        # Models section
        models_header = QHBoxLayout()
        models_label = QLabel("Models")
        models_label.setObjectName("sectionLabel")
        models_header.addWidget(models_label)
        models_header.addStretch()
        
        self.models_count = QLabel("")
        self.models_count.setObjectName("countLabel")
        models_header.addWidget(self.models_count)
        layout.addLayout(models_header)
        
        self.models_tree = QTreeWidget()
        self.models_tree.setHeaderLabels(["File", "Status", ""])
        self.models_tree.setColumnWidth(0, 280)
        self.models_tree.setColumnWidth(1, 120)
        self.models_tree.setColumnWidth(2, 90)
        self.models_tree.setRootIsDecorated(False)
        layout.addWidget(self.models_tree)
        
        return group
    
    def _create_action_bar(self):
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 15, 0, 0)
        
        self.install_nodes_btn = QPushButton("Install Missing Nodes")
        self.install_nodes_btn.setObjectName("secondaryBtn")
        self.install_nodes_btn.clicked.connect(self.install_all_nodes)
        layout.addWidget(self.install_nodes_btn)
        
        self.install_models_btn = QPushButton("Download Missing Models")
        self.install_models_btn.setObjectName("secondaryBtn")
        self.install_models_btn.clicked.connect(self.download_all_models)
        layout.addWidget(self.install_models_btn)
        
        self.update_db_btn = QPushButton("Refresh DB")
        self.update_db_btn.setObjectName("smallBtn")
        self.update_db_btn.clicked.connect(self.update_node_db)
        layout.addWidget(self.update_db_btn)
        
        layout.addStretch()
        
        self.run_btn = QPushButton("Run ComfyUI")
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.clicked.connect(self.run_comfy)
        self.run_btn.setEnabled(False)
        layout.addWidget(self.run_btn)
        
        return frame
    
    def _get_stylesheet(self):
        return """
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a1a, stop:1 #1a1a2e);
            }
            
            #headerFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a1a3e, stop:0.5 #2a2a4e, stop:1 #1a1a3e);
                border-radius: 15px;
                padding: 20px;
                border: 1px solid #3a3a5e;
            }
            
            #titleLabel {
                color: #00ffcc;
                font-size: 28px;
                font-weight: bold;
            }
            
            #systemInfo { color: #888; font-size: 11px; }
            
            #startupFrame {
                background: rgba(0, 255, 200, 0.05);
                border: 1px solid #00ffcc;
                border-radius: 10px;
            }
            
            #startupLabel { color: #00ffcc; font-size: 14px; }
            
            #startupProgress {
                background: #1a1a2e;
                border: none;
                border-radius: 5px;
                height: 6px;
            }
            #startupProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00ffcc, stop:1 #00ccff);
                border-radius: 5px;
            }
            
            QGroupBox {
                color: #ffffff;
                font-size: 15px;
                font-weight: bold;
                border: 1px solid #2a2a4e;
                border-radius: 12px;
                margin-top: 18px;
                padding-top: 18px;
                background: rgba(20, 20, 40, 0.7);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
                color: #00ffcc;
            }
            
            #sectionLabel { color: #00ccff; font-size: 13px; font-weight: bold; }
            #countLabel { color: #666; font-size: 11px; }
            
            QListWidget, QTreeWidget {
                background: rgba(10, 10, 25, 0.9);
                color: #ffffff;
                border: 1px solid #2a2a4e;
                border-radius: 8px;
                font-size: 12px;
            }
            QListWidget::item { padding: 12px 10px; border-radius: 6px; margin: 3px 0; }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00ffcc, stop:1 #00ccff);
                color: #000;
            }
            QListWidget::item:hover:!selected { background: rgba(0, 255, 200, 0.15); }
            
            QTreeWidget::item { padding: 10px 5px; border-bottom: 1px solid #1a1a2e; }
            QTreeWidget::item:selected { background: rgba(0, 255, 200, 0.2); }
            QHeaderView::section {
                background: #1a1a3e;
                color: #00ccff;
                padding: 10px;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
            
            QPushButton {
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 13px;
                font-weight: bold;
            }
            #primaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00ffcc, stop:1 #00ccff);
                color: #000;
                font-size: 15px;
                padding: 15px 40px;
            }
            #primaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #33ffdd, stop:1 #33ddff);
            }
            #primaryBtn:disabled { background: #333; color: #666; }
            
            #secondaryBtn { background: #2a2a4e; color: #ffffff; }
            #secondaryBtn:hover { background: #3a3a5e; }
            
            #smallBtn { background: #2a2a4e; color: #ccc; padding: 8px 16px; font-size: 12px; }
            #smallBtn:hover { background: #3a3a5e; }
            
            #installBtn { background: #ff6b6b; color: white; padding: 5px 15px; font-size: 11px; border-radius: 5px; }
            #installBtn:hover { background: #ff8787; }
            
            #downloadBtn { background: #6b9fff; color: white; padding: 5px 15px; font-size: 11px; border-radius: 5px; }
            #downloadBtn:hover { background: #87b0ff; }
            
            QStatusBar { background: #0a0a1a; color: #555; border-top: 1px solid #2a2a4e; padding: 5px; }
            
            QScrollBar:vertical { background: #1a1a2e; width: 10px; border-radius: 5px; }
            QScrollBar::handle:vertical { background: #3a3a5e; border-radius: 5px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #00ffcc; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """
    
    def run_startup_checks(self):
        self.startup_frame.show()
        self.worker = StartupWorker()
        self.worker.progress.connect(self.on_startup_progress)
        self.worker.finished.connect(self.on_startup_finished)
        self.worker.start()
    
    def on_startup_progress(self, message):
        self.startup_label.setText(message)
    
    def on_startup_finished(self, results):
        self.startup_frame.hide()
        self.is_ready = True
        self.run_btn.setEnabled(True)
        
        self.refresh_workflows()
        self.update_system_status()
        
        msg = f"Ready! Nodes: {results['node_db_count']} | Models: {results['model_db_count']} | Workflows: {results['total_workflows']}"
        self.status_bar.showMessage(msg)
    
    def refresh_workflows(self):
        self.workflow_list.clear()
        workflows = scan_workflows()
        for wf in workflows:
            item = QListWidgetItem(wf)
            item.setData(Qt.UserRole, wf)
            self.workflow_list.addItem(item)
    
    def sync_workflows_ui(self):
        self.status_bar.showMessage("Syncing workflows...")
        QApplication.processEvents()
        synced, skipped = sync_workflows()
        self.refresh_workflows()
        self.status_bar.showMessage(f"Synced {synced}, skipped {skipped}")
    
    def update_node_db(self):
        self.status_bar.showMessage("Refreshing databases...")
        QApplication.processEvents()
        fetch_node_db(force_refresh=True)
        load_model_db()
        self.status_bar.showMessage(f"Nodes: {len(NODE_DB)} | Models: {len(MODEL_DB)}")
        
        current = self.workflow_list.currentItem()
        if current:
            self.check_dependencies(current.data(Qt.UserRole))
    
    def on_workflow_selected(self, current, previous):
        if not current:
            return
        filename = current.data(Qt.UserRole)
        self.check_dependencies(filename)
    
    def check_dependencies(self, filename):
        deps = check_workflow_dependencies(filename)
        
        # Nodes
        self.nodes_tree.clear()
        self.pending_node_installs = []
        installed_count = 0
        missing_count = 0
        
        for node in deps["nodes"]:
            folder = node["folder"]
            if folder == "Builtin":
                continue
            
            item = QTreeWidgetItem()
            item.setText(0, folder)
            
            if folder == "Unknown":
                item.setText(1, "Unknown")
                item.setForeground(1, QColor("#ffd93d"))
            elif node["installed"]:
                item.setText(1, "Installed")
                item.setForeground(1, QColor("#00ffcc"))
                installed_count += 1
            else:
                item.setText(1, "Missing")
                item.setForeground(1, QColor("#ff6b6b"))
                missing_count += 1
                if node["url"]:
                    self.pending_node_installs.append(node["url"])
                    btn = QPushButton("Install")
                    btn.setObjectName("installBtn")
                    btn.setFixedSize(75, 28)
                    btn.clicked.connect(lambda c, u=node["url"]: self.install_single_node(u))
                    self.nodes_tree.setItemWidget(item, 2, btn)
            
            self.nodes_tree.addTopLevelItem(item)
        
        self.nodes_count.setText(f"OK: {installed_count} / Missing: {missing_count}")
        
        # Models
        self.models_tree.clear()
        self.pending_model_downloads = []
        found = 0
        missing_m = 0
        
        for model in deps["models"]:
            item = QTreeWidgetItem()
            name = model["name"]
            display_name = name if len(name) < 40 else name[:37] + "..."
            item.setText(0, display_name)
            item.setToolTip(0, name)
            item.setData(0, Qt.UserRole, name)
            
            if model["installed"]:
                item.setText(1, "Found")
                item.setForeground(1, QColor("#00ffcc"))
                found += 1
            else:
                if model["url"]:
                    item.setText(1, "Available")
                    item.setForeground(1, QColor("#6b9fff"))
                    self.pending_model_downloads.append(name)
                    btn = QPushButton("Download")
                    btn.setObjectName("downloadBtn")
                    btn.setFixedSize(75, 28)
                    btn.clicked.connect(lambda c, m=name: self.download_single_model(m))
                    self.models_tree.setItemWidget(item, 2, btn)
                else:
                    item.setText(1, "Unknown")
                    item.setForeground(1, QColor("#ffd93d"))
                missing_m += 1
            
            self.models_tree.addTopLevelItem(item)
        
        self.models_count.setText(f"OK: {found} / Missing: {missing_m}")
    
    def install_single_node(self, url):
        dialog = ProgressDialog(self, "Installing Node")
        dialog.show()
        
        self.node_worker = NodeInstallWorker([url])
        self.node_worker.progress.connect(lambda msg, c, t: self._update_progress(dialog, msg, c, t, True))
        self.node_worker.finished.connect(lambda ok, msg: self._finish_install(dialog, ok, msg))
        self.node_worker.start()
    
    def install_all_nodes(self):
        if not self.pending_node_installs:
            QMessageBox.information(self, "Info", "No missing nodes to install!")
            return
        
        reply = QMessageBox.question(self, "Confirm", 
            f"Install {len(self.pending_node_installs)} missing node(s)?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            dialog = ProgressDialog(self, "Installing Nodes")
            dialog.show()
            
            self.node_worker = NodeInstallWorker(self.pending_node_installs)
            self.node_worker.progress.connect(lambda msg, c, t: self._update_progress(dialog, msg, c, t, True))
            self.node_worker.finished.connect(lambda ok, msg: self._finish_install(dialog, ok, msg))
            self.node_worker.start()
    
    def download_single_model(self, model_name):
        dialog = ProgressDialog(self, "Downloading Model")
        dialog.status_label.setText(f"Downloading {model_name[:40]}...")
        dialog.show()
        
        self.model_worker = ModelDownloadWorker(model_name)
        self.model_worker.progress.connect(lambda n, d, t: self._update_download_progress(dialog, n, d, t))
        self.model_worker.finished.connect(lambda ok, msg: self._finish_download(dialog, ok, msg))
        self.model_worker.start()
    
    def download_all_models(self):
        if not self.pending_model_downloads:
            QMessageBox.information(self, "Info", "No models to download!")
            return
        
        QMessageBox.information(self, "Info", 
            f"Model downloads are large files.\nPlease download one at a time using the 'Download' buttons.")
    
    def _update_progress(self, dialog, message, current, total, is_count):
        dialog.status_label.setText(message)
        if is_count and total > 0:
            pct = int((current / total) * 100)
            dialog.progress_bar.setValue(pct)
            dialog.detail_label.setText(f"{current} / {total}")
        QApplication.processEvents()
    
    def _update_download_progress(self, dialog, name, downloaded, total):
        if total > 0:
            pct = int((downloaded / total) * 100)
            dialog.progress_bar.setValue(pct)
            
            mb_down = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            dialog.detail_label.setText(f"{mb_down:.1f} MB / {mb_total:.1f} MB")
        QApplication.processEvents()
    
    def _finish_install(self, dialog, success, message):
        dialog.close()
        if success:
            self.status_bar.showMessage(message)
            current = self.workflow_list.currentItem()
            if current:
                self.check_dependencies(current.data(Qt.UserRole))
        else:
            QMessageBox.warning(self, "Error", message)
    
    def _finish_download(self, dialog, success, message):
        dialog.close()
        if success:
            self.status_bar.showMessage(message)
            current = self.workflow_list.currentItem()
            if current:
                self.check_dependencies(current.data(Qt.UserRole))
        else:
            QMessageBox.warning(self, "Download Failed", message)
    
    def update_system_status(self):
        status = get_system_status()
        parts = []
        
        if status["python_version"]:
            parts.append(f"Python {status['python_version']}")
        
        if status["cuda_available"] and status["gpu_name"]:
            parts.append(status["gpu_name"])
        
        parts.append(f"Nodes: {status['node_db_size']} | Models: {len(MODEL_DB)}")
        
        self.system_info.setText(" | ".join(parts))
    
    def run_comfy(self):
        if run_comfyui():
            QMessageBox.information(self, "ComfyUI", "ComfyUI is starting!\n\nhttp://localhost:8188")
        else:
            QMessageBox.warning(self, "Error", "Failed to start ComfyUI")
