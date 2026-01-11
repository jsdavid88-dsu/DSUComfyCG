"""
DSUComfyCG Manager - Main Window UI
PySide6-based desktop application for managing ComfyUI workflows and dependencies.
"""

import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QStatusBar, QMessageBox, QProgressBar,
    QGroupBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIcon

from core.checker import (
    scan_workflows, check_workflow_dependencies, get_system_status,
    install_node, run_comfyui
)


class InstallWorker(QThread):
    """Background worker for installing nodes."""
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
        self.resize(900, 600)
        self.setMinimumSize(700, 500)
        
        # Apply dark theme
        self.setStyleSheet(self._get_stylesheet())
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Header
        header = QLabel("DSUComfyCG Manager")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #4CAF50; margin-bottom: 10px;")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)
        
        # Splitter for left/right panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, stretch=1)
        
        # Left panel - Workflows
        left_panel = self._create_workflow_panel()
        splitter.addWidget(left_panel)
        
        # Right panel - Dependencies
        right_panel = self._create_dependency_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([300, 600])
        
        # Bottom buttons
        btn_layout = QHBoxLayout()
        
        self.check_btn = QPushButton("🔄 Check All")
        self.check_btn.clicked.connect(self.check_all)
        btn_layout.addWidget(self.check_btn)
        
        btn_layout.addStretch()
        
        self.run_btn = QPushButton("▶ Run ComfyUI")
        self.run_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px 30px;")
        self.run_btn.clicked.connect(self.run_comfy)
        btn_layout.addWidget(self.run_btn)
        
        main_layout.addLayout(btn_layout)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Initialize
        self.refresh_workflows()
        self.update_system_status()
    
    def _get_stylesheet(self):
        return """
            QMainWindow { background-color: #1e1e1e; }
            QLabel { color: #ffffff; }
            QListWidget, QTreeWidget { 
                background-color: #2d2d2d; 
                color: #ffffff; 
                border: 1px solid #3d3d3d;
                border-radius: 5px;
            }
            QListWidget::item:selected, QTreeWidget::item:selected { 
                background-color: #4CAF50; 
            }
            QListWidget::item:hover, QTreeWidget::item:hover { 
                background-color: #3d3d3d; 
            }
            QPushButton { 
                background-color: #3d3d3d; 
                color: #ffffff; 
                border: none; 
                padding: 8px 16px; 
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #4d4d4d; }
            QPushButton:pressed { background-color: #5d5d5d; }
            QGroupBox { 
                color: #ffffff; 
                border: 1px solid #3d3d3d; 
                border-radius: 5px; 
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                left: 10px; 
                padding: 0 5px;
            }
            QStatusBar { background-color: #2d2d2d; color: #aaaaaa; }
        """
    
    def _create_workflow_panel(self):
        group = QGroupBox("📁 Workflows")
        layout = QVBoxLayout(group)
        
        self.workflow_list = QListWidget()
        self.workflow_list.currentItemChanged.connect(self.on_workflow_selected)
        layout.addWidget(self.workflow_list)
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_workflows)
        layout.addWidget(refresh_btn)
        
        return group
    
    def _create_dependency_panel(self):
        group = QGroupBox("📦 Dependencies")
        layout = QVBoxLayout(group)
        
        # Nodes section
        nodes_label = QLabel("🔧 Custom Nodes")
        nodes_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        layout.addWidget(nodes_label)
        
        self.nodes_tree = QTreeWidget()
        self.nodes_tree.setHeaderLabels(["Node", "Status", "Action"])
        self.nodes_tree.setColumnWidth(0, 200)
        self.nodes_tree.setColumnWidth(1, 100)
        layout.addWidget(self.nodes_tree)
        
        # Models section
        models_label = QLabel("🧠 Models")
        models_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(models_label)
        
        self.models_tree = QTreeWidget()
        self.models_tree.setHeaderLabels(["Model", "Status", "Action"])
        self.models_tree.setColumnWidth(0, 200)
        self.models_tree.setColumnWidth(1, 100)
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
        
        # Update nodes tree
        self.nodes_tree.clear()
        for node in deps["nodes"]:
            item = QTreeWidgetItem()
            item.setText(0, node["folder"])
            
            if node["folder"] == "Builtin":
                item.setText(1, "Built-in")
                item.setForeground(1, Qt.gray)
            elif node["installed"]:
                item.setText(1, "✅ Installed")
                item.setForeground(1, Qt.green)
            else:
                item.setText(1, "❌ Missing")
                item.setForeground(1, Qt.red)
                if node["url"]:
                    item.setData(0, Qt.UserRole, node["url"])
            
            self.nodes_tree.addTopLevelItem(item)
        
        # Update models tree
        self.models_tree.clear()
        for model in deps["models"]:
            item = QTreeWidgetItem()
            item.setText(0, model["name"])
            
            if model["installed"]:
                item.setText(1, "✅ Found")
                item.setForeground(1, Qt.green)
            else:
                item.setText(1, "❌ Missing")
                item.setForeground(1, Qt.red)
            
            self.models_tree.addTopLevelItem(item)
        
        # Count missing
        missing_nodes = sum(1 for n in deps["nodes"] if not n["installed"] and n["folder"] != "Builtin" and n["folder"] != "Unknown")
        missing_models = sum(1 for m in deps["models"] if not m["installed"])
        
        self.status_bar.showMessage(f"Checked {filename}: {missing_nodes} missing nodes, {missing_models} missing models")
    
    def check_all(self):
        """Check all workflows and summarize."""
        workflows = scan_workflows()
        total_missing_nodes = set()
        total_missing_models = set()
        
        for wf in workflows:
            deps = check_workflow_dependencies(wf)
            for n in deps["nodes"]:
                if not n["installed"] and n["folder"] not in ("Builtin", "Unknown"):
                    total_missing_nodes.add(n["folder"])
            for m in deps["models"]:
                if not m["installed"]:
                    total_missing_models.add(m["name"])
        
        msg = f"Total: {len(total_missing_nodes)} missing nodes, {len(total_missing_models)} missing models"
        self.status_bar.showMessage(msg)
        
        if total_missing_nodes or total_missing_models:
            QMessageBox.warning(self, "Dependencies Missing", 
                f"Missing Nodes:\n{', '.join(total_missing_nodes) or 'None'}\n\n"
                f"Missing Models:\n{', '.join(total_missing_models) or 'None'}")
        else:
            QMessageBox.information(self, "All Good!", "All dependencies are satisfied! ✅")
    
    def update_system_status(self):
        status = get_system_status()
        parts = []
        
        if status["comfyui_installed"]:
            parts.append("ComfyUI: ✅")
        else:
            parts.append("ComfyUI: ❌")
        
        if status["python_version"]:
            parts.append(f"Python: {status['python_version']}")
        
        if status["cuda_available"]:
            parts.append("CUDA: ✅")
            if status["gpu_name"]:
                parts.append(f"GPU: {status['gpu_name']}")
        else:
            parts.append("CUDA: ❌")
        
        self.status_bar.showMessage(" | ".join(parts))
    
    def run_comfy(self):
        if run_comfyui():
            QMessageBox.information(self, "ComfyUI", "ComfyUI is starting! Check http://localhost:8188")
        else:
            QMessageBox.warning(self, "Error", "Failed to start ComfyUI")
