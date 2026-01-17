"""
DSUComfyCG Manager - URL Input Dialog for Unknown Models
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QMessageBox
)
from PySide6.QtCore import Qt


class ModelUrlInputDialog(QDialog):
    """Dialog for user to input download URL for unknown models."""
    
    def __init__(self, model_name, target_folder, parent=None):
        super().__init__(parent)
        self.model_name = model_name
        self.target_folder = target_folder
        self.url = None
        self.save_to_db = False
        
        self.setWindowTitle("모델 다운로드 URL 입력")
        self.setMinimumWidth(500)
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
                padding: 8px;
                color: #fff;
                font-size: 12px;
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
            QPushButton#cancelBtn {
                background-color: #555;
            }
            QPushButton#cancelBtn:hover {
                background-color: #666;
            }
            QCheckBox {
                color: #aaa;
            }
        """)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Warning icon and title
        title = QLabel("⚠️ 모델을 찾을 수 없습니다")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffcc00;")
        layout.addWidget(title)
        
        # Model info
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #2a2a4e; border-radius: 8px; padding: 10px;")
        info_layout = QVBoxLayout(info_frame)
        
        model_label = QLabel(f"<b>모델명:</b> {self.model_name}")
        model_label.setStyleSheet("font-size: 13px;")
        info_layout.addWidget(model_label)
        
        folder_label = QLabel(f"<b>저장 위치:</b> ComfyUI/models/{self.target_folder}")
        folder_label.setStyleSheet("font-size: 13px; color: #00ffcc;")
        info_layout.addWidget(folder_label)
        
        layout.addWidget(info_frame)
        
        # URL input
        url_label = QLabel("다운로드 URL:")
        url_label.setStyleSheet("font-size: 12px; margin-top: 10px;")
        layout.addWidget(url_label)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://huggingface.co/repo/file.safetensors")
        layout.addWidget(self.url_input)
        
        # Examples
        examples = QLabel(
            "<b>예시:</b><br>"
            "• https://huggingface.co/Kijai/LTXV2_comfy/resolve/main/VAE/model.safetensors<br>"
            "• https://civitai.com/api/download/models/12345"
        )
        examples.setStyleSheet("font-size: 11px; color: #888;")
        examples.setWordWrap(True)
        layout.addWidget(examples)
        
        # Save to DB checkbox
        self.save_checkbox = QCheckBox("이 모델 정보를 DB에 저장 (다음에 자동 사용)")
        self.save_checkbox.setChecked(True)
        layout.addWidget(self.save_checkbox)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        skip_btn = QPushButton("건너뛰기")
        skip_btn.setObjectName("cancelBtn")
        skip_btn.clicked.connect(self.reject)
        btn_layout.addWidget(skip_btn)
        
        download_btn = QPushButton("다운로드")
        download_btn.clicked.connect(self._on_download)
        btn_layout.addWidget(download_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "오류", "URL을 입력해주세요.")
            return
        
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "오류", "올바른 URL 형식이 아닙니다.")
            return
        
        self.url = url
        self.save_to_db = self.save_checkbox.isChecked()
        self.accept()
    
    def get_result(self):
        """Returns (url, save_to_db) or (None, False) if cancelled."""
        return self.url, self.save_to_db
