"""
ComfyUI Installation Dialog
Provides environment selection, addon/node checkboxes, and progress display.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QCheckBox, QGroupBox, QPushButton, QProgressBar,
    QTextEdit, QComboBox, QScrollArea, QWidget, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont


class InstallWorker(QThread):
    """Background thread for ComfyUI installation."""
    progress = Signal(str)
    finished = Signal(bool, str)
    
    def __init__(self, env_name, options):
        super().__init__()
        self.env_name = env_name
        self.options = options
    
    def run(self):
        from core.checker import install_comfyui
        success, msg = install_comfyui(
            env_name=self.env_name,
            options=self.options,
            progress_cb=self.progress.emit
        )
        self.finished.emit(success, msg)


class InstallDialog(QDialog):
    """Dialog for ComfyUI installation with option selection."""
    
    # Default custom nodes from Easy-Install reference
    DEFAULT_NODES = [
        ("https://github.com/Comfy-Org/ComfyUI-Manager", "comfyui-manager", "ComfyUI Manager", True),
        ("https://github.com/yolain/ComfyUI-Easy-Use", "ComfyUI-Easy-Use", "Easy Use", True),
        ("https://github.com/Fannovel16/comfyui_controlnet_aux", "comfyui_controlnet_aux", "ControlNet Aux", True),
        ("https://github.com/rgthree/rgthree-comfy", "rgthree-comfy", "rgthree Comfy", True),
        ("https://github.com/MohammadAboulEla/ComfyUI-iTools", "comfyui-itools", "iTools", False),
        ("https://github.com/city96/ComfyUI-GGUF", "ComfyUI-GGUF", "GGUF Support", True),
        ("https://github.com/gseth/ControlAltAI-Nodes", "controlaltai-nodes", "ControlAltAI", False),
        ("https://github.com/lquesada/ComfyUI-Inpaint-CropAndStitch", "comfyui-inpaint-cropandstitch", "Inpaint Crop&Stitch", False),
        ("https://github.com/1038lab/ComfyUI-RMBG", "comfyui-rmbg", "Background Removal", True),
        ("https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite", "comfyui-videohelpersuite", "Video Helper Suite", True),
        ("https://github.com/shiimizu/ComfyUI-TiledDiffusion", "ComfyUI-TiledDiffusion", "Tiled Diffusion", False),
        ("https://github.com/kijai/ComfyUI-KJNodes", "comfyui-kjnodes", "KJ Nodes", True),
        ("https://github.com/kijai/ComfyUI-WanVideoWrapper", "ComfyUI-WanVideoWrapper", "Wan Video", True),
        ("https://github.com/1038lab/ComfyUI-QwenVL", "ComfyUI-QwenVL", "QwenVL", False),
        ("https://github.com/kijai/ComfyUI-WanAnimatePreprocess", "ComfyUI-WanAnimatePreprocess", "Wan Animate Preprocess", False),
    ]
    
    # Optional addon packages
    ADDON_PACKAGES = [
        ("onnxruntime-gpu", "ONNX Runtime GPU", "GPU 가속 추론", False),
        ("triton", "Triton", "커널 최적화 (실험적)", False),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ComfyUI 설치")
        self.setMinimumSize(550, 650)
        self.setMaximumSize(650, 800)
        self.worker = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # ── Header ──
        header = QLabel("🚀 ComfyUI 설치")
        header.setFont(QFont("", 16, QFont.Bold))
        layout.addWidget(header)
        
        desc = QLabel("Python 3.12.10 + PyTorch 2.9.1 + CUDA 13.0 을 자동으로 설치합니다.")
        desc.setStyleSheet("color: #888;")
        layout.addWidget(desc)
        
        # ── Environment Name ──
        env_group = QGroupBox("환경 설정")
        env_layout = QHBoxLayout(env_group)
        env_layout.addWidget(QLabel("환경 이름:"))
        self.env_name_input = QLineEdit("stable")
        self.env_name_input.setPlaceholderText("stable, latest, dev, ...")
        env_layout.addWidget(self.env_name_input)
        layout.addWidget(env_group)
        
        # ── Shared Models ──
        self.shared_models_cb = QCheckBox("공유 모델 폴더 사용 (models/)")
        self.shared_models_cb.setChecked(True)
        self.shared_models_cb.setToolTip("모든 환경이 같은 모델 폴더를 공유합니다.")
        layout.addWidget(self.shared_models_cb)
        
        # ── Scrollable area for options ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)
        
        # ── Custom Nodes ──
        nodes_group = QGroupBox("커스텀 노드 (선택)")
        nodes_layout = QVBoxLayout(nodes_group)
        self.node_checkboxes = []
        for url, folder, label, default_on in self.DEFAULT_NODES:
            cb = QCheckBox(label)
            cb.setChecked(default_on)
            cb.setProperty("url", url)
            cb.setProperty("folder", folder)
            nodes_layout.addWidget(cb)
            self.node_checkboxes.append(cb)
        
        # Select all / none buttons
        btn_row = QHBoxLayout()
        select_all_btn = QPushButton("전체 선택")
        select_all_btn.clicked.connect(lambda: self._set_all_nodes(True))
        select_none_btn = QPushButton("전체 해제")
        select_none_btn.clicked.connect(lambda: self._set_all_nodes(False))
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(select_none_btn)
        btn_row.addStretch()
        nodes_layout.addLayout(btn_row)
        scroll_layout.addWidget(nodes_group)
        
        # ── Addon Packages ──
        addons_group = QGroupBox("추가 패키지 (선택)")
        addons_layout = QVBoxLayout(addons_group)
        self.addon_checkboxes = []
        for pkg_name, label, desc, default_on in self.ADDON_PACKAGES:
            cb = QCheckBox(f"{label} — {desc}")
            cb.setChecked(default_on)
            cb.setProperty("pkg_name", pkg_name)
            addons_layout.addWidget(cb)
            self.addon_checkboxes.append(cb)
        scroll_layout.addWidget(addons_group)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)
        
        # ── Progress ──
        self.progress_group = QGroupBox("설치 진행 상황")
        progress_layout = QVBoxLayout(self.progress_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        progress_layout.addWidget(self.progress_bar)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px;")
        self.log_text.hide()
        progress_layout.addWidget(self.log_text)
        self.progress_group.hide()
        layout.addWidget(self.progress_group)
        
        # ── Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        self.install_btn = QPushButton("🚀 설치 시작")
        self.install_btn.setStyleSheet("""
            QPushButton {
                background: #10b981; color: white; font-weight: bold;
                padding: 8px 24px; border-radius: 6px; font-size: 14px;
            }
            QPushButton:hover { background: #059669; }
            QPushButton:disabled { background: #6b7280; }
        """)
        self.install_btn.clicked.connect(self.start_install)
        btn_layout.addWidget(self.install_btn)
        layout.addLayout(btn_layout)
    
    def _set_all_nodes(self, checked):
        for cb in self.node_checkboxes:
            cb.setChecked(checked)
    
    def start_install(self):
        env_name = self.env_name_input.text().strip()
        if not env_name:
            self.env_name_input.setFocus()
            return
        
        # Sanitize env name
        env_name = env_name.lower().replace(" ", "_")
        
        # Collect options
        selected_nodes = []
        for cb in self.node_checkboxes:
            if cb.isChecked():
                selected_nodes.append((cb.property("url"), cb.property("folder")))
        
        selected_addons = []
        for cb in self.addon_checkboxes:
            if cb.isChecked():
                selected_addons.append(cb.property("pkg_name"))
        
        options = {
            "install_custom_nodes": selected_nodes,
            "install_addons": selected_addons,
            "shared_models": self.shared_models_cb.isChecked(),
        }
        
        # Disable inputs
        self.install_btn.setEnabled(False)
        self.install_btn.setText("설치 중...")
        self.env_name_input.setEnabled(False)
        self.cancel_btn.setText("닫기")
        
        # Show progress
        self.progress_group.show()
        self.progress_bar.show()
        self.log_text.show()
        
        # Start install in background thread
        self.worker = InstallWorker(env_name, options)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()
    
    def on_progress(self, msg):
        self.log_text.append(msg)
        # Scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        QApplication.processEvents()
    
    def on_finished(self, success, msg):
        self.progress_bar.hide()
        self.install_btn.setEnabled(True)
        
        if success:
            self.install_btn.setText("✅ 설치 완료!")
            self.install_btn.setStyleSheet("""
                QPushButton {
                    background: #10b981; color: white; font-weight: bold;
                    padding: 8px 24px; border-radius: 6px; font-size: 14px;
                }
            """)
            self.log_text.append(f"\n🎉 {msg}")
        else:
            self.install_btn.setText("❌ 설치 실패")
            self.install_btn.setStyleSheet("""
                QPushButton {
                    background: #ef4444; color: white; font-weight: bold;
                    padding: 8px 24px; border-radius: 6px; font-size: 14px;
                }
            """)
            self.log_text.append(f"\n❌ {msg}")
