"""
DSUComfyCG Manager - Main Window UI (v7 - With Download Queue)
"""

import sys
import os
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QStatusBar, QMessageBox, QProgressBar,
    QGroupBox, QFrame, QApplication, QDialog, QScrollArea, QMenu,
    QTabWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QAction, QCursor

from core.checker import (
    scan_workflows, check_workflow_dependencies, get_system_status,
    install_node, run_comfyui, sync_workflows, fetch_node_db, NODE_DB,
    download_model, load_model_db, MODEL_DB,
    check_for_updates, perform_update, get_local_version,
    check_comfyui_version, check_custom_nodes_updates, 
    update_comfyui, update_all_custom_nodes, get_system_health_report,
    save_url_to_model_db, guess_model_folder
)
from ui.url_input_dialog import ModelUrlInputDialog
from ui.workflow_validator import WorkflowValidatorDialog


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
    item_progress = Signal(str, object, object)  # name, downloaded, total_bytes (use object for large values)
    item_finished = Signal(str, bool, str, str)  # name, success, message, warning (optional)
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
            success, msg, warn = install_node(url)
            self.item_finished.emit(f"Node: {name}", success, msg, warn or "")
        
        # Download models
        for name, url in self.models:
            if self.is_cancelled:
                break
            index += 1
            self.item_started.emit(f"Model: {name[:30]}...", index, total)
            
            def progress_cb(downloaded, total_bytes):
                self.item_progress.emit(name, downloaded, total_bytes)
            
            success, msg = download_model(name, progress_cb)
            self.item_finished.emit(f"Model: {name[:30]}...", success, msg, "")
        
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
        
        # System Status Panel (shown after startup)
        self.status_panel = self._create_system_status_panel()
        self.status_panel.hide()  # Hidden until startup complete
        main_layout.addWidget(self.status_panel)
        
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
        
        # Version label
        self.version_label = QLabel()
        self.version_label.setObjectName("versionLabel")
        self.version_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.version_label)
        
        layout.addStretch()
        
        # Update button (hidden by default)
        self.update_btn = QPushButton("🔄 Update Available")
        self.update_btn.setObjectName("updateBtn")
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.update_btn.clicked.connect(self.handle_update)
        self.update_btn.hide()  # Hidden until update check
        layout.addWidget(self.update_btn)
        
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
    
    def _create_system_status_panel(self):
        """Create system status panel showing ComfyUI/nodes/models status."""
        frame = QFrame()
        frame.setObjectName("statusPanel")
        frame.setStyleSheet("""
            #statusPanel {
                background: rgba(20, 20, 40, 0.9);
                border: 1px solid #2a2a4e;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        
        # Title
        title = QLabel("📊 시스템 상태")
        title.setStyleSheet("color: #00ffcc; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        
        # Status rows
        status_grid = QVBoxLayout()
        status_grid.setSpacing(6)
        
        # ComfyUI row
        comfy_row = QHBoxLayout()
        self.comfy_label = QLabel("ComfyUI")
        self.comfy_label.setStyleSheet("color: #fff; font-size: 12px;")
        self.comfy_status = QLabel("체크 중...")
        self.comfy_status.setStyleSheet("color: #888; font-size: 11px;")
        self.comfy_update_btn = QPushButton("업데이트")
        self.comfy_update_btn.setStyleSheet("""
            QPushButton {
                background: #4CAF50; color: white; border: none;
                padding: 4px 8px; border-radius: 3px; font-size: 10px;
            }
            QPushButton:hover { background: #45a049; }
            QPushButton:disabled { background: #555; }
        """)
        self.comfy_update_btn.clicked.connect(self.handle_comfy_update)
        self.comfy_update_btn.hide()
        comfy_row.addWidget(self.comfy_label)
        comfy_row.addWidget(self.comfy_status)
        comfy_row.addStretch()
        comfy_row.addWidget(self.comfy_update_btn)
        status_grid.addLayout(comfy_row)
        
        # Custom Nodes row
        nodes_row = QHBoxLayout()
        self.nodes_label = QLabel("커스텀 노드")
        self.nodes_label.setStyleSheet("color: #fff; font-size: 12px;")
        self.nodes_status = QLabel("체크 중...")
        self.nodes_status.setStyleSheet("color: #888; font-size: 11px;")
        self.nodes_update_btn = QPushButton("전체 업데이트")
        self.nodes_update_btn.setStyleSheet("""
            QPushButton {
                background: #4CAF50; color: white; border: none;
                padding: 4px 8px; border-radius: 3px; font-size: 10px;
            }
            QPushButton:hover { background: #45a049; }
            QPushButton:disabled { background: #555; }
        """)
        self.nodes_update_btn.clicked.connect(self.handle_nodes_update)
        self.nodes_update_btn.hide()
        nodes_row.addWidget(self.nodes_label)
        nodes_row.addWidget(self.nodes_status)
        nodes_row.addStretch()
        nodes_row.addWidget(self.nodes_update_btn)
        status_grid.addLayout(nodes_row)
        
        # Models row
        models_row = QHBoxLayout()
        self.models_label = QLabel("모델")
        self.models_label.setStyleSheet("color: #fff; font-size: 12px;")
        self.models_status = QLabel("체크 중...")
        self.models_status.setStyleSheet("color: #888; font-size: 11px;")
        models_row.addWidget(self.models_label)
        models_row.addWidget(self.models_status)
        models_row.addStretch()
        status_grid.addLayout(models_row)
        
        layout.addLayout(status_grid)
        
        return frame
    
    def _create_workflow_panel(self):
        group = QGroupBox("Workflows")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        # Tabs for Custom vs Standard
        self.wf_tabs = QTabWidget()
        
        # 1. Custom Workflows Tab
        custom_tab = QWidget()
        custom_layout = QVBoxLayout(custom_tab)
        custom_layout.setContentsMargins(0, 5, 0, 0)
        
        self.workflow_list = QListWidget()
        self.workflow_list.currentItemChanged.connect(self.on_workflow_selected)
        custom_layout.addWidget(self.workflow_list)
        
        # Custom Sync/Refresh
        btn_layout = QHBoxLayout()
        sync_btn = QPushButton("Sync")
        sync_btn.setObjectName("smallBtn")
        sync_btn.clicked.connect(self.sync_workflows_ui)
        btn_layout.addWidget(sync_btn)
        
        validate_btn = QPushButton("Validate")
        validate_btn.setObjectName("smallBtn")
        validate_btn.setToolTip("선택한 워크플로우의 의존성을 검증합니다")
        validate_btn.clicked.connect(self.validate_current_workflow)
        btn_layout.addWidget(validate_btn)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("smallBtn")
        refresh_btn.clicked.connect(self.refresh_workflows)
        btn_layout.addWidget(refresh_btn)
        custom_layout.addLayout(btn_layout)
        
        self.wf_tabs.addTab(custom_tab, "My Workflows")
        
        # 2. Standard Packs Tab
        pack_tab = QWidget()
        pack_layout = QVBoxLayout(pack_tab)
        pack_layout.setContentsMargins(0, 5, 0, 0)
        
        self.pack_list = QListWidget()
        self.pack_list.setAlternatingRowColors(True)
        # self.pack_list.itemClicked.connect(self.on_pack_selected) # Not needed yet
        pack_layout.addWidget(self.pack_list)
        
        # Pack Install Button
        pack_btn_layout = QHBoxLayout()
        install_pack_btn = QPushButton("Install Selected Pack")
        install_pack_btn.setObjectName("primaryBtn")
        install_pack_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                border: 1px solid #10b981;
                font-size: 13px; padding: 10px;
            }
            QPushButton:hover { background: #34d399; }
        """)
        install_pack_btn.clicked.connect(self.install_standard_pack)
        pack_btn_layout.addWidget(install_pack_btn)
        pack_layout.addLayout(pack_btn_layout)
        
        self.wf_tabs.addTab(pack_tab, "DSU Standard")
        
        layout.addWidget(self.wf_tabs)
        
        # Load standard packs
        self.load_standard_packs()
        
        return group

    def load_standard_packs(self):
        """Load DSU Standard Packs from manifest."""
        manifest_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "standard_pack_manifest.json")
        if not os.path.exists(manifest_path):
            return

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.pack_list.clear()
            for wf in data.get("workflows", []):
                item = QListWidgetItem()
                item.setText(f"[{wf['category']}] {wf['name']}")
                item.setToolTip(wf['description'])
                item.setData(Qt.UserRole, wf)  # Store full wf data
                self.pack_list.addItem(item)
                
        except Exception as e:
            print(f"Error loading pack manifest: {e}")

    def install_standard_pack(self):
        """Install selected standard pack."""
        item = self.pack_list.currentItem()
        if not item:
            QMessageBox.warning(self, "선택 필요", "설치할 팩을 선택해주세요.")
            return
            
        wf_data = item.data(Qt.UserRole)
        confirm = QMessageBox.question(
            self, "설치 확인",
            f"'{wf_data['name']}' 패키지를 설치하시겠습니까?\n\n"
            f"설명: {wf_data['description']}\n"
            "설치 후 자동으로 의존성 검사를 시작합니다.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm != QMessageBox.Yes:
            return
            
        # Copy source json to workflows folder
        src_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "workflows", wf_data['file'])
        target_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ComfyUI", "user", "default", "workflows")
        os.makedirs(target_dir, exist_ok=True)
        
        target_file = os.path.join(target_dir, wf_data['file'])
        
        try:
            if not os.path.exists(src_file):
                 QMessageBox.critical(self, "오류", f"소스 파일을 찾을 수 없습니다:\n{src_file}")
                 return
                 
            shutil.copy2(src_file, target_file)
            
            # Switch to 'My Workflows' and select the new file
            self.refresh_workflows()
            self.wf_tabs.setCurrentIndex(0)
            
            # Find and select the item
            items = self.workflow_list.findItems(wf_data['file'], Qt.MatchContains)
            if items:
                self.workflow_list.setCurrentItem(items[0])
                # Trigger validation automatically
                self.validate_current_workflow()
                
            QMessageBox.information(self, "성공", f"'{wf_data['name']}' 설치가 완료되었습니다.")
            
        except Exception as e:
            QMessageBox.critical(self, "설치 실패", f"오류 발생: {str(e)}")
    
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
        self.nodes_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.nodes_tree.customContextMenuRequested.connect(self.show_nodes_context_menu)
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
        self.models_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.models_tree.customContextMenuRequested.connect(self.show_models_context_menu)
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
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1b26, stop:1 #24283b);
            }
            #headerFrame {
                background: rgba(30, 32, 48, 0.8);
                border-radius: 16px;
                padding: 24px;
                border: 1px solid rgba(115, 218, 202, 0.2);
            }
            #titleLabel { color: #7aa2f7; font-size: 28px; font-weight: 800; font-family: 'Segoe UI', sans-serif; }
            #systemInfo { color: #565f89; font-size: 13px; font-weight: 500; }
            
            #startupFrame {
                background: rgba(122, 162, 247, 0.1);
                border: 1px solid #7aa2f7;
                border-radius: 12px;
            }
            #startupLabel { color: #bb9af7; font-size: 15px; font-weight: 600; }
            #startupProgress {
                background: #1a1b26; border: none; border-radius: 6px; height: 8px;
            }
            #startupProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7aa2f7, stop:1 #bb9af7);
                border-radius: 6px;
            }
            
            QGroupBox {
                color: #c0caf5; font-size: 15px; font-weight: 700;
                border: 1px solid #414868; border-radius: 12px;
                margin-top: 24px; padding-top: 20px;
                background: rgba(36, 40, 59, 0.6);
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 16px; padding: 0 8px; color: #7dcfff;
            }
            
            #sectionLabel { color: #7dcfff; font-size: 13px; font-weight: 700; }
            #countLabel { color: #565f89; font-size: 12px; font-weight: 600; }
            #queueSummary { color: #9aa5ce; font-size: 13px; padding: 12px; }
            
            #queueProgressFrame {
                background: rgba(187, 154, 247, 0.1);
                border: 1px solid #414868;
                border-radius: 10px;
            }
            #queueProgressBar {
                background: #1a1b26; border: 1px solid #414868;
                border-radius: 8px; height: 22px; text-align: center; color: #fff; font-weight: bold;
            }
            #queueProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #bb9af7, stop:1 #f7768e);
                border-radius: 7px;
            }
            
            QListWidget, QTreeWidget {
                background: rgba(26, 27, 38, 0.95); color: #c0caf5;
                border: 1px solid #414868; border-radius: 10px; font-size: 13px; outline: none;
            }
            QListWidget::item { padding: 10px 14px; border-radius: 6px; margin: 4px 6px; background: transparent; }
            QListWidget::item:selected {
                background: rgba(122, 162, 247, 0.2); 
                color: #7aa2f7; 
                border: 1px solid #7aa2f7;
            }
            QListWidget::item:hover {
                background: rgba(122, 162, 247, 0.1);
            }
            QTreeWidget::item { padding: 8px 6px; border-bottom: 1px solid #24283b; }
            QHeaderView::section {
                background: #24283b; color: #7dcfff; padding: 10px;
                border: none; font-weight: 700; font-size: 12px; text-transform: uppercase;
            }
            
            #queueList::item { padding: 8px 12px; font-size: 12px; }
            
            QPushButton { 
                border: none; border-radius: 8px; padding: 10px 18px; 
                font-size: 13px; font-weight: 700; font-family: 'Segoe UI', sans-serif;
            }
            
            #primaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7aa2f7, stop:1 #3d59a1);
                color: #ffffff; font-size: 15px; padding: 14px 40px;
                border: 1px solid #7aa2f7;
            }
            #primaryBtn:hover { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #89b4fa, stop:1 #587ace);
                border-color: #bb9af7;
            }
            #primaryBtn:pressed { background: #3d59a1; }
            #primaryBtn:disabled { background: #2f334d; color: #565f89; border: 1px solid #414868; }
            
            #secondaryBtn { background: #24283b; color: #c0caf5; border: 1px solid #414868; }
            #secondaryBtn:hover { background: #414868; color: #fff; border-color: #565f89; }
            
            #smallBtn { background: #24283b; color: #9aa5ce; padding: 8px 14px; font-size: 12px; border: 1px solid #414868; }
            #smallBtn:hover { background: #414868; color: #c0caf5; border-color: #7aa2f7; }
            
            #installBtn { 
                background: rgba(247, 118, 142, 0.2); color: #f7768e; 
                padding: 6px 12px; font-size: 12px; border-radius: 6px; border: 1px solid rgba(247, 118, 142, 0.5);
            }
            #installBtn:hover { background: rgba(247, 118, 142, 0.4); }
            
            #downloadBtn { 
                background: rgba(122, 162, 247, 0.2); color: #7aa2f7; 
                padding: 6px 12px; font-size: 12px; border-radius: 6px; border: 1px solid rgba(122, 162, 247, 0.5);
            }
            #downloadBtn:hover { background: rgba(122, 162, 247, 0.4); }
            
            #addQueueBtn { 
                background: rgba(187, 154, 247, 0.2); color: #bb9af7; 
                padding: 6px 12px; font-size: 12px; border-radius: 6px; border: 1px solid rgba(187, 154, 247, 0.5);
            }
            #addQueueBtn:hover { background: rgba(187, 154, 247, 0.4); }
            
            #urlInputBtn { 
                background: rgba(224, 175, 104, 0.2); color: #e0af68; 
                padding: 6px 12px; font-size: 12px; border-radius: 6px; border: 1px solid rgba(224, 175, 104, 0.5);
            }
            #urlInputBtn:hover { background: rgba(224, 175, 104, 0.4); }
        """
        
    def show_nodes_context_menu(self, position):
        """Show context menu for nodes tree."""
        item = self.nodes_tree.itemAt(position)
        if not item:
            return
            
        menu = QMenu(self.nodes_tree)
        menu.setStyleSheet("""
            QMenu { background-color: #2a2a3e; color: #e0e0e0; border: 1px solid #3a3a5e; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background-color: #5865f2; color: white; }
        """)
        
        copy_action = QAction("Copy Name", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(item.text(0)))
        menu.addAction(copy_action)
        
        menu.exec(self.nodes_tree.viewport().mapToGlobal(position))
        
    def show_models_context_menu(self, position):
        """Show context menu for models tree."""
        item = self.models_tree.itemAt(position)
        if not item:
            return
            
        menu = QMenu(self.models_tree)
        menu.setStyleSheet("""
            QMenu { background-color: #2a2a3e; color: #e0e0e0; border: 1px solid #3a3a5e; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background-color: #5865f2; color: white; }
        """)
        
        copy_action = QAction("Copy Name", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(item.text(0)))
        menu.addAction(copy_action)
        
        menu.exec(self.models_tree.viewport().mapToGlobal(position))
    
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
        self.status_panel.show()  # Show system status panel
        self.is_ready = True
        self.run_btn.setEnabled(True)
        
        self.refresh_workflows()
        self.update_system_status()
        self.refresh_system_status()  # Populate status panel
        
        # Check for updates
        self.check_version_updates()
        
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
    
    def check_version_updates(self):
        """Check for app updates and update UI."""
        local_version = get_local_version()
        self.version_label.setText(f"v{local_version}")
        
        # Check in background (non-blocking)
        try:
            update_available, local_ver, remote_ver, error = check_for_updates()
            
            if error:
                self.version_label.setToolTip(f"Update check failed: {error}")
            elif update_available:
                self.update_btn.setText(f"🔄 Update to v{remote_ver}")
                self.update_btn.setToolTip(f"Current: v{local_ver} → Latest: v{remote_ver}")
                self.update_btn.show()
                self.status_bar.showMessage(f"Update available: v{remote_ver}", 5000)
            else:
                self.version_label.setToolTip("You're on the latest version")
        except Exception as e:
            self.version_label.setToolTip(f"Update check error: {e}")
    
    def handle_update(self):
        """Handle update button click."""
        reply = QMessageBox.question(
            self,
            "Update DSUComfyCG",
            "This will update DSUComfyCG Manager from GitHub.\n\n"
            "The app will need to restart after updating.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.update_btn.setEnabled(False)
            self.update_btn.setText("Updating...")
            QApplication.processEvents()
            
            success, message = perform_update()
            
            if success:
                QMessageBox.information(self, "Update Complete", message)
                # Suggest restart
                restart_reply = QMessageBox.question(
                    self,
                    "Restart Required",
                    "Update complete! Restart the app to apply changes?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if restart_reply == QMessageBox.Yes:
                    QApplication.quit()
            else:
                QMessageBox.warning(self, "Update Failed", message)
                self.update_btn.setEnabled(True)
                self.update_btn.setText("🔄 Update Available")
    
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
    
    def validate_current_workflow(self):
        """현재 선택된 워크플로우의 의존성을 검증합니다."""
        current = self.workflow_list.currentItem()
        if not current:
            QMessageBox.warning(self, "워크플로우 선택", "먼저 워크플로우를 선택하세요.")
            return
        
        filename = current.data(Qt.UserRole)
        dialog = WorkflowValidatorDialog(filename, self)
        
        if dialog.exec() == QDialog.Accepted and dialog.is_resolved():
            self.status_bar.showMessage(f"✓ {filename} 의존성 검증 완료")
            # Refresh dependencies display
            self.check_dependencies(filename)
        else:
            self.status_bar.showMessage(f"✗ {filename} 검증 취소됨")
    
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
                item.setText(1, "설치됨")
                item.setForeground(1, QColor("#00ffcc"))
                found += 1
            elif model["url"]:
                item.setText(1, "다운로드 대기")
                item.setForeground(1, QColor("#7aa2f7"))
                btn = QPushButton("다운로드")
                btn.setObjectName("downloadBtn")
                btn.setFixedSize(60, 24)
                btn.clicked.connect(lambda c, m=model: self.add_model_to_queue(m))
                self.models_tree.setItemWidget(item, 2, btn)
                missing_m += 1
            else:
                item.setText(1, "Unknown")
                item.setForeground(1, QColor("#ffd93d"))
                # Add button to input URL manually
                btn = QPushButton("URL입력")
                btn.setObjectName("urlInputBtn")
                btn.setFixedSize(60, 24)
                btn.clicked.connect(lambda c, n=name: self.show_url_input_dialog(n))
                self.models_tree.setItemWidget(item, 2, btn)
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
    
    def show_url_input_dialog(self, model_name):
        """Show dialog for user to input download URL for unknown model."""
        # Guess folder from model name
        folder = guess_model_folder(model_name)
        
        dialog = ModelUrlInputDialog(model_name, folder, self)
        if dialog.exec() == QDialog.Accepted:
            url, save_to_db = dialog.get_result()
            if url:
                # Save to DB if requested
                if save_to_db:
                    success, msg = save_url_to_model_db(model_name, url, folder)
                    if success:
                        self.status_bar.showMessage(f"Saved {model_name} to DB")
                
                # Add to queue
                self.add_model_to_queue(model_name, url)
                
                # Refresh dependencies display
                current = self.workflow_list.currentItem()
                if current:
                    self.check_dependencies(current.data(Qt.UserRole))
    
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
    
    def on_queue_item_finished(self, name, success, message, warning):
        status = "✓" if success else "✗"
        display_msg = f"{status} {name}: {message}"
        if warning:
            display_msg += f" ⚠️ {warning[:50]}"
        self.status_bar.showMessage(display_msg)
    
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
            parts.append(status["gpu_name"][:30])
        parts.append(f"DB: {status['node_db_size']}")
        self.system_info.setText(" | ".join(parts))
    
    def run_comfy(self):
        if run_comfyui():
            QMessageBox.information(self, "ComfyUI", "ComfyUI is starting!\n\nhttp://localhost:8188")
        else:
            QMessageBox.warning(self, "Error", "Failed to start ComfyUI")
    
    def refresh_system_status(self):
        """Refresh system status panel with current info."""
        # Check ComfyUI
        try:
            comfy_info = check_comfyui_version()
            if comfy_info["error"]:
                self.comfy_status.setText(f"⚠️ {comfy_info['error']}")
                self.comfy_status.setStyleSheet("color: #ff6b6b;")
            elif comfy_info["update_available"]:
                self.comfy_status.setText(f"⚠️ {comfy_info['commits_behind']}개 커밋 뒤처짐")
                self.comfy_status.setStyleSheet("color: #ffcc00;")
                self.comfy_update_btn.show()
            else:
                self.comfy_status.setText(f"✅ 최신 ({comfy_info['current_commit']})")
                self.comfy_status.setStyleSheet("color: #4CAF50;")
                self.comfy_update_btn.hide()
        except Exception as e:
            self.comfy_status.setText(f"❌ 오류: {e}")
            self.comfy_status.setStyleSheet("color: #ff6b6b;")
        
        # Check Custom Nodes
        try:
            nodes_info = check_custom_nodes_updates()
            total = len(nodes_info)
            updatable = len([n for n in nodes_info if n["update_available"]])
            
            if updatable > 0:
                self.nodes_status.setText(f"⚠️ {total}개 중 {updatable}개 업데이트 가능")
                self.nodes_status.setStyleSheet("color: #ffcc00;")
                self.nodes_update_btn.show()
            else:
                self.nodes_status.setText(f"✅ {total}개 모두 최신")
                self.nodes_status.setStyleSheet("color: #4CAF50;")
                self.nodes_update_btn.hide()
        except Exception as e:
            self.nodes_status.setText(f"❌ 오류: {e}")
            self.nodes_status.setStyleSheet("color: #ff6b6b;")
        
        # Models count
        self.models_status.setText(f"✅ {len(MODEL_DB)}개 등록됨")
        self.models_status.setStyleSheet("color: #4CAF50;")
    
    def handle_comfy_update(self):
        """Handle ComfyUI update button click."""
        reply = QMessageBox.question(
            self, "ComfyUI 업데이트",
            "ComfyUI를 최신 버전으로 업데이트합니다.\n\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        self.comfy_update_btn.setEnabled(False)
        self.comfy_update_btn.setText("업데이트 중...")
        QApplication.processEvents()
        
        success, msg = update_comfyui()
        
        if success:
            QMessageBox.information(self, "완료", "ComfyUI가 업데이트되었습니다!")
            self.refresh_system_status()
        else:
            QMessageBox.warning(self, "실패", f"업데이트 실패: {msg}")
            self.comfy_update_btn.setEnabled(True)
            self.comfy_update_btn.setText("업데이트")
    
    def handle_nodes_update(self):
        """Handle custom nodes update button click."""
        reply = QMessageBox.question(
            self, "커스텀 노드 업데이트",
            "모든 커스텀 노드를 최신 버전으로 업데이트합니다.\n\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        self.nodes_update_btn.setEnabled(False)
        self.nodes_update_btn.setText("업데이트 중...")
        QApplication.processEvents()
        
        success_count, fail_count, results = update_all_custom_nodes()
        
        msg = f"완료!\n\n성공: {success_count}개\n실패: {fail_count}개"
        if fail_count > 0:
            failed_names = [r["name"] for r in results if not r["success"]]
            msg += f"\n\n실패 목록: {', '.join(failed_names[:5])}"
        
        QMessageBox.information(self, "업데이트 완료", msg)
        self.refresh_system_status()

