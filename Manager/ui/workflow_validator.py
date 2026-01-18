"""
DSUComfyCG Manager - Workflow Validator Dialog
모든 의존성이 해결될 때까지 워크플로우 등록을 차단합니다.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QScrollArea, QWidget, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.checker import (
    check_workflow_dependencies, save_url_to_model_db, 
    guess_model_folder, FALLBACK_NODE_DB
)


class WorkflowValidatorDialog(QDialog):
    """
    워크플로우 의존성 검증 다이얼로그.
    Unknown 의존성이 있으면 URL 입력을 강제합니다.
    """
    
    def __init__(self, workflow_filename, parent=None):
        super().__init__(parent)
        self.workflow_filename = workflow_filename
        self.pending_urls = {}  # {name: (type, url_input_widget, folder)}
        self.all_resolved = False
        
        self.setWindowTitle("워크플로우 의존성 검증")
        self.setMinimumSize(700, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a2e;
            }
            QLabel {
                color: #fff;
            }
            QLineEdit {
                background-color: #2a2a4e;
                border: 1px solid #3a3a6e;
                border-radius: 4px;
                padding: 6px;
                color: #fff;
            }
            QLineEdit:focus {
                border-color: #00ffcc;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #555;
            }
            QPushButton#cancelBtn {
                background-color: #666;
            }
            QTreeWidget {
                background-color: #2a2a4e;
                border: none;
                color: white;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #1a1a2e;
                color: #888;
                padding: 6px;
                border: none;
            }
        """)
        
        self._setup_ui()
        self._load_dependencies()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel(f"📋 {self.workflow_filename}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)
        
        # Resolved section
        resolved_label = QLabel("✅ 해결됨")
        resolved_label.setStyleSheet("color: #00ffcc; font-weight: bold;")
        layout.addWidget(resolved_label)
        
        self.resolved_tree = QTreeWidget()
        self.resolved_tree.setHeaderLabels(["이름", "유형", "상태"])
        self.resolved_tree.setMaximumHeight(150)
        header = self.resolved_tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.resolved_tree)
        
        # Unresolved section
        self.unresolved_label = QLabel("⚠️ 미해결 - URL 입력 필요")
        self.unresolved_label.setStyleSheet("color: #ffd93d; font-weight: bold;")
        layout.addWidget(self.unresolved_label)
        
        # Scroll area for unresolved items
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #2a2a4e; border-radius: 8px;")
        
        self.unresolved_container = QWidget()
        self.unresolved_layout = QVBoxLayout(self.unresolved_container)
        self.unresolved_layout.setSpacing(10)
        scroll.setWidget(self.unresolved_container)
        layout.addWidget(scroll)
        
        # Warning message
        self.warning_label = QLabel("⚠️ 모든 의존성을 해결해야 등록할 수 있습니다.")
        self.warning_label.setStyleSheet("color: #ff6b6b; font-size: 12px;")
        layout.addWidget(self.warning_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("취소")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        self.register_btn = QPushButton("등록 완료")
        self.register_btn.setEnabled(False)
        self.register_btn.clicked.connect(self._on_register)
        btn_layout.addWidget(self.register_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_dependencies(self):
        """워크플로우 의존성 로드 및 분류."""
        deps = check_workflow_dependencies(self.workflow_filename)
        
        resolved_count = 0
        unresolved_count = 0
        
        # Check nodes
        for node in deps["nodes"]:
            folder = node["folder"]
            if folder == "Builtin":
                continue
            
            if folder == "Unknown":
                self._add_unresolved_item(node["type"], "node", None)
                unresolved_count += 1
            else:
                item = QTreeWidgetItem([folder, "노드", "✓"])
                item.setForeground(2, QColor("#00ffcc"))
                self.resolved_tree.addTopLevelItem(item)
                resolved_count += 1
        
        # Check models
        for model in deps["models"]:
            name = model["name"]
            
            if model["installed"]:
                item = QTreeWidgetItem([name[:40], "모델", "✓ 설치됨"])
                item.setForeground(2, QColor("#00ffcc"))
                self.resolved_tree.addTopLevelItem(item)
                resolved_count += 1
            elif model["url"]:
                item = QTreeWidgetItem([name[:40], "모델", "✓ URL확보"])
                item.setForeground(2, QColor("#6b9fff"))
                self.resolved_tree.addTopLevelItem(item)
                resolved_count += 1
            else:
                folder = guess_model_folder(name)
                self._add_unresolved_item(name, "model", folder)
                unresolved_count += 1
        
        # Update labels
        self.unresolved_label.setText(f"⚠️ 미해결 ({unresolved_count}) - URL 입력 필요")
        
        if unresolved_count == 0:
            self.all_resolved = True
            self.register_btn.setEnabled(True)
            self.warning_label.setText("✅ 모든 의존성이 해결되었습니다!")
            self.warning_label.setStyleSheet("color: #00ffcc; font-size: 12px;")
    
    def _add_unresolved_item(self, name, dep_type, folder):
        """미해결 항목 추가."""
        frame = QFrame()
        frame.setStyleSheet("background-color: #3a3a5e; border-radius: 6px; padding: 10px;")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setSpacing(8)
        
        # Name and type
        type_str = "노드" if dep_type == "node" else "모델"
        name_label = QLabel(f"<b>{type_str}:</b> {name}")
        name_label.setStyleSheet("font-size: 13px;")
        frame_layout.addWidget(name_label)
        
        if folder:
            folder_label = QLabel(f"<span style='color: #888;'>저장 위치: ComfyUI/models/{folder}</span>")
            frame_layout.addWidget(folder_label)
        
        # URL input
        url_layout = QHBoxLayout()
        url_input = QLineEdit()
        url_input.setPlaceholderText("https://github.com/... 또는 https://huggingface.co/...")
        url_input.textChanged.connect(self._check_all_filled)
        url_layout.addWidget(url_input)
        frame_layout.addLayout(url_layout)
        
        self.unresolved_layout.addWidget(frame)
        self.pending_urls[name] = (dep_type, url_input, folder)
    
    def _check_all_filled(self):
        """모든 URL이 입력되었는지 확인."""
        all_filled = all(
            widget.text().strip().startswith(("http://", "https://"))
            for _, (_, widget, _) in self.pending_urls.items()
        )
        self.register_btn.setEnabled(all_filled)
        
        if all_filled:
            self.warning_label.setText("✅ 모든 URL이 입력되었습니다. 등록하세요.")
            self.warning_label.setStyleSheet("color: #00ffcc; font-size: 12px;")
        else:
            self.warning_label.setText("⚠️ 모든 의존성을 해결해야 등록할 수 있습니다.")
            self.warning_label.setStyleSheet("color: #ff6b6b; font-size: 12px;")
    
    def _on_register(self):
        """등록 버튼 클릭 - URL들을 DB에 저장."""
        saved_count = 0
        
        for name, (dep_type, widget, folder) in self.pending_urls.items():
            url = widget.text().strip()
            if not url:
                continue
            
            if dep_type == "model":
                # Save to models_db.json
                success, msg = save_url_to_model_db(name, url, folder or "checkpoints")
                if success:
                    saved_count += 1
            else:
                # Save to FALLBACK_NODE_DB (in-memory for now)
                # TODO: Persist to file
                folder_name = name.replace(" ", "-").replace("(", "").replace(")", "")
                FALLBACK_NODE_DB[name] = (folder_name, url)
                saved_count += 1
        
        QMessageBox.information(
            self, "등록 완료",
            f"워크플로우가 등록되었습니다.\n{saved_count}개의 새 URL이 DB에 저장되었습니다."
        )
        self.all_resolved = True
        self.accept()
    
    def is_resolved(self):
        """모든 의존성이 해결되었는지 반환."""
        return self.all_resolved
