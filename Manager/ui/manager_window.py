"""
DSUComfyCG Manager - Main Window UI (v7 - With Download Queue)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QStatusBar, QMessageBox, QProgressBar,
    QGroupBox, QFrame, QApplication, QDialog, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont

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
            "total_workflows": 0,
            "missing_nodes": [],
            "missing_models": []
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
        
        self.progress.emit("Scanning all workflows...")
        workflows = scan_workflows()
        results["total_workflows"] = len(workflows)
        
        # Scan all workflows for missing dependencies
        all_missing_nodes = {}
        all_missing_models = {}
        
        for wf in workflows:
            deps = check_workflow_dependencies(wf)
            
            for node in deps["nodes"]:
                if not node["installed"] and node["folder"] != "Builtin" and node["url"]:
                    if node["url"] not in all_missing_nodes:
                        all_missing_nodes[node["url"]] = node["folder"]
            
            for model in deps["models"]:
                if not model["installed"] and model["url"]:
                    if model["name"] not in all_missing_models:
                        all_missing_models[model["name"]] = model["url"]
        
        results["missing_nodes"] = list(all_missing_nodes.items())
        results["missing_models"] = list(all_missing_models.items())
        
        self.progress.emit("Ready!")
        self.finished.emit(results)


class DownloadQueueWorker(QThread):
    """Background worker for downloading queue items."""
    item_started = Signal(str, int, int)  # name, index, total
    item_progress = Signal(str, int, int)  # name, downloaded, total_bytes
    item_finished = Signal(str, bool, str)  # name, success, message
    all_finished = Signal()
    
    def __init__(self, nodes, models):
        super().__init__()
        self.nodes = nodes  # list of (url, name)
        self.models = models  # list of (name, url)
        self.is_cancelled = False
    
    def run(self):
        total = len(self.nodes) + len(self.models)
        index = 0
        
        # Install nodes
        for url, name in self.nodes:
            if self.is_cancelled:
                break
            index += 1
            self.item_started.emit(f"Node: {name}", index, total)
            success, msg = install_node(url)
            self.item_finished.emit(f"Node: {name}", success, msg)
        
        # Download models
        for name, url in self.models:
            if self.is_cancelled:
                break
            index += 1
            self.item_started.emit(f"Model: {name[:30]}...", index, total)
            
            def progress_cb(downloaded, total_bytes):
                self.item_progress.emit(name, downloaded, total_bytes)
            
            success, msg = download_model(name, progress_cb)
            self.item_finished.emit(f"Model: {name[:30]}...", success, msg)
        
        self.all_finished.emit()
    
    def cancel(self):
        self.is_cancelled = True


class ManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DSUComfyCG Manager")
        self.resize(1400, 800)
        self.setMinimumSize(1200, 700)
        
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
        
        # Main content with 3 columns
        content_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(content_splitter, stretch=1)
        
        # Left: Workflows
        left_panel = self._create_workflow_panel()
        content_splitter.addWidget(left_panel)
        
        # Center: Dependencies
        center_panel = self._create_dependency_panel()
        content_splitter.addWidget(center_panel)
        
        # Right: Download Queue
        right_panel = self._create_queue_panel()
        content_splitter.addWidget(right_panel)
        
        content_splitter.setSizes([280, 550, 400])
        
        # Action bar
        action_bar = self._create_action_bar()
        main_layout.addWidget(action_bar)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.pending_node_installs = []
        self.pending_model_downloads = []
        self.queue_nodes = []
        self.queue_models = []
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
        self.nodes_tree.setColumnWidth(0, 200)
        self.nodes_tree.setColumnWidth(1, 100)
        self.nodes_tree.setColumnWidth(2, 80)
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
        self.models_tree.setColumnWidth(0, 200)
        self.models_tree.setColumnWidth(1, 100)
        self.models_tree.setColumnWidth(2, 80)
        self.models_tree.setRootIsDecorated(False)
        layout.addWidget(self.models_tree)
        
        return group
    
    def _create_queue_panel(self):
        group = QGroupBox("Download Queue")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        # Summary
        self.queue_summary = QLabel("Scanning...")
        self.queue_summary.setObjectName("queueSummary")
        self.queue_summary.setWordWrap(True)
        layout.addWidget(self.queue_summary)
        
        # Progress section
        self.queue_progress_frame = QFrame()
        self.queue_progress_frame.setObjectName("queueProgressFrame")
        progress_layout = QVBoxLayout(self.queue_progress_frame)
        progress_layout.setContentsMargins(10, 10, 10, 10)
        
        self.queue_current_label = QLabel("Ready")
        self.queue_current_label.setStyleSheet("color: #00ffcc; font-size: 12px;")
        progress_layout.addWidget(self.queue_current_label)
        
        self.queue_progress_bar = QProgressBar()
        self.queue_progress_bar.setRange(0, 100)
        self.queue_progress_bar.setValue(0)
        self.queue_progress_bar.setObjectName("queueProgressBar")
        progress_layout.addWidget(self.queue_progress_bar)
        
        self.queue_detail_label = QLabel("")
        self.queue_detail_label.setStyleSheet("color: #888; font-size: 11px;")
        progress_layout.addWidget(self.queue_detail_label)
        
        layout.addWidget(self.queue_progress_frame)
        
        # Queue list
        self.queue_list = QListWidget()
        self.queue_list.setObjectName("queueList")
        layout.addWidget(self.queue_list)
        
        # Queue buttons
        btn_layout = QHBoxLayout()
        
        self.start_queue_btn = QPushButton("Start Download")
        self.start_queue_btn.setObjectName("primaryBtn")
        self.start_queue_btn.clicked.connect(self.start_queue_download)
        self.start_queue_btn.setEnabled(False)
        btn_layout.addWidget(self.start_queue_btn)
        
        self.clear_queue_btn = QPushButton("Clear")
        self.clear_queue_btn.setObjectName("smallBtn")
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        btn_layout.addWidget(self.clear_queue_btn)
        
        layout.addLayout(btn_layout)
        
        return group
    
    def _create_action_bar(self):
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 15, 0, 0)
        
        self.update_db_btn = QPushButton("Refresh DB")
        self.update_db_btn.setObjectName("smallBtn")
        self.update_db_btn.clicked.connect(self.update_node_db)
        layout.addWidget(self.update_db_btn)
        
        self.rescan_btn = QPushButton("Rescan All")
        self.rescan_btn.setObjectName("smallBtn")
        self.rescan_btn.clicked.connect(self.rescan_all_workflows)
        layout.addWidget(self.rescan_btn)
        
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
            #titleLabel { color: #00ffcc; font-size: 26px; font-weight: bold; }
            #systemInfo { color: #888; font-size: 11px; }
            
            #startupFrame {
                background: rgba(0, 255, 200, 0.05);
                border: 1px solid #00ffcc;
                border-radius: 10px;
            }
            #startupLabel { color: #00ffcc; font-size: 14px; }
            #startupProgress {
                background: #1a1a2e; border: none; border-radius: 5px; height: 6px;
            }
            #startupProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00ffcc, stop:1 #00ccff);
                border-radius: 5px;
            }
            
            QGroupBox {
                color: #ffffff; font-size: 14px; font-weight: bold;
                border: 1px solid #2a2a4e; border-radius: 12px;
                margin-top: 18px; padding-top: 18px;
                background: rgba(20, 20, 40, 0.7);
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 15px; padding: 0 10px; color: #00ffcc;
            }
            
            #sectionLabel { color: #00ccff; font-size: 12px; font-weight: bold; }
            #countLabel { color: #666; font-size: 11px; }
            #queueSummary { color: #ccc; font-size: 12px; padding: 10px; }
            
            #queueProgressFrame {
                background: rgba(0, 200, 255, 0.05);
                border: 1px solid #2a2a4e;
                border-radius: 8px;
            }
            #queueProgressBar {
                background: #1a1a2e; border: 1px solid #3a3a5e;
                border-radius: 6px; height: 20px; text-align: center; color: #fff;
            }
            #queueProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00ffcc, stop:1 #00ccff);
                border-radius: 5px;
            }
            
            QListWidget, QTreeWidget {
                background: rgba(10, 10, 25, 0.9); color: #ffffff;
                border: 1px solid #2a2a4e; border-radius: 8px; font-size: 11px;
            }
            QListWidget::item { padding: 8px 10px; border-radius: 4px; margin: 2px 0; }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00ffcc, stop:1 #00ccff);
                color: #000;
            }
            QTreeWidget::item { padding: 8px 5px; border-bottom: 1px solid #1a1a2e; }
            QHeaderView::section {
                background: #1a1a3e; color: #00ccff; padding: 8px;
                border: none; font-weight: bold; font-size: 10px;
            }
            
            #queueList::item { padding: 6px 8px; font-size: 11px; }
            
            QPushButton { border: none; border-radius: 8px; padding: 10px 20px; font-size: 12px; font-weight: bold; }
            #primaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00ffcc, stop:1 #00ccff);
                color: #000; font-size: 14px; padding: 12px 30px;
            }
            #primaryBtn:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #33ffdd, stop:1 #33ddff); }
            #primaryBtn:disabled { background: #333; color: #666; }
            #secondaryBtn { background: #2a2a4e; color: #ffffff; }
            #secondaryBtn:hover { background: #3a3a5e; }
            #smallBtn { background: #2a2a4e; color: #ccc; padding: 6px 12px; font-size: 11px; }
            #smallBtn:hover { background: #3a3a5e; }
            #installBtn { background: #ff6b6b; color: white; padding: 4px 12px; font-size: 10px; border-radius: 4px; }
            #installBtn:hover { background: #ff8787; }
            #downloadBtn { background: #6b9fff; color: white; padding: 4px 12px; font-size: 10px; border-radius: 4px; }
            #downloadBtn:hover { background: #87b0ff; }
            #addQueueBtn { background: #9b6bff; color: white; padding: 4px 12px; font-size: 10px; border-radius: 4px; }
            #addQueueBtn:hover { background: #b087ff; }
            
            QStatusBar { background: #0a0a1a; color: #555; border-top: 1px solid #2a2a4e; padding: 5px; }
            QScrollBar:vertical { background: #1a1a2e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #3a3a5e; border-radius: 4px; min-height: 30px; }
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
        
        # Populate queue with missing items
        self.queue_nodes = results["missing_nodes"]
        self.queue_models = results["missing_models"]
        self.update_queue_display()
        
        n_nodes = len(self.queue_nodes)
        n_models = len(self.queue_models)
        
        if n_nodes > 0 or n_models > 0:
            self.queue_summary.setText(
                f"Found missing dependencies:\n"
                f"• {n_nodes} custom node(s)\n"
                f"• {n_models} model(s)\n\n"
                f"Click 'Start Download' to install all."
            )
            self.start_queue_btn.setEnabled(True)
        else:
            self.queue_summary.setText("All dependencies installed! ✓")
        
        self.status_bar.showMessage(
            f"Ready! Nodes: {results['node_db_count']} | Models: {results['model_db_count']} | Workflows: {results['total_workflows']}"
        )
    
    def update_queue_display(self):
        self.queue_list.clear()
        
        for url, name in self.queue_nodes:
            item = QListWidgetItem(f"📦 {name}")
            item.setData(Qt.UserRole, ("node", url, name))
            self.queue_list.addItem(item)
        
        for name, url in self.queue_models:
            display = name if len(name) < 35 else name[:32] + "..."
            item = QListWidgetItem(f"📥 {display}")
            item.setData(Qt.UserRole, ("model", name, url))
            self.queue_list.addItem(item)
    
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
    
    def rescan_all_workflows(self):
        self.status_bar.showMessage("Rescanning all workflows...")
        QApplication.processEvents()
        
        workflows = scan_workflows()
        all_missing_nodes = {}
        all_missing_models = {}
        
        for wf in workflows:
            deps = check_workflow_dependencies(wf)
            for node in deps["nodes"]:
                if not node["installed"] and node["folder"] != "Builtin" and node["url"]:
                    if node["url"] not in all_missing_nodes:
                        all_missing_nodes[node["url"]] = node["folder"]
            for model in deps["models"]:
                if not model["installed"] and model["url"]:
                    if model["name"] not in all_missing_models:
                        all_missing_models[model["name"]] = model["url"]
        
        self.queue_nodes = list(all_missing_nodes.items())
        self.queue_models = list(all_missing_models.items())
        self.update_queue_display()
        
        n_nodes = len(self.queue_nodes)
        n_models = len(self.queue_models)
        
        if n_nodes > 0 or n_models > 0:
            self.queue_summary.setText(
                f"Found missing dependencies:\n• {n_nodes} node(s)\n• {n_models} model(s)"
            )
            self.start_queue_btn.setEnabled(True)
        else:
            self.queue_summary.setText("All dependencies installed! ✓")
            self.start_queue_btn.setEnabled(False)
        
        self.status_bar.showMessage(f"Scan complete: {n_nodes} nodes, {n_models} models missing")
    
    def on_workflow_selected(self, current, previous):
        if not current:
            return
        filename = current.data(Qt.UserRole)
        self.check_dependencies(filename)
    
    def check_dependencies(self, filename):
        deps = check_workflow_dependencies(filename)
        
        # Nodes
        self.nodes_tree.clear()
        installed_count = missing_count = 0
        
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
                    btn = QPushButton("+Queue")
                    btn.setObjectName("addQueueBtn")
                    btn.setFixedSize(60, 24)
                    btn.clicked.connect(lambda c, u=node["url"], n=folder: self.add_node_to_queue(u, n))
                    self.nodes_tree.setItemWidget(item, 2, btn)
            
            self.nodes_tree.addTopLevelItem(item)
        
        self.nodes_count.setText(f"OK: {installed_count} / Missing: {missing_count}")
        
        # Models
        self.models_tree.clear()
        found = missing_m = 0
        
        for model in deps["models"]:
            item = QTreeWidgetItem()
            name = model["name"]
            item.setText(0, name if len(name) < 30 else name[:27] + "...")
            item.setToolTip(0, name)
            
            if model["installed"]:
                item.setText(1, "Found")
                item.setForeground(1, QColor("#00ffcc"))
                found += 1
            else:
                if model["url"]:
                    item.setText(1, "Available")
                    item.setForeground(1, QColor("#6b9fff"))
                    btn = QPushButton("+Queue")
                    btn.setObjectName("addQueueBtn")
                    btn.setFixedSize(60, 24)
                    btn.clicked.connect(lambda c, n=name, u=model["url"]: self.add_model_to_queue(n, u))
                    self.models_tree.setItemWidget(item, 2, btn)
                else:
                    item.setText(1, "Unknown")
                    item.setForeground(1, QColor("#ffd93d"))
                missing_m += 1
            
            self.models_tree.addTopLevelItem(item)
        
        self.models_count.setText(f"OK: {found} / Missing: {missing_m}")
    
    def add_node_to_queue(self, url, name):
        if (url, name) not in self.queue_nodes:
            self.queue_nodes.append((url, name))
            self.update_queue_display()
            self.start_queue_btn.setEnabled(True)
            self.status_bar.showMessage(f"Added {name} to queue")
    
    def add_model_to_queue(self, name, url):
        if (name, url) not in self.queue_models:
            self.queue_models.append((name, url))
            self.update_queue_display()
            self.start_queue_btn.setEnabled(True)
            self.status_bar.showMessage(f"Added {name[:30]} to queue")
    
    def clear_queue(self):
        self.queue_nodes = []
        self.queue_models = []
        self.queue_list.clear()
        self.queue_summary.setText("Queue cleared")
        self.start_queue_btn.setEnabled(False)
        self.queue_progress_bar.setValue(0)
        self.queue_current_label.setText("Ready")
        self.queue_detail_label.setText("")
    
    def start_queue_download(self):
        if not self.queue_nodes and not self.queue_models:
            return
        
        total = len(self.queue_nodes) + len(self.queue_models)
        reply = QMessageBox.question(self, "Start Download",
            f"Download {total} item(s)?\n\n"
            f"• {len(self.queue_nodes)} node(s)\n"
            f"• {len(self.queue_models)} model(s)\n\n"
            "This may take a while for large models.",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
        
        self.start_queue_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        
        self.download_worker = DownloadQueueWorker(self.queue_nodes, self.queue_models)
        self.download_worker.item_started.connect(self.on_queue_item_started)
        self.download_worker.item_progress.connect(self.on_queue_item_progress)
        self.download_worker.item_finished.connect(self.on_queue_item_finished)
        self.download_worker.all_finished.connect(self.on_queue_all_finished)
        self.download_worker.start()
    
    def on_queue_item_started(self, name, index, total):
        self.queue_current_label.setText(f"[{index}/{total}] {name}")
        pct = int((index - 1) / total * 100)
        self.queue_progress_bar.setValue(pct)
        self.queue_detail_label.setText("Starting...")
        QApplication.processEvents()
    
    def on_queue_item_progress(self, name, downloaded, total_bytes):
        if total_bytes > 0:
            mb_down = downloaded / (1024 * 1024)
            mb_total = total_bytes / (1024 * 1024)
            self.queue_detail_label.setText(f"{mb_down:.1f} MB / {mb_total:.1f} MB")
        QApplication.processEvents()
    
    def on_queue_item_finished(self, name, success, message):
        status = "✓" if success else "✗"
        self.status_bar.showMessage(f"{status} {name}: {message}")
    
    def on_queue_all_finished(self):
        self.queue_progress_bar.setValue(100)
        self.queue_current_label.setText("Complete!")
        self.queue_detail_label.setText("")
        
        self.queue_nodes = []
        self.queue_models = []
        self.queue_list.clear()
        
        self.start_queue_btn.setEnabled(False)
        self.run_btn.setEnabled(True)
        
        self.queue_summary.setText("All downloads complete! ✓")
        
        current = self.workflow_list.currentItem()
        if current:
            self.check_dependencies(current.data(Qt.UserRole))
        
        QMessageBox.information(self, "Done", "All downloads complete!")
    
    def update_system_status(self):
        status = get_system_status()
        parts = []
        if status["python_version"]:
            parts.append(f"Py {status['python_version']}")
        if status["cuda_available"] and status["gpu_name"]:
            parts.append(status["gpu_name"][:20])
        parts.append(f"DB: {status['node_db_size']}")
        self.system_info.setText(" | ".join(parts))
    
    def run_comfy(self):
        if run_comfyui():
            QMessageBox.information(self, "ComfyUI", "ComfyUI is starting!\n\nhttp://localhost:8188")
        else:
            QMessageBox.warning(self, "Error", "Failed to start ComfyUI")
