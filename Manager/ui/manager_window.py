"""
DSUComfyCG Manager - Main Window UI (v8 - Local Model Browser + Settings + Confidence)
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
    QStackedWidget, QSpacerItem, QSizePolicy, QTabWidget,
    QLineEdit, QCheckBox, QFormLayout, QComboBox,
    QFileDialog, QHeaderView, QTableWidget, QTableWidgetItem, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QAction, QCursor

from core.checker import (
    scan_workflows, check_workflow_dependencies, get_system_status,
    install_node, run_comfyui, install_comfyui, sync_workflows, fetch_node_db, NODE_DB,
    download_model, load_model_db, MODEL_DB,
    check_for_updates, perform_update, get_local_version,
    check_comfyui_version, check_custom_nodes_updates, 
    update_comfyui, update_all_custom_nodes, get_system_health_report,
    save_url_to_model_db, guess_model_folder, check_model_installed,
    get_all_installed_models, get_unused_models,
    scan_all_workflows_for_models, clear_not_found_cache,
    get_models_path, read_extra_model_paths, write_extra_model_paths,
    ENVIRONMENTS, get_active_env, set_active_env
)
from core.search_engines import load_settings, save_settings, get_api_key, set_api_key, advanced_search_tavily
from core.aria2_downloader import is_aria2_available
from ui.url_input_dialog import ModelUrlInputDialog
from ui.workflow_validator import WorkflowValidatorDialog
from ui.install_dialog import InstallDialog

class SearchWorker(QThread):
    finished = Signal(list)
    
    def __init__(self, model_name, api_key=None):
        super().__init__()
        self.model_name = model_name
        self.api_key = api_key
        
    def run(self):
        results = advanced_search_tavily(self.model_name, self.api_key)
        self.finished.emit(results)


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


class SystemStatusWorker(QThread):
    """Background worker for checking system status (ComfyUI version + custom nodes)."""
    result_signal = Signal(dict)

    def run(self):
        result = {"comfy_info": None, "comfy_error": None, "nodes_info": None, "nodes_error": None}
        try:
            result["comfy_info"] = check_comfyui_version()
        except Exception as e:
            result["comfy_error"] = str(e)
        try:
            result["nodes_info"] = check_custom_nodes_updates()
        except Exception as e:
            result["nodes_error"] = str(e)
        self.result_signal.emit(result)


class ComfyUpdateWorker(QThread):
    """Background worker for updating ComfyUI."""
    result_signal = Signal(bool, str)

    def run(self):
        success, msg = update_comfyui()
        self.result_signal.emit(success, msg)


class NodesUpdateWorker(QThread):
    """Background worker for updating all custom nodes."""
    result_signal = Signal(int, int, list)

    def run(self):
        success_count, fail_count, results = update_all_custom_nodes()
        self.result_signal.emit(success_count, fail_count, results)


class NodeDbRefreshWorker(QThread):
    """Background worker for refreshing node/model databases."""
    result_signal = Signal(int, int)

    def run(self):
        fetch_node_db(force_refresh=True)
        load_model_db()
        self.result_signal.emit(len(NODE_DB), len(MODEL_DB))


class SyncWorkflowsWorker(QThread):
    """Background worker for syncing workflows."""
    result_signal = Signal(int, int)

    def run(self):
        synced, skipped = sync_workflows()
        self.result_signal.emit(synced, skipped)


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

            # If URL provided and not in DB, save to DB first so download_model can find it
            if url:
                from core.checker import check_model_in_db, save_url_to_model_db, guess_model_folder
                in_db, _ = check_model_in_db(name)
                if not in_db:
                    folder = guess_model_folder(name)
                    save_url_to_model_db(name, url, folder)

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
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        header = self._create_header()
        main_layout.addWidget(header)
        
        self.startup_frame = self._create_startup_frame()
        main_layout.addWidget(self.startup_frame)
        
        # System Status Panel (shown after startup)
        self.status_panel = self._create_system_status_panel()
        self.status_panel.hide()  # Hidden until startup complete
        main_layout.addWidget(self.status_panel)
        
        # Main content area tabs
        self.main_tabs = QTabWidget()
        self.main_tabs.setObjectName("mainTabs")
        main_layout.addWidget(self.main_tabs, stretch=1)
        
        # Page 1: Workflow Models
        workflow_tab = self._create_workflow_models_tab()
        self.main_tabs.addTab(workflow_tab, "Workflow Models")
        
        # Page 2: Downloads Placeholder (Will implement later if needed, or point to queue)
        downloads_tab = QWidget()
        self.main_tabs.addTab(downloads_tab, "Downloads")
        
        # Page 3: Local Model Browser
        model_browser_tab = self._create_model_browser_tab()
        self.main_tabs.addTab(model_browser_tab, "Local Browser")
        
        # Page 4: Workflows
        workflows_tab = self._create_workflows_tab()
        self.main_tabs.addTab(workflows_tab, "Workflows")
        
        # Page 5: Settings
        settings_tab = self._create_settings_tab()
        self.main_tabs.addTab(settings_tab, "Help/Settings")
        
        # Connect tab selection
        self.main_tabs.currentChanged.connect(self._on_main_tab_changed)
        
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
        
        # --- Environment Selector ---
        env_label = QLabel("Environment:")
        env_label.setStyleSheet("color: #64748b; font-weight: bold; font-size: 13px;")
        layout.addWidget(env_label)
        
        self.env_combo = QComboBox()
        self.env_combo.setObjectName("envCombo")
        self.env_combo.setMinimumWidth(220)
        self.env_combo.setStyleSheet("""
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 12px;
                color: #1e293b;
                font-weight: bold;
                font-size: 13px;
            }
            QComboBox:focus { border-color: #3b82f6; }
        """)
        layout.addWidget(self.env_combo)
        
        self.env_mgr_btn = QPushButton("⚙️ Manage")
        self.env_mgr_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                color: #475569;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #e2e8f0; color: #1e293b; }
        """)
        self.env_mgr_btn.clicked.connect(self._open_env_manager)
        layout.addWidget(self.env_mgr_btn)
        
        layout.addSpacing(15)
        # --- End Environment ---
        
        # 1-Click Install All Button
        self.install_all_btn = QPushButton("⚡ One-Click Install All")
        self.install_all_btn.setObjectName("installAllBtn")
        self.install_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:disabled {
                background-color: #475569;
                color: #94a3b8;
            }
        """)
        self.install_all_btn.clicked.connect(self.install_all_missing)
        self.install_all_btn.hide() # Shown only when dependencies are missing
        layout.addWidget(self.install_all_btn)
        
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
        
        self._populate_envs_combo()
        self.env_combo.currentIndexChanged.connect(self._on_env_changed)
        return frame

    def _populate_envs_combo(self):
        self.env_combo.blockSignals(True)
        self.env_combo.clear()
        
        active_index = 0
        
        for i, (eid, edata) in enumerate(ENVIRONMENTS.items()):
            display_name = f"{edata['name']} ({edata['type']})"
            self.env_combo.addItem(display_name, eid)
                
        # Actually correctly locating the active index
        for i in range(self.env_combo.count()):
            current_path = get_active_env().get("path", "")
            if ENVIRONMENTS.get(self.env_combo.itemData(i), {}).get("path") == current_path:
                active_index = i
                break
                
        self.env_combo.setCurrentIndex(active_index)
        self.env_combo.blockSignals(False)

    def _on_env_changed(self, index):
        env_id = self.env_combo.itemData(index)
        if env_id:
            set_active_env(env_id)
            # When environment changes, trigger a full UI reload of states
            self.refresh_all()
            self.update_system_status()

    def refresh_all(self):
        """Convenience wrapper to refresh all major UI panels."""
        self.refresh_workflows()
        self.populate_all_models_table()
            
    def _open_env_manager(self):
        from ui.env_manager_dialog import EnvManagerDialog
        dlg = EnvManagerDialog(self)
        if dlg.exec():
            # Refresh if user made changes in the dialog
            self._populate_envs_combo()
            self._on_env_changed(self.env_combo.currentIndex())
    
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
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
                padding: 16px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        
        # Title
        title = QLabel("📊 시스템 상태")
        title.setStyleSheet("color: #0f172a; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        # Status rows
        status_grid = QVBoxLayout()
        status_grid.setSpacing(6)
        
        # ComfyUI row
        comfy_row = QHBoxLayout()
        self.comfy_label = QLabel("ComfyUI")
        self.comfy_label.setStyleSheet("color: #334155; font-size: 13px; font-weight: 500;")
        self.comfy_status = QLabel("체크 중...")
        self.comfy_status.setStyleSheet("color: #64748b; font-size: 12px;")
        self.comfy_update_btn = QPushButton("업데이트")
        self.comfy_update_btn.setStyleSheet("""
            QPushButton {
                background: #10b981; color: white; border: none;
                padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #059669; }
            QPushButton:disabled { background: #94a3b8; }
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
        self.nodes_label.setStyleSheet("color: #334155; font-size: 13px; font-weight: 500;")
        self.nodes_status = QLabel("체크 중...")
        self.nodes_status.setStyleSheet("color: #64748b; font-size: 12px;")
        self.nodes_update_btn = QPushButton("전체 업데이트")
        self.nodes_update_btn.setStyleSheet("""
            QPushButton {
                background: #10b981; color: white; border: none;
                padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #059669; }
            QPushButton:disabled { background: #94a3b8; }
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
        self.models_label.setStyleSheet("color: #334155; font-size: 13px; font-weight: 500;")
        self.models_status = QLabel("체크 중...")
        self.models_status.setStyleSheet("color: #64748b; font-size: 12px;")
        models_row.addWidget(self.models_label)
        models_row.addWidget(self.models_status)
        models_row.addStretch()
        status_grid.addLayout(models_row)
        
        layout.addLayout(status_grid)
        
        return frame
    
    def _create_workflow_models_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # 1. Top Controls (Filter combo box)
        controls_layout = QHBoxLayout()
        self.model_filter_combo = QComboBox()
        self.model_filter_combo.addItems(["All Models", "Missing Only", "Existing Only"])
        self.model_filter_combo.setFixedWidth(150)
        # We can implement filter logic later
        controls_layout.addWidget(self.model_filter_combo)
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        # 2. Summary Banner
        banner_frame = QFrame()
        banner_frame.setStyleSheet("background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;")
        banner_layout = QHBoxLayout(banner_frame)
        banner_layout.setContentsMargins(20, 15, 20, 15)
        banner_layout.setSpacing(40)
        
        def _make_stat(title, color):
            vbox = QVBoxLayout()
            vbox.setSpacing(2)
            num_label = QLabel("0")
            num_label.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: bold; border: none; background: transparent;")
            num_label.setAlignment(Qt.AlignCenter)
            title_label = QLabel(title)
            title_label.setStyleSheet("color: #64748b; font-size: 12px; font-weight: bold; border: none; background: transparent;")
            title_label.setAlignment(Qt.AlignCenter)
            vbox.addWidget(num_label)
            vbox.addWidget(title_label)
            return vbox, num_label
            
        stat1, self.stat_total = _make_stat("TOTAL MODELS", "#1e293b")
        stat2, self.stat_existing = _make_stat("EXISTING", "#0d9488")
        stat3, self.stat_missing = _make_stat("MISSING", "#ef4444")
        stat4, self.stat_downloadable = _make_stat("DOWNLOADABLE", "#0d9488")
        
        banner_layout.addLayout(stat1)
        banner_layout.addLayout(stat2)
        banner_layout.addLayout(stat3)
        banner_layout.addLayout(stat4)
        banner_layout.addStretch()
        
        layout.addWidget(banner_frame)
        
        # 3. Table View
        self.models_table = QTableWidget()
        self.models_table.setColumnCount(6)
        self.models_table.setHorizontalHeaderLabels(["Filename", "Type", "Directory", "Status", "Source", "Action"])
        self.models_table.horizontalHeader().setStretchLastSection(False)
        self.models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.models_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.models_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        
        self.models_table.verticalHeader().setVisible(False)
        self.models_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.models_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.models_table.setShowGrid(False)
        
        layout.addWidget(self.models_table, stretch=1)
        
        # 4. Bottom Panel (Totals + Download Progress)
        bottom_layout = QHBoxLayout()
        
        self.table_footer = QLabel("Total: 0 | Existing: 0 | Missing: 0")
        self.table_footer.setStyleSheet("color: #64748b; font-size: 13px; font-weight: bold;")
        bottom_layout.addWidget(self.table_footer)
        
        bottom_layout.addStretch()
        
        # Inline progress section styled for the dark theme
        self.queue_progress_frame = QFrame()
        self.queue_progress_frame.setFixedWidth(400)
        self.queue_progress_frame.setStyleSheet("background-color: transparent; border: none;")
        progress_layout = QHBoxLayout(self.queue_progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        self.queue_current_label = QLabel("Ready")
        self.queue_current_label.setStyleSheet("color: #0d9488; font-size: 12px; font-weight: bold;")
        self.queue_current_label.setFixedWidth(120)
        progress_layout.addWidget(self.queue_current_label)
        
        self.queue_progress_bar = QProgressBar()
        self.queue_progress_bar.setRange(0, 100)
        self.queue_progress_bar.setValue(0)
        self.queue_progress_bar.setFixedHeight(14)
        self.queue_progress_bar.setTextVisible(False)
        self.queue_progress_bar.setStyleSheet("""
            QProgressBar { background: #e2e8f0; border: none; border-radius: 6px; }
            QProgressBar::chunk { background-color: #0d9488; border-radius: 6px; }
        """)
        progress_layout.addWidget(self.queue_progress_bar)
        
        self.queue_detail_label = QLabel("")
        self.queue_detail_label.setStyleSheet("color: #64748b; font-size: 11px;")
        progress_layout.addWidget(self.queue_detail_label)
        
        bottom_layout.addWidget(self.queue_progress_frame)
        self.queue_progress_frame.hide()  # Hidden until download starts
        
        layout.addLayout(bottom_layout)
        
        return tab
    

    
    def _create_model_browser_tab(self):
        """Create the Local Model Browser tab (NEW)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Left: Folder tree
        left_panel = QVBoxLayout()
        folder_label = QLabel("📁 모델 폴더")
        folder_label.setStyleSheet("color: #0ea5e9; font-size: 15px; font-weight: bold;")
        left_panel.addWidget(folder_label)
        
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabels(["Folder", "Count"])
        self.folder_tree.setColumnWidth(0, 180)
        self.folder_tree.setColumnWidth(1, 50)
        self.folder_tree.setMaximumWidth(280)
        self.folder_tree.currentItemChanged.connect(self._on_folder_selected)
        left_panel.addWidget(self.folder_tree)
        
        # Scan button
        scan_usage_btn = QPushButton("🔍 워크플로우 스캔")
        scan_usage_btn.setObjectName("smallBtn")
        scan_usage_btn.setToolTip("모든 워크플로우를 스캔하여 모델 사용 이력을 업데이트합니다")
        scan_usage_btn.clicked.connect(self._scan_model_usage)
        left_panel.addWidget(scan_usage_btn)
        
        layout.addLayout(left_panel)
        
        # Right: Model list
        right_panel = QVBoxLayout()
        
        # Search and filter bar
        filter_layout = QHBoxLayout()
        
        self.model_search = QLineEdit()
        self.model_search.setPlaceholderText("🔍 모델 검색...")
        self.model_search.setStyleSheet("""
            QLineEdit {
                background: rgba(26, 27, 38, 0.95); color: #c0caf5;
                border: 1px solid #414868; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #7aa2f7; }
        """)
        self.model_search.textChanged.connect(self._filter_model_list)
        filter_layout.addWidget(self.model_search)
        
        self.unused_filter = QCheckBox("미사용만")
        self.unused_filter.setStyleSheet("color: #f7768e; font-size: 12px;")
        self.unused_filter.setToolTip("워크플로우에서 사용되지 않는 모델만 표시")
        self.unused_filter.toggled.connect(self._filter_model_list)
        filter_layout.addWidget(self.unused_filter)
        
        right_panel.addLayout(filter_layout)
        
        # Model count
        self.browser_count_label = QLabel("")
        self.browser_count_label.setStyleSheet("color: #565f89; font-size: 11px;")
        right_panel.addWidget(self.browser_count_label)
        
        # Model list tree
        self.model_browser_tree = QTreeWidget()
        self.model_browser_tree.setHeaderLabels(["Name", "Folder", "Size", "Modified"])
        self.model_browser_tree.setColumnWidth(0, 300)
        self.model_browser_tree.setColumnWidth(1, 120)
        self.model_browser_tree.setColumnWidth(2, 80)
        self.model_browser_tree.setColumnWidth(3, 130)
        self.model_browser_tree.setRootIsDecorated(False)
        self.model_browser_tree.setSortingEnabled(True)
        self.model_browser_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.model_browser_tree.customContextMenuRequested.connect(self._show_browser_context_menu)
        right_panel.addWidget(self.model_browser_tree)
        
        layout.addLayout(right_panel, stretch=1)
        
        # Store all models for filtering
        self._all_browser_models = []
        self._unused_model_names = set()
        
        return widget
        
    def _create_workflows_tab(self):
        """Create the Workflows tab (NEW)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title_layout = QHBoxLayout()
        title = QLabel("📂 Workflows")
        title.setStyleSheet("color: #0ea5e9; font-size: 18px; font-weight: bold;")
        title_layout.addWidget(title)
        
        refresh_btn = QPushButton("새로고침")
        refresh_btn.setStyleSheet("background: #334155; color: white; padding: 5px 15px; border-radius: 6px;")
        refresh_btn.clicked.connect(self._refresh_workflows_tab)
        title_layout.addStretch()
        title_layout.addWidget(refresh_btn)
        
        layout.addLayout(title_layout)
        
        self.workflow_list_table = QTableWidget(0, 2)
        self.workflow_list_table.setHorizontalHeaderLabels(["Filename", "Action"])
        self.workflow_list_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.workflow_list_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.workflow_list_table.setColumnWidth(1, 150)
        self.workflow_list_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.workflow_list_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.workflow_list_table.verticalHeader().setDefaultSectionSize(40)
        self.workflow_list_table.verticalHeader().setVisible(False)
        self.workflow_list_table.setShowGrid(False)
        
        layout.addWidget(self.workflow_list_table)
        self._refresh_workflows_tab()
        
        return widget
        
    def _refresh_workflows_tab(self):
        # Only populate if the table exists to avoid startup timing issues
        if not hasattr(self, 'workflow_list_table'): return
        self.workflow_list_table.setRowCount(0)
        workflows = scan_workflows()
        for wf in workflows:
            row = self.workflow_list_table.rowCount()
            self.workflow_list_table.insertRow(row)
            
            name_item = QTableWidgetItem(wf)
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.workflow_list_table.setItem(row, 0, name_item)
            
            btn = QPushButton("🔍 의존성 검증")
            btn.setStyleSheet("background: #10b981; color: white; font-weight: bold; border-radius: 4px; padding: 6px;")
            btn.clicked.connect(lambda checked=False, filename=wf: self._validate_workflow(filename))
            
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            btn_layout.addWidget(btn)
            self.workflow_list_table.setCellWidget(row, 1, btn_widget)
            
    def _validate_workflow(self, filename):
        dialog = WorkflowValidatorDialog(filename, self)
        if dialog.exec():
            QMessageBox.information(self, "검증 완료", f"{filename}의 모든 모델/노드 URL이 등록 대기열에 추가되었습니다.\n[새로고침]을 눌러 다운로드를 진행하세요.")
            self.refresh_all()
    
    def _create_settings_tab(self):
        """Create the Settings tab (NEW)."""
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(20)
        
        title = QLabel("⚙️ 설정")
        title.setStyleSheet("color: #7dcfff; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # --- API Keys Section ---
        api_group = QGroupBox("API Keys")
        api_layout = QFormLayout(api_group)
        api_layout.setSpacing(12)
        
        input_style = """
            QLineEdit {
                background: rgba(26, 27, 38, 0.95); color: #c0caf5;
                border: 1px solid #414868; border-radius: 6px;
                padding: 8px 12px; font-size: 12px; font-family: 'Consolas', monospace;
            }
            QLineEdit:focus { border-color: #7aa2f7; }
        """
        
        self.hf_token_input = QLineEdit()
        self.hf_token_input.setPlaceholderText("hf_...")
        self.hf_token_input.setEchoMode(QLineEdit.Password)
        self.hf_token_input.setStyleSheet(input_style)
        api_layout.addRow(QLabel("HuggingFace Token:"), self.hf_token_input)
        
        self.civitai_key_input = QLineEdit()
        self.civitai_key_input.setPlaceholderText("선택사항 - rate limit 해제용")
        self.civitai_key_input.setEchoMode(QLineEdit.Password)
        self.civitai_key_input.setStyleSheet(input_style)
        api_layout.addRow(QLabel("CivitAI API Key:"), self.civitai_key_input)
        
        self.tavily_key_input = QLineEdit()
        self.tavily_key_input.setPlaceholderText("선택사항 - AI 검색용")
        self.tavily_key_input.setEchoMode(QLineEdit.Password)
        self.tavily_key_input.setStyleSheet(input_style)
        api_layout.addRow(QLabel("Tavily API Key:"), self.tavily_key_input)
        
        layout.addWidget(api_group)
        
        # --- Search Settings ---
        search_group = QGroupBox("검색 설정")
        search_layout = QFormLayout(search_group)
        search_layout.setSpacing(12)
        
        self.enable_civitai_cb = QCheckBox("CivitAI 검색 활성화")
        self.enable_civitai_cb.setStyleSheet("color: #c0caf5;")
        search_layout.addRow(self.enable_civitai_cb)
        
        self.enable_tavily_cb = QCheckBox("Tavily AI 검색 활성화 (API 키 필요)")
        self.enable_tavily_cb.setStyleSheet("color: #c0caf5;")
        search_layout.addRow(self.enable_tavily_cb)
        
        layout.addWidget(search_group)
        
        # --- Download Settings ---
        dl_group = QGroupBox("다운로드 설정")
        dl_layout = QFormLayout(dl_group)
        dl_layout.setSpacing(12)
        
        self.use_aria2_cb = QCheckBox("aria2c 사용 (설치 시 자동 감지)")
        self.use_aria2_cb.setStyleSheet("color: #c0caf5;")
        dl_layout.addRow(self.use_aria2_cb)
        
        aria2_status = "✅ 설치됨" if is_aria2_available() else "❌ 미설치"
        aria2_label = QLabel(f"aria2c 상태: {aria2_status}")
        aria2_label.setStyleSheet("color: #888; font-size: 11px;")
        dl_layout.addRow(aria2_label)
        
        layout.addWidget(dl_group)
        
        # --- Cache Actions ---
        cache_group = QGroupBox("캐시 관리")
        cache_layout = QVBoxLayout(cache_group)
        
        clear_cache_btn = QPushButton("🗑️ NOT_FOUND 캐시 초기화")
        clear_cache_btn.setObjectName("smallBtn")
        clear_cache_btn.setToolTip("못찾은 모델 캐시를 초기화하여 다시 검색합니다")
        clear_cache_btn.clicked.connect(self._clear_not_found_cache)
        cache_layout.addWidget(clear_cache_btn)
        
        layout.addWidget(cache_group)
        
        # --- Models Path Manager ---
        path_group = QGroupBox("공유 모델 경로 관리 (여러 ComfyUI 통합용)")
        path_layout = QVBoxLayout(path_group)
        
        self.paths_list = QListWidget()
        self.paths_list.setStyleSheet(input_style + "QListWidget { padding: 4px; }")
        
        extra = read_extra_model_paths()
        base_folders = set()
        for mtype, paths in extra.items():
            for p in paths:
                parent = os.path.dirname(p).replace("\\", "/")
                base_folders.add(parent)
                
        self.paths_list.addItems(sorted(list(base_folders)))
        
        path_layout.addWidget(self.paths_list)
        
        path_btn_layout = QHBoxLayout()
        add_path_btn = QPushButton("➕ 모델 폴더 추가")
        add_path_btn.setObjectName("mediumBtn")
        add_path_btn.setStyleSheet("""
            QPushButton { background: #1a1b26; border: 1px solid #414868; padding: 6px; border-radius: 4px; color: #c0caf5; }
            QPushButton:hover { background: #24283b; }
        """)
        add_path_btn.clicked.connect(self._add_model_path)
        
        remove_path_btn = QPushButton("➖ 선택 삭제")
        remove_path_btn.setObjectName("mediumBtn")
        remove_path_btn.setStyleSheet("""
            QPushButton { background: #1a1b26; border: 1px solid #414868; padding: 6px; border-radius: 4px; color: #f7768e; }
            QPushButton:hover { background: #24283b; }
        """)
        remove_path_btn.clicked.connect(self._remove_model_path)
        
        path_btn_layout.addWidget(add_path_btn)
        path_btn_layout.addWidget(remove_path_btn)
        path_layout.addLayout(path_btn_layout)
        
        layout.addWidget(path_group)
        
        # Save button
        save_btn = QPushButton("💾 설정 저장")
        save_btn.setObjectName("primaryBtn")
        save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                border: 1px solid #10b981; font-size: 14px; padding: 12px;
            }
            QPushButton:hover { background: #34d399; }
        """)
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)
        
        layout.addStretch()
        
        scroll.setWidget(inner)
        
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        
        # Load current settings
        self._load_settings_to_ui()
        
        return widget
    
    def _load_settings_to_ui(self):
        """Load settings from file into UI controls."""
        settings = load_settings()
        api_keys = settings.get("api_keys", {})
        self.hf_token_input.setText(api_keys.get("hf_token", ""))
        self.civitai_key_input.setText(api_keys.get("civitai_api_key", ""))
        self.tavily_key_input.setText(api_keys.get("tavily_api_key", ""))
        
        search = settings.get("search", {})
        self.enable_civitai_cb.setChecked(search.get("enable_civitai", True))
        self.enable_tavily_cb.setChecked(search.get("enable_tavily", True))
        
        dl = settings.get("download", {})
        self.use_aria2_cb.setChecked(dl.get("use_aria2", True))
    
    def _save_settings(self):
        """Save UI settings to file."""
        settings = load_settings()
        settings["api_keys"] = {
            "hf_token": self.hf_token_input.text().strip(),
            "civitai_api_key": self.civitai_key_input.text().strip(),
            "tavily_api_key": self.tavily_key_input.text().strip(),
        }
        settings["search"] = {
            "enable_civitai": self.enable_civitai_cb.isChecked(),
            "enable_tavily": self.enable_tavily_cb.isChecked(),
            "fuzzy_threshold": settings.get("search", {}).get("fuzzy_threshold", 0.70),
        }
        settings["download"] = {
            "use_aria2": self.use_aria2_cb.isChecked(),
            "aria2_max_connections": 16,
            "aria2_split": 16,
            "parallel_threads": 4,
        }
        if save_settings(settings):
            QMessageBox.information(self, "저장 완료", "설정이 저장되었습니다.")
        else:
            QMessageBox.warning(self, "저장 실패", "설정 저장에 실패했습니다.")
    
    def _clear_not_found_cache(self):
        """Clear the NOT_FOUND cache."""
        clear_not_found_cache()
        QMessageBox.information(self, "캐시 초기화", "NOT_FOUND 캐시가 초기화되었습니다.\n다음 검색 시 모든 모델을 다시 찾습니다.")

    def _add_model_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "공유 모델 루트 폴더 선택 (checkpoints, loras 등이 있는 상위 폴더)")
        if not dir_path:
            return
            
        dir_path = dir_path.replace("\\", "/")
        
        for i in range(self.paths_list.count()):
            if self.paths_list.item(i).text() == dir_path:
                QMessageBox.warning(self, "중복", "이미 등록된 경로입니다.")
                return
                
        self.paths_list.addItem(dir_path)
        self._apply_model_paths_from_list()

    def _remove_model_path(self):
        selected = self.paths_list.selectedItems()
        if not selected:
            return
        for item in selected:
            self.paths_list.takeItem(self.paths_list.row(item))
        self._apply_model_paths_from_list()
        
    def _apply_model_paths_from_list(self):
        base_folders = []
        for i in range(self.paths_list.count()):
            base_folders.append(self.paths_list.item(i).text())
            
        paths_dict = {}
        from core.checker import FOLDER_MAPPINGS
        standard_types = list(FOLDER_MAPPINGS.keys()) if FOLDER_MAPPINGS else [
            'checkpoints', 'loras', 'controlnet', 'vae', 'clip', 'clip_vision',
            'unet', 'upscale_models', 'embeddings', 'diffusion_models', 'text_encoders',
            'sam2', 'LLM', 'audio', 'rife', 'yolo', 'dwpose'
        ]
        
        for base in base_folders:
            for mtype in standard_types:
                full_p = os.path.join(base, mtype).replace("\\", "/")
                paths_dict.setdefault(mtype, []).append(full_p)
                
        if write_extra_model_paths(paths_dict):
            QMessageBox.information(self, "경로 업데이트", "공유 모델 경로가 업데이트 되었습니다.\n새 경로의 모델들은 다음에 앱을 시작할 때 완전히 반영됩니다.")
            self._refresh_model_browser()
        else:
            QMessageBox.warning(self, "오류", "extra_model_paths.yaml 저장에 실패했습니다.")
    
    def _on_main_tab_changed(self, index):
        """Handle main tab change. Lazy-load model browser on first visit."""
        if index == 2 and not self._all_browser_models:
            self._refresh_model_browser()
    
    def _refresh_model_browser(self):
        """Refresh the local model browser."""
        self.status_bar.showMessage("로컬 모델 스캔 중...")
        QApplication.processEvents()
        
        self._all_browser_models = get_all_installed_models()
        
        # Build folder tree
        self.folder_tree.clear()
        folder_counts = {}
        for m in self._all_browser_models:
            folder = m["folder"].split("/")[0] if "/" in m["folder"] else m["folder"]
            folder_counts[folder] = folder_counts.get(folder, 0) + 1
        
        all_item = QTreeWidgetItem(["전체", str(len(self._all_browser_models))])
        all_item.setData(0, Qt.UserRole, "__all__")
        self.folder_tree.addTopLevelItem(all_item)
        
        for folder, count in sorted(folder_counts.items()):
            item = QTreeWidgetItem([folder, str(count)])
            item.setData(0, Qt.UserRole, folder)
            self.folder_tree.addTopLevelItem(item)
        
        self.folder_tree.setCurrentItem(all_item)
        self._filter_model_list()
        self.status_bar.showMessage(f"로컬 모델: {len(self._all_browser_models)}개")
    
    def _on_folder_selected(self, current, previous):
        """Handle folder selection in browser."""
        self._filter_model_list()
    
    def _filter_model_list(self):
        """Filter and display model list based on search/folder/unused filters."""
        if not self._all_browser_models:
            return
        
        search_text = self.model_search.text().lower().strip() if hasattr(self, 'model_search') else ""
        show_unused_only = self.unused_filter.isChecked() if hasattr(self, 'unused_filter') else False
        
        # Get selected folder
        selected_folder = "__all__"
        if hasattr(self, 'folder_tree') and self.folder_tree.currentItem():
            selected_folder = self.folder_tree.currentItem().data(0, Qt.UserRole) or "__all__"
        
        self.model_browser_tree.clear()
        shown = 0
        
        from datetime import datetime
        
        for m in self._all_browser_models:
            # Folder filter
            if selected_folder != "__all__":
                folder_base = m["folder"].split("/")[0] if "/" in m["folder"] else m["folder"]
                if folder_base != selected_folder:
                    continue
            
            # Search filter
            if search_text and search_text not in m["name"].lower():
                continue
            
            # Unused filter
            if show_unused_only and m["name"] not in self._unused_model_names:
                continue
            
            # Format size
            size_mb = m["size_bytes"] / (1024 * 1024)
            if size_mb > 1024:
                size_str = f"{size_mb / 1024:.1f} GB"
            else:
                size_str = f"{size_mb:.0f} MB"
            
            # Format time
            try:
                mod_time = datetime.fromtimestamp(m["modified_time"]).strftime("%Y-%m-%d %H:%M")
            except Exception:
                mod_time = ""
            
            item = QTreeWidgetItem([m["name"], m["folder"], size_str, mod_time])
            item.setData(0, Qt.UserRole, m)  # Store full model data
            
            # Color unused models red
            if m["name"] in self._unused_model_names:
                item.setForeground(0, QColor("#f7768e"))
            
            self.model_browser_tree.addTopLevelItem(item)
            shown += 1
        
        self.browser_count_label.setText(f"{shown} / {len(self._all_browser_models)} 모델")
    
    def _scan_model_usage(self):
        """Scan all workflows for model usage and refresh unused tracking."""
        self.status_bar.showMessage("워크플로우 전체 스캔 중...")
        QApplication.processEvents()
        
        usage = scan_all_workflows_for_models()
        
        # Build unused set
        unused = get_unused_models()
        self._unused_model_names = {m["name"] for m in unused}
        
        self._refresh_model_browser()
        
        msg = f"스캔 완료: {len(usage)}개 모델 사용 이력, {len(self._unused_model_names)}개 미사용"
        self.status_bar.showMessage(msg)
        QMessageBox.information(self, "스캔 완료", msg)
    
    def _show_browser_context_menu(self, position):
        """Context menu for model browser."""
        item = self.model_browser_tree.itemAt(position)
        if not item:
            return
        
        model_data = item.data(0, Qt.UserRole)
        if not model_data:
            return
        
        menu = QMenu(self.model_browser_tree)
        menu.setStyleSheet("""
            QMenu { background-color: #2a2a3e; color: #e0e0e0; border: 1px solid #3a3a5e; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background-color: #5865f2; color: white; }
        """)
        
        copy_name = QAction("이름 복사", self)
        copy_name.triggered.connect(lambda: QApplication.clipboard().setText(model_data["name"]))
        menu.addAction(copy_name)
        
        copy_path = QAction("경로 복사", self)
        copy_path.triggered.connect(lambda: QApplication.clipboard().setText(model_data["path"]))
        menu.addAction(copy_path)
        
        open_folder = QAction("폴더 열기", self)
        open_folder.triggered.connect(lambda: os.startfile(os.path.dirname(model_data["path"])))
        menu.addAction(open_folder)
        
        menu.addSeparator()
        
        delete_action = QAction("🗑️ 삭제", self)
        delete_action.triggered.connect(lambda: self._delete_model(model_data))
        menu.addAction(delete_action)
        
        menu.exec(self.model_browser_tree.viewport().mapToGlobal(position))
    
    def _delete_model(self, model_data):
        """Delete a model file."""
        confirm = QMessageBox.question(
            self, "모델 삭제",
            f"'{model_data['name']}'을 삭제하시겠습니까?\n\n"
            f"경로: {model_data['path']}\n"
            f"크기: {model_data['size_bytes'] / (1024*1024):.0f} MB\n\n"
            "이 작업은 되돌릴 수 없습니다.",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                os.remove(model_data["path"])
                self._refresh_model_browser()
                self.status_bar.showMessage(f"삭제됨: {model_data['name']}")
            except Exception as e:
                QMessageBox.critical(self, "삭제 실패", str(e))
    
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
        
        self.install_btn = QPushButton("📥 Install ComfyUI")
        self.install_btn.setObjectName("installBtn")
        self.install_btn.clicked.connect(self.handle_install_action)
        self.install_btn.hide()
        layout.addWidget(self.install_btn)
        
        self.run_btn = QPushButton("▶️ Run ComfyUI")
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.clicked.connect(self.handle_comfy_action)
        self.run_btn.setEnabled(False)
        layout.addWidget(self.run_btn)
        
        return frame
    
    def _get_stylesheet(self):
        return """
            QMainWindow {
                background-color: #f3f4f6;
            }
            QWidget {
                color: #1e293b;
                font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            }
            #mainContentArea, QScrollArea, QScrollArea > QWidget > QWidget {
                background-color: #f3f4f6;
                border: none;
            }
            /* Flat Tab Styling */
            QTabWidget::pane {
                border-top: 2px solid #e2e8f0;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: transparent;
                color: #64748b;
                padding: 14px 28px;
                border: none;
                font-size: 15px;
                font-weight: bold;
                margin-right: 4px;
            }
            QTabBar::tab:hover {
                background-color: #f1f5f9;
                color: #1e293b;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #0d9488;
                border: 2px solid #e2e8f0;
                border-bottom: 2px solid #ffffff;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            
            #headerFrame {
                background-color: #ffffff;
                border-bottom: 1px solid #e2e8f0;
            }
            #titleLabel { color: #0f172a; font-size: 26px; font-weight: 800; }
            #systemInfo { color: #64748b; font-size: 13px; font-weight: 600; }
            
            #startupFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }
            #startupLabel { color: #0d9488; font-size: 15px; font-weight: bold; }
            #startupProgress {
                background: #f1f5f9; border: none; border-radius: 6px; height: 8px;
            }
            #startupProgress::chunk {
                background-color: #0d9488;
                border-radius: 6px;
            }
            
            QGroupBox {
                color: #1e293b; font-size: 15px; font-weight: bold;
                border: 1px solid #e2e8f0; border-radius: 16px;
                margin-top: 24px; padding-top: 24px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 16px; padding: 0 4px; color: #0d9488;
            }
            /* QTableWidget Styling for Easy Install Look */
            QTableWidget {
                background-color: #ffffff;
                color: #334155;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: transparent;
                font-size: 13px;
                outline: none;
            }
            QTableWidget::item {
                padding: 12px 16px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:selected {
                background-color: #f0fdfa;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #64748b;
                padding: 16px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                font-weight: bold;
                font-size: 13px;
                text-align: left;
            }
            
            QListWidget, QTreeWidget {
                background-color: #ffffff; color: #334155;
                border: 1px solid #e2e8f0; border-radius: 12px; font-size: 13px; outline: none;
            }
            QTreeWidget::item { padding: 10px 8px; border-bottom: 1px solid #f1f5f9; }
            QTreeWidget::item:selected {
                background-color: #f0fdfa; color: #0f172a;
                border-radius: 6px;
            }
            
            QPushButton { 
                border: none; border-radius: 16px; padding: 8px 16px; 
                font-size: 14px; font-weight: bold;
            }
            
            /* Primary Run Button */
            #primaryBtn {
                background-color: #3b82f6; color: #ffffff; font-size: 15px; padding: 10px 24px;
                border-radius: 20px;
            }
            #primaryBtn:hover { background-color: #2563eb; }
            #primaryBtn:pressed { background-color: #1d4ed8; }
            #primaryBtn:disabled { background-color: #e2e8f0; color: #94a3b8; }

            /* Install Button */
            #installBtn {
                background-color: #10b981; color: #ffffff; font-size: 15px; padding: 10px 24px;
                border-radius: 20px;
            }
            #installBtn:hover { background-color: #059669; }
            #installBtn:pressed { background-color: #047857; }
            
            #secondaryBtn { background-color: #f1f5f9; color: #475569; }
            #secondaryBtn:hover { background-color: #e2e8f0; }
            
            #smallBtn { background-color: #f1f5f9; color: #64748b; padding: 6px 14px; font-size: 12px; border-radius: 14px; }
            #smallBtn:hover { background-color: #e2e8f0; color: #1e293b; }
            
            /* Action Table Button */
            #tableActionBtn {
                background-color: #3b82f6; color: #ffffff; border-radius: 12px; padding: 8px 16px; 
                font-weight: bold; font-size: 12px;
            }
            #tableActionBtn:hover { background-color: #2563eb; }
            #tableActionBtn:pressed { background-color: #1d4ed8; }
            
            QLineEdit, QComboBox {
                background-color: #ffffff;
                color: #1e293b;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus { border-color: #3b82f6; outline: none; }
            QComboBox::drop-down { border: none; }
        """
        
    # Legacy context menus (nodes_tree / models_tree) removed in Phase 8 tabular redesign.
    
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
        
        # Populate all models in the Tabular interface!
        self.populate_all_models_table()
        
        n_nodes = len(results["missing_nodes"])
        n_models = len(results["missing_models"])
        
        if n_nodes > 0 or n_models > 0:
            self.install_all_btn.show()
            self.install_all_btn.setText(f"⚡ 1-Click Install All ({n_nodes} nodes, {n_models} models)")
        else:
            self.install_all_btn.hide()
        
        self.status_bar.showMessage(
            f"Ready! Nodes: {results['node_db_count']} | Models: {results['model_db_count']} | Workflows: {results['total_workflows']}"
        )

    
    def check_version_updates(self):
        """Check for app updates in background thread."""
        local_version = get_local_version()
        self.version_label.setText(f"v{local_version}")

        from PySide6.QtCore import QThread, Signal

        class UpdateCheckWorker(QThread):
            result_signal = Signal(bool, str, str, str)

            def run(self):
                try:
                    update_available, local_ver, remote_ver, error = check_for_updates()
                    self.result_signal.emit(update_available, local_ver or "", remote_ver or "", error or "")
                except Exception as e:
                    self.result_signal.emit(False, "", "", str(e))

        def _on_update_check_done(update_available, local_ver, remote_ver, error):
            if error:
                self.version_label.setToolTip(f"Update check failed: {error}")
            elif update_available:
                self.update_btn.setText(f"🔄 Update to v{remote_ver}")
                self.update_btn.setToolTip(f"Current: v{local_ver} → Latest: v{remote_ver}")
                self.update_btn.show()
                self.status_bar.showMessage(f"Update available: v{remote_ver}", 5000)
            else:
                self.version_label.setToolTip("You're on the latest version")

        self._update_worker = UpdateCheckWorker()
        self._update_worker.result_signal.connect(_on_update_check_done)
        self._update_worker.start()
    
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
    
    def refresh_workflows(self):
        # Delegate to the new Tabular UI workflows table
        self._refresh_workflows_tab()
    
    def sync_workflows_ui(self):
        self.status_bar.showMessage("Syncing workflows...")
        self._sync_wf_worker = SyncWorkflowsWorker()
        self._sync_wf_worker.result_signal.connect(self._on_sync_workflows_done)
        self._sync_wf_worker.start()

    def _on_sync_workflows_done(self, synced, skipped):
        self.refresh_workflows()
        self.status_bar.showMessage(f"Synced {synced}, skipped {skipped}")

    def update_node_db(self):
        self.status_bar.showMessage("Refreshing databases...")
        self.update_db_btn.setEnabled(False)
        self._node_db_worker = NodeDbRefreshWorker()
        self._node_db_worker.result_signal.connect(self._on_node_db_done)
        self._node_db_worker.start()

    def _on_node_db_done(self, node_count, model_count):
        self.update_db_btn.setEnabled(True)
        self.status_bar.showMessage(f"Nodes: {node_count} | Models: {model_count}")
    
    def rescan_all_workflows(self):
        self.status_bar.showMessage("Rescanning all workflows...")
        QApplication.processEvents()
        
        # Populate the tabular view with ALL known models from the global database
        # For this tabular view, we want to show everything.
        self.populate_all_models_table()
        
        self.status_bar.showMessage(f"Scan complete. Populated models list.")

    def populate_all_models_table(self):
        self.models_table.setRowCount(0)
        
        from core.checker import parse_workflow
        
        # 1. Collect all models from MODEL_DB
        combined_models = {}
        for name, url in MODEL_DB.items():
            if isinstance(url, dict):
                url_str = url.get("url", "")
            else:
                url_str = url
            combined_models[name] = {"url": url_str, "folder": guess_model_folder(name)}
            
        # 2. Add all models used in all local workflows
        workflows = scan_workflows()
        for wf in workflows:
            _, wf_models = parse_workflow(wf)
            for m in wf_models:
                if m not in combined_models:
                    combined_models[m] = {"url": "", "folder": guess_model_folder(m)}
                    
        total = len(combined_models)
        existing = 0
        missing = 0
        downloadable = 0
        
        for i, (name, data) in enumerate(combined_models.items()):
            folder = data["folder"]
            url = data["url"]
            self.models_table.insertRow(i)
            
            # Check all model paths (including shared models via EXTRA_MODEL_PATHS)
            is_installed, _, _ = check_model_installed(name)
            
            # Column 0: Filename
            item_name = QTableWidgetItem(name)
            self.models_table.setItem(i, 0, item_name)
            
            # Column 1: Type
            item_type = QTableWidgetItem(folder)
            self.models_table.setItem(i, 1, item_type)
            
            # Column 2: Directory
            item_dir = QTableWidgetItem(f"models/{folder}/")
            self.models_table.setItem(i, 2, item_dir)
            
            # Column 3: Status
            if is_installed:
                existing += 1
                status_text = "EXISTS"
                status_color = QColor("#10b981")
            else:
                missing += 1
                status_text = "MISSING"
                status_color = QColor("#ef4444")
            
            item_status = QTableWidgetItem(status_text)
            item_status.setForeground(status_color)
            font = item_status.font()
            font.setBold(True)
            item_status.setFont(font)
            self.models_table.setItem(i, 3, item_status)
            
            # Column 4: Source
            source_text = url if url else "Unknown"
            item_source = QTableWidgetItem(source_text)
            if url:
                item_source.setForeground(QColor("#3b82f6"))
            self.models_table.setItem(i, 4, item_source)
            
            # Column 5: Action Button
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 4, 4, 4)
            btn = QPushButton("Download" if not is_installed else "Re-download")
            btn.setObjectName("tableActionBtn")
            btn.setCursor(Qt.PointingHandCursor)
            
            if url:
                if not is_installed: downloadable += 1
                btn.clicked.connect(lambda c, n=name, u=url: self.add_model_to_queue(n, u))
            else:
                btn.setText("Manual URL")
                btn.clicked.connect(lambda c, n=name: self.show_url_input_dialog(n))
                
            action_layout.addWidget(btn)
            self.models_table.setCellWidget(i, 5, action_widget)
            
            item_name.setToolTip(name)
            item_source.setToolTip(source_text)

        self.stat_total.setText(str(total))
        self.stat_existing.setText(str(existing))
        self.stat_missing.setText(str(missing))
        self.stat_downloadable.setText(str(downloadable))
        self.table_footer.setText(f"Total: {total} | Existing: {existing} | Missing: {missing}")

    def install_all_missing(self):
        """1-Click Install All functionality for missing nodes and models with URLs."""
        # Get currently selected workflow
        row = self.workflow_list_table.currentRow()
        if row < 0:
            return
        item = self.workflow_list_table.item(row, 0)
        if not item:
            return
        current_workflow = item.text()
        if not current_workflow:
            return

        deps = check_workflow_dependencies(current_workflow)
        items_added = 0
        
        # Add missing nodes with URLs
        for node in deps["nodes"]:
            if not node["installed"] and node["folder"] != "Builtin" and node["url"]:
                # Check if already in queue to avoid duplicates
                if not any(n[0] == node["url"] for n in self.queue_nodes):
                    self.add_node_to_queue(node["url"], node["folder"])
                    items_added += 1
                    
        # Add missing models with URLs
        for model in deps["models"]:
            if not model["installed"] and model["url"]:
                # Check if already in queue
                if not any(m[0] == model["name"] for m in self.queue_models):
                    self.add_model_to_queue(model["name"], model["url"])
                    items_added += 1
                    
        if items_added > 0:
            QMessageBox.information(self, "1-Click Install", f"{items_added} items added to the download queue.")
            self.start_queue_download() # Automatically start the queue
        else:
            QMessageBox.information(self, "1-Click Install", "No downloadable items found. Some models may need a manual source URL.")
    
    def add_node_to_queue(self, url, name):
        if (url, name) not in self.queue_nodes:
            self.queue_nodes.append((url, name))
            self.status_bar.showMessage(f"Added {name} to queue")
            self.start_queue_download()
    
    def add_model_to_queue(self, name, url):
        if (name, url) not in self.queue_models:
            self.queue_models.append((name, url))
            self.status_bar.showMessage(f"Added {name[:30]} to queue")
            self.start_queue_download()
    
    def show_url_input_dialog(self, model_name):
        """Show dialog for user to input download URL for unknown model."""
        folder = guess_model_folder(model_name)
        dialog = ModelUrlInputDialog(model_name, folder, self)
        if dialog.exec() == QDialog.Accepted:
            url, save_to_db = dialog.get_result()
            if url:
                if save_to_db:
                    success, msg = save_url_to_model_db(model_name, url, folder)
                    if success:
                        self.status_bar.showMessage(f"Saved {model_name} to DB")
                
                self.add_model_to_queue(model_name, url)
    
    def clear_queue(self):
        self.queue_nodes = []
        self.queue_models = []
        self.queue_progress_bar.setValue(0)
        self.queue_current_label.setText("Ready")
        self.queue_detail_label.setText("")
        self.queue_progress_frame.hide()
    
    def start_queue_download(self):
        if not self.queue_nodes and not self.queue_models:
            return
            
        if hasattr(self, 'download_worker') and self.download_worker.isRunning():
            return  # Already running, queued items will be picked up on next start maybe. 
            # Or better, we only pop what was given. But Downloadworker takes lists up front.
        
        self.queue_progress_frame.show()
        self.run_btn.setEnabled(False)
        
        # Pass a copy so we can clear our local queue or manage it
        self.download_worker = DownloadQueueWorker(list(self.queue_nodes), list(self.queue_models))
        self.download_worker.item_started.connect(self.on_queue_item_started)
        self.download_worker.item_progress.connect(self.on_queue_item_progress)
        self.download_worker.item_finished.connect(self.on_queue_item_finished)
        self.download_worker.all_finished.connect(self.on_queue_all_finished)
        self.download_worker.start()
        
        # Clean local queues as they are now handed off to worker
        self.queue_nodes.clear()
        self.queue_models.clear()
    
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
            
            # Estimate percentage based on current item download + overall index progress
            # To be accurate we'd need more logic, but this is ok for now.
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
        self.queue_progress_frame.hide()
        
        self.run_btn.setEnabled(True)
        
        # Refresh the tabular UI to show EXSTS instead of MISSING
        self.populate_all_models_table()

        
        self.status_bar.showMessage("All downloads complete! ✓")
        
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
        
        # UI toggling for Install vs Run
        if not status.get("comfy_installed", False):
            self.install_btn.show()
            self.run_btn.hide()
            self.run_btn.setEnabled(False)
        else:
            self.install_btn.hide()
            self.run_btn.show()
            self.run_btn.setEnabled(True)
    
    def handle_install_action(self):
        """Handle ComfyUI Core Installation - opens the install dialog."""
        dialog = InstallDialog(self)
        dialog.exec()
        # Refresh status after dialog closes
        self.update_system_status()
        self.refresh_system_status()

    def handle_comfy_action(self):
        """Handle Run ComfyUI."""
        success, msg = run_comfyui()
        if success:
            QMessageBox.information(self, "ComfyUI", "ComfyUI is starting!\n\nhttp://localhost:8188")
        else:
            QMessageBox.warning(self, "Error", msg)
    
    def refresh_system_status(self):
        """Refresh system status panel with current info (runs in background thread)."""
        self.comfy_status.setText("확인 중...")
        self.comfy_status.setStyleSheet("color: #9ca3af; font-weight: bold;")
        self.nodes_status.setText("확인 중...")
        self.nodes_status.setStyleSheet("color: #9ca3af; font-weight: bold;")
        self.models_status.setText(f"✅ {len(MODEL_DB)}개 등록됨")
        self.models_status.setStyleSheet("color: #10b981; font-weight: bold;")

        if hasattr(self, '_system_status_worker') and self._system_status_worker.isRunning():
            return
        self._system_status_worker = SystemStatusWorker()
        self._system_status_worker.result_signal.connect(self._on_system_status_done)
        self._system_status_worker.start()

    def _on_system_status_done(self, result):
        """Handle system status worker results on the main thread."""
        # ComfyUI status
        comfy_info = result.get("comfy_info")
        comfy_error = result.get("comfy_error")
        if comfy_error:
            self.comfy_status.setText(f"❌ 오류: {comfy_error}")
            self.comfy_status.setStyleSheet("color: #ef4444; font-weight: bold;")
        elif comfy_info and comfy_info.get("error"):
            self.comfy_status.setText(f"⚠️ {comfy_info['error']}")
            self.comfy_status.setStyleSheet("color: #ef4444; font-weight: bold;")
        elif comfy_info and comfy_info.get("update_available"):
            self.comfy_status.setText(f"⚠️ {comfy_info['commits_behind']}개 커밋 뒤처짐")
            self.comfy_status.setStyleSheet("color: #eab308; font-weight: bold;")
            self.comfy_update_btn.show()
        elif comfy_info:
            self.comfy_status.setText(f"✅ 최신 ({comfy_info['current_commit']})")
            self.comfy_status.setStyleSheet("color: #10b981; font-weight: bold;")
            self.comfy_update_btn.hide()

        # Custom Nodes status
        nodes_info = result.get("nodes_info")
        nodes_error = result.get("nodes_error")
        if nodes_error:
            self.nodes_status.setText(f"❌ 오류: {nodes_error}")
            self.nodes_status.setStyleSheet("color: #ef4444; font-weight: bold;")
        elif nodes_info is not None:
            total = len(nodes_info)
            updatable = len([n for n in nodes_info if n["update_available"]])
            if updatable > 0:
                self.nodes_status.setText(f"⚠️ {total}개 중 {updatable}개 업데이트 가능")
                self.nodes_status.setStyleSheet("color: #eab308; font-weight: bold;")
                self.nodes_update_btn.show()
            else:
                self.nodes_status.setText(f"✅ {total}개 모두 최신")
                self.nodes_status.setStyleSheet("color: #10b981; font-weight: bold;")
                self.nodes_update_btn.hide()

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

        self._comfy_update_worker = ComfyUpdateWorker()
        self._comfy_update_worker.result_signal.connect(self._on_comfy_update_done)
        self._comfy_update_worker.start()

    def _on_comfy_update_done(self, success, msg):
        """Handle ComfyUI update worker results on the main thread."""
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

        self._nodes_update_worker = NodesUpdateWorker()
        self._nodes_update_worker.result_signal.connect(self._on_nodes_update_done)
        self._nodes_update_worker.start()

    def _on_nodes_update_done(self, success_count, fail_count, results):
        """Handle custom nodes update worker results on the main thread."""
        msg = f"완료!\n\n성공: {success_count}개\n실패: {fail_count}개"
        if fail_count > 0:
            failed_names = [r["name"] for r in results if not r["success"]]
            msg += f"\n\n실패 목록: {', '.join(failed_names[:5])}"

        QMessageBox.information(self, "업데이트 완료", msg)
        self.refresh_system_status()

