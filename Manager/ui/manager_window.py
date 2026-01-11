"""
DSUComfyCG Manager - Main Window UI (v2 - Modern Design)
PySide6-based desktop application for managing ComfyUI workflows and dependencies.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QStatusBar, QMessageBox, QProgressBar,
    QGroupBox, QFrame, QHeaderView, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QColor, QPalette

from core.checker import (
    scan_workflows, check_workflow_dependencies, get_system_status,
    install_node, run_comfyui, NODE_DB
)


class InstallWorker(QThread):
    finished = Signal(bool, str)
    
    def __init__(self, git_url):
        super().__init__()
        self.git_url = git_url
    
    def run(self):
        success, message = install_node(self.git_url)
        self.finished.emit(success, message)


class ManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DSUComfyCG Manager")
        self.resize(1000, 700)
        self.setMinimumSize(800, 600)
        
        self.setStyleSheet(self._get_modern_stylesheet())
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Header with gradient feel
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        
        title = QLabel("🚀 DSUComfyCG Manager")
        title.setObjectName("titleLabel")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Status indicators in header
        self.status_label = QLabel()
        self.status_label.setObjectName("statusIndicator")
        header_layout.addWidget(self.status_label)
        
        main_layout.addWidget(header_frame)
        
        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("mainSplitter")
        main_layout.addWidget(splitter, stretch=1)
        
        # Left panel
        left_panel = self._create_workflow_panel()
        splitter.addWidget(left_panel)
        
        # Right panel
        right_panel = self._create_dependency_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([350, 650])
        
        # Bottom action bar
        action_bar = QFrame()
        action_bar.setObjectName("actionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 10, 0, 0)
        
        self.install_all_btn = QPushButton("📦 Install All Missing")
        self.install_all_btn.setObjectName("secondaryBtn")
        self.install_all_btn.clicked.connect(self.install_all_missing)
        action_layout.addWidget(self.install_all_btn)
        
        self.check_btn = QPushButton("🔄 Check All")
        self.check_btn.setObjectName("secondaryBtn")
        self.check_btn.clicked.connect(self.check_all)
        action_layout.addWidget(self.check_btn)
        
        action_layout.addStretch()
        
        self.run_btn = QPushButton("▶  Run ComfyUI")
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.clicked.connect(self.run_comfy)
        action_layout.addWidget(self.run_btn)
        
        main_layout.addWidget(action_bar)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.pending_installs = []
        self.refresh_workflows()
        self.update_system_status()
    
    def _get_modern_stylesheet(self):
        return """
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0f0f23, stop:1 #1a1a2e);
            }
            
            #headerFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #16213e, stop:1 #1a1a2e);
                border-radius: 12px;
                padding: 15px;
            }
            
            #titleLabel {
                color: #00d9ff;
                font-size: 24px;
                font-weight: bold;
            }
            
            #statusIndicator {
                color: #888;
                font-size: 12px;
            }
            
            QGroupBox {
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                border: 2px solid #2d2d44;
                border-radius: 12px;
                margin-top: 15px;
                padding-top: 15px;
                background: rgba(22, 33, 62, 0.5);
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
                color: #00d9ff;
            }
            
            QListWidget {
                background: rgba(15, 15, 35, 0.8);
                color: #ffffff;
                border: 1px solid #2d2d44;
                border-radius: 8px;
                padding: 5px;
                font-size: 13px;
            }
            
            QListWidget::item {
                padding: 10px 8px;
                border-radius: 6px;
                margin: 2px 0;
            }
            
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00d9ff, stop:1 #0099cc);
                color: #000;
            }
            
            QListWidget::item:hover:!selected {
                background: rgba(0, 217, 255, 0.1);
            }
            
            QTreeWidget {
                background: rgba(15, 15, 35, 0.8);
                color: #ffffff;
                border: 1px solid #2d2d44;
                border-radius: 8px;
                font-size: 12px;
            }
            
            QTreeWidget::item {
                padding: 8px 4px;
                border-bottom: 1px solid #1a1a2e;
            }
            
            QTreeWidget::item:selected {
                background: rgba(0, 217, 255, 0.2);
            }
            
            QHeaderView::section {
                background: #16213e;
                color: #00d9ff;
                padding: 8px;
                border: none;
                font-weight: bold;
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
                    stop:0 #00d9ff, stop:1 #00ff88);
                color: #000;
            }
            
            #primaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00eeff, stop:1 #00ff99);
            }
            
            #secondaryBtn {
                background: #2d2d44;
                color: #ffffff;
            }
            
            #secondaryBtn:hover {
                background: #3d3d54;
            }
            
            #installBtn {
                background: #ff6b6b;
                color: white;
                padding: 4px 12px;
                font-size: 11px;
                border-radius: 4px;
            }
            
            #installBtn:hover {
                background: #ff8787;
            }
            
            #installedLabel {
                color: #00ff88;
            }
            
            #missingLabel {
                color: #ff6b6b;
            }
            
            #unknownLabel {
                color: #ffd93d;
            }
            
            QStatusBar {
                background: #0f0f23;
                color: #666;
                border-top: 1px solid #2d2d44;
            }
            
            QScrollBar:vertical {
                background: #1a1a2e;
                width: 10px;
                border-radius: 5px;
            }
            
            QScrollBar::handle:vertical {
                background: #3d3d54;
                border-radius: 5px;
                min-height: 30px;
            }
            
            QScrollBar::handle:vertical:hover {
                background: #00d9ff;
            }
        """
    
    def _create_workflow_panel(self):
        group = QGroupBox("📁 Workflows")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        self.workflow_list = QListWidget()
        self.workflow_list.currentItemChanged.connect(self.on_workflow_selected)
        layout.addWidget(self.workflow_list)
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.clicked.connect(self.refresh_workflows)
        layout.addWidget(refresh_btn)
        
        return group
    
    def _create_dependency_panel(self):
        group = QGroupBox("📦 Dependencies")
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        
        # Nodes section
        nodes_header = QHBoxLayout()
        nodes_label = QLabel("🔧 Custom Nodes")
        nodes_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #00d9ff;")
        nodes_header.addWidget(nodes_label)
        nodes_header.addStretch()
        layout.addLayout(nodes_header)
        
        self.nodes_tree = QTreeWidget()
        self.nodes_tree.setHeaderLabels(["Node Package", "Status", "Action"])
        self.nodes_tree.setColumnWidth(0, 250)
        self.nodes_tree.setColumnWidth(1, 120)
        self.nodes_tree.setColumnWidth(2, 100)
        self.nodes_tree.setRootIsDecorated(False)
        layout.addWidget(self.nodes_tree)
        
        # Models section
        models_header = QHBoxLayout()
        models_label = QLabel("🧠 Models")
        models_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #00d9ff;")
        models_header.addWidget(models_label)
        models_header.addStretch()
        layout.addLayout(models_header)
        
        self.models_tree = QTreeWidget()
        self.models_tree.setHeaderLabels(["Model File", "Status", "Action"])
        self.models_tree.setColumnWidth(0, 250)
        self.models_tree.setColumnWidth(1, 120)
        self.models_tree.setColumnWidth(2, 100)
        self.models_tree.setRootIsDecorated(False)
        layout.addWidget(self.models_tree)
        
        return group
    
    def refresh_workflows(self):
        self.workflow_list.clear()
        workflows = scan_workflows()
        for wf in workflows:
            item = QListWidgetItem(f"📄 {wf}")
            item.setData(Qt.UserRole, wf)
            self.workflow_list.addItem(item)
        self.status_bar.showMessage(f"Found {len(workflows)} workflow(s)")
    
    def on_workflow_selected(self, current, previous):
        if not current:
            return
        filename = current.data(Qt.UserRole)
        self.check_dependencies(filename)
    
    def check_dependencies(self, filename):
        deps = check_workflow_dependencies(filename)
        
        self.nodes_tree.clear()
        self.pending_installs = []
        
        seen_folders = set()
        for node in deps["nodes"]:
            folder = node["folder"]
            if folder in seen_folders or folder == "Builtin":
                continue
            seen_folders.add(folder)
            
            item = QTreeWidgetItem()
            item.setText(0, folder)
            
            if folder == "Unknown":
                item.setText(1, "⚠️ Unknown")
                item.setForeground(1, QColor("#ffd93d"))
            elif node["installed"]:
                item.setText(1, "✅ Installed")
                item.setForeground(1, QColor("#00ff88"))
            else:
                item.setText(1, "❌ Missing")
                item.setForeground(1, QColor("#ff6b6b"))
                if node["url"]:
                    self.pending_installs.append(node["url"])
                    # Add install button
                    btn = QPushButton("Install")
                    btn.setObjectName("installBtn")
                    btn.setFixedSize(70, 26)
                    btn.clicked.connect(lambda checked, url=node["url"]: self.install_single_node(url))
                    self.nodes_tree.setItemWidget(item, 2, btn)
            
            self.nodes_tree.addTopLevelItem(item)
        
        self.models_tree.clear()
        seen_models = set()
        for model in deps["models"]:
            name = model["name"]
            if name in seen_models:
                continue
            seen_models.add(name)
            
            item = QTreeWidgetItem()
            item.setText(0, name if len(name) < 35 else name[:32] + "...")
            item.setToolTip(0, name)
            
            if model["installed"]:
                item.setText(1, "✅ Found")
                item.setForeground(1, QColor("#00ff88"))
            else:
                item.setText(1, "❌ Missing")
                item.setForeground(1, QColor("#ff6b6b"))
            
            self.models_tree.addTopLevelItem(item)
        
        missing_nodes = len([n for n in deps["nodes"] if not n["installed"] and n["folder"] not in ("Builtin", "Unknown")])
        missing_models = sum(1 for m in deps["models"] if not m["installed"])
        self.status_bar.showMessage(f"{filename}: {missing_nodes} missing nodes, {missing_models} missing models")
    
    def install_single_node(self, url):
        self.status_bar.showMessage(f"Installing {url.split('/')[-1]}...")
        QApplication.processEvents()
        
        success, msg = install_node(url)
        if success:
            QMessageBox.information(self, "Success", msg)
            # Refresh current selection
            current = self.workflow_list.currentItem()
            if current:
                self.check_dependencies(current.data(Qt.UserRole))
        else:
            QMessageBox.warning(self, "Error", msg)
    
    def install_all_missing(self):
        if not self.pending_installs:
            QMessageBox.information(self, "Info", "No missing nodes to install!")
            return
        
        reply = QMessageBox.question(self, "Confirm", 
            f"Install {len(self.pending_installs)} missing node(s)?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            for url in self.pending_installs:
                self.status_bar.showMessage(f"Installing {url.split('/')[-1]}...")
                QApplication.processEvents()
                install_node(url)
            
            QMessageBox.information(self, "Done", "Installation complete!")
            current = self.workflow_list.currentItem()
            if current:
                self.check_dependencies(current.data(Qt.UserRole))
    
    def check_all(self):
        workflows = scan_workflows()
        total_missing = set()
        
        for wf in workflows:
            deps = check_workflow_dependencies(wf)
            for n in deps["nodes"]:
                if not n["installed"] and n["folder"] not in ("Builtin", "Unknown"):
                    total_missing.add(n["folder"])
        
        if total_missing:
            QMessageBox.warning(self, "Missing Dependencies", 
                f"Missing across all workflows:\n\n{chr(10).join(sorted(total_missing))}")
        else:
            QMessageBox.information(self, "All Good!", "All known dependencies are installed! ✅")
    
    def update_system_status(self):
        status = get_system_status()
        parts = []
        
        if status["comfyui_installed"]:
            parts.append("ComfyUI ✅")
        
        if status["python_version"]:
            parts.append(f"Python {status['python_version']}")
        
        if status["cuda_available"] and status["gpu_name"]:
            parts.append(f"🎮 {status['gpu_name']}")
        
        self.status_label.setText(" | ".join(parts))
    
    def run_comfy(self):
        if run_comfyui():
            QMessageBox.information(self, "ComfyUI", "ComfyUI is starting!\n\nOpen http://localhost:8188")
        else:
            QMessageBox.warning(self, "Error", "Failed to start ComfyUI")
