import os
from pathlib import Path
from PySide6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSlider, QComboBox, QCheckBox,
    QListWidget, QAbstractItemView, QFileDialog
)
from PySide6.QtCore import Qt, Signal

from core.bgm_helper import BgmConfig, AUDIO_EXTENSIONS

class AudioListWidget(QListWidget):
    """支持拖拽音频文件的列表组件"""
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setStyleSheet("""
            QListWidget {
                background-color: #f8fafc;
                border: 1px dashed #cbd5e1;
                border-radius: 6px;
                padding: 4px;
                font-size: 12px;
                color: #0f172a;
            }
            QListWidget::item {
                padding: 4px 6px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #f1f5f9;
            }
            QListWidget::item:selected {
                background-color: #eff6ff;
                color: #1d4ed8;
            }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        valid_paths = []
        for u in urls:
            p = u.toLocalFile()
            if os.path.isfile(p) and Path(p).suffix.lower() in AUDIO_EXTENSIONS:
                valid_paths.append(str(Path(p).resolve()))
            elif os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if Path(f).suffix.lower() in AUDIO_EXTENSIONS:
                            valid_paths.append(str(Path(root, f).resolve()))
        if valid_paths:
            self.files_dropped.emit(valid_paths)
            event.acceptProposedAction()
        else:
            event.ignore()

class BgmWidget(QFrame):
    """优雅浅色折叠式背景音乐配置组件 (默认折叠，紧凑美观)"""
    config_changed = Signal()

    def __init__(self, title: str = "添加背景音乐", parent=None):
        super().__init__(parent)
        self.setObjectName("bgmCard")
        self.setStyleSheet("""
            QFrame#bgmCard {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
        """)

        self._is_expanded = False

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        # 1. 顶层标题与折叠摘要栏 (常驻显示)
        header_bar = QHBoxLayout()
        header_bar.setContentsMargins(0, 0, 0, 0)
        header_bar.setSpacing(10)

        # 启用复选框
        self.chk_enable = QCheckBox("添加背景音乐")
        self.chk_enable.setCursor(Qt.PointingHandCursor)
        self.chk_enable.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                font-weight: 600;
                color: #0f172a;
            }
        """)
        self.chk_enable.toggled.connect(self._on_enable_toggled)

        # 状态描述胶囊标签
        self.lbl_status_tag = QLabel("未开启")
        self.lbl_status_tag.setStyleSheet("""
            QLabel {
                background-color: #f1f5f9;
                color: #64748b;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            }
        """)

        # 展开/折叠按钮
        self.btn_toggle = QPushButton("展开配置 ▾")
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setFixedHeight(26)
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                color: #475569;
                font-size: 12px;
                font-weight: 500;
                padding: 2px 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                color: #0f172a;
                border-color: #cbd5e1;
            }
        """)
        self.btn_toggle.clicked.connect(self.toggle_expanded)

        header_bar.addWidget(self.chk_enable)
        header_bar.addWidget(self.lbl_status_tag)
        header_bar.addStretch()
        header_bar.addWidget(self.btn_toggle)
        card_layout.addLayout(header_bar)

        # 2. 折叠面板内容区 (默认隐藏，展开时呈现完整配置)
        self.body_widget = QWidget()
        body_layout = QVBoxLayout(self.body_widget)
        body_layout.setContentsMargins(0, 4, 0, 0)
        body_layout.setSpacing(10)

        # 分割线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #f1f5f9; background-color: #f1f5f9; height: 1px; border: none;")
        body_layout.addWidget(sep)

        # 音频列表与操作按钮
        list_box = QHBoxLayout()
        list_box.setSpacing(8)

        self.audio_list = AudioListWidget()
        self.audio_list.setFixedHeight(75)
        self.audio_list.files_dropped.connect(self._add_audio_paths)
        list_box.addWidget(self.audio_list, stretch=1)

        btn_vbox = QVBoxLayout()
        btn_vbox.setSpacing(5)
        
        self.btn_add = QPushButton("添加音频")
        self.btn_add.setFixedHeight(26)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._choose_audio_files)

        self.btn_remove = QPushButton("移除")
        self.btn_remove.setFixedHeight(26)
        self.btn_remove.setCursor(Qt.PointingHandCursor)
        self.btn_remove.clicked.connect(self._remove_selected_audios)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setFixedHeight(26)
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear_audios)

        btn_vbox.addWidget(self.btn_add)
        btn_vbox.addWidget(self.btn_remove)
        btn_vbox.addWidget(self.btn_clear)
        list_box.addLayout(btn_vbox)
        body_layout.addLayout(list_box)

        # 播放参数控制 (音量滑块、循环模式、播放顺序)
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(2, 2, 2, 2)
        grid_layout.setHorizontalSpacing(14)
        grid_layout.setVerticalSpacing(8)

        # 音乐音量
        lbl_bgm_vol = QLabel("音乐音量:")
        lbl_bgm_vol.setStyleSheet("color: #475569; font-size: 12px; font-weight: 500;")
        self.slider_bgm = QSlider(Qt.Horizontal)
        self.slider_bgm.setRange(0, 200)
        self.slider_bgm.setValue(100)
        self.slider_bgm.setFixedHeight(18)
        self.lbl_bgm_val = QLabel("100%")
        self.lbl_bgm_val.setFixedWidth(42)
        self.lbl_bgm_val.setStyleSheet("color: #2563eb; font-weight: bold; font-family: Consolas, monospace; font-size: 12px;")
        self.slider_bgm.valueChanged.connect(self._on_bgm_vol_changed)

        # 循环模式 (高度充足，内边距宽裕，杜绝文字显示一半)
        lbl_loop = QLabel("循环模式:")
        lbl_loop.setStyleSheet("color: #475569; font-size: 12px; font-weight: 500;")
        self.combo_loop = QComboBox()
        self.combo_loop.setFixedHeight(28)
        self.combo_loop.setMinimumWidth(110)
        self.combo_loop.addItems(["无限循环", "播放一次"])
        self.combo_loop.currentIndexChanged.connect(self._on_param_changed)

        # 原声音量
        lbl_orig_vol = QLabel("原声音量:")
        lbl_orig_vol.setStyleSheet("color: #475569; font-size: 12px; font-weight: 500;")
        self.slider_orig = QSlider(Qt.Horizontal)
        self.slider_orig.setRange(0, 200)
        self.slider_orig.setValue(100)
        self.slider_orig.setFixedHeight(18)
        self.lbl_orig_val = QLabel("100%")
        self.lbl_orig_val.setFixedWidth(42)
        self.lbl_orig_val.setStyleSheet("color: #2563eb; font-weight: bold; font-family: Consolas, monospace; font-size: 12px;")
        self.slider_orig.valueChanged.connect(self._on_orig_vol_changed)

        # 播放顺序
        lbl_order = QLabel("播放顺序:")
        lbl_order.setStyleSheet("color: #475569; font-size: 12px; font-weight: 500;")
        self.combo_order = QComboBox()
        self.combo_order.setFixedHeight(28)
        self.combo_order.setMinimumWidth(110)
        self.combo_order.addItems(["顺序播放", "随机播放"])
        self.combo_order.currentIndexChanged.connect(self._on_param_changed)

        # 网格排布
        grid_layout.addWidget(lbl_bgm_vol, 0, 0)
        grid_layout.addWidget(self.slider_bgm, 0, 1)
        grid_layout.addWidget(self.lbl_bgm_val, 0, 2)
        grid_layout.addWidget(lbl_loop, 0, 3)
        grid_layout.addWidget(self.combo_loop, 0, 4)

        grid_layout.addWidget(lbl_orig_vol, 1, 0)
        grid_layout.addWidget(self.slider_orig, 1, 1)
        grid_layout.addWidget(self.lbl_orig_val, 1, 2)
        grid_layout.addWidget(lbl_order, 1, 3)
        grid_layout.addWidget(self.combo_order, 1, 4)

        grid_layout.setColumnStretch(1, 1)
        grid_layout.setColumnStretch(4, 0)
        body_layout.addLayout(grid_layout)

        card_layout.addWidget(self.body_widget)

        # 默认折叠：隐藏 body 内容
        self.body_widget.setVisible(False)
        self._update_status_tag()

    def toggle_expanded(self):
        """展开或折叠面板"""
        self.set_expanded(not self._is_expanded)

    def set_expanded(self, expanded: bool):
        """设置展开状态"""
        self._is_expanded = expanded
        self.body_widget.setVisible(expanded)
        self.btn_toggle.setText("收起配置 ▴" if expanded else "展开配置 ▾")

    def isChecked(self) -> bool:
        """向后兼容 QGroupBox 接口"""
        return self.chk_enable.isChecked()

    def setChecked(self, checked: bool):
        """向后兼容 QGroupBox 接口"""
        self.chk_enable.setChecked(checked)

    def _on_enable_toggled(self, checked: bool):
        # 若用户勾选启用且尚未添加音频，则自动展开便于用户快速添加音频
        if checked and self.audio_list.count() == 0 and not self._is_expanded:
            self.set_expanded(True)
        self._update_status_tag()
        self.config_changed.emit()

    def _on_bgm_vol_changed(self, val: int):
        self.lbl_bgm_val.setText(f"{val}%")
        self._update_status_tag()
        self.config_changed.emit()

    def _on_orig_vol_changed(self, val: int):
        if val == 0:
            self.lbl_orig_val.setText("静音")
        else:
            self.lbl_orig_val.setText(f"{val}%")
        self._update_status_tag()
        self.config_changed.emit()

    def _on_param_changed(self):
        self._update_status_tag()
        self.config_changed.emit()

    def _update_status_tag(self):
        """刷新胶囊状态文本与样式"""
        if not self.chk_enable.isChecked():
            self.lbl_status_tag.setText("未开启")
            self.lbl_status_tag.setStyleSheet("""
                background-color: #f1f5f9;
                color: #64748b;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            """)
            return

        cnt = self.audio_list.count()
        if cnt == 0:
            self.lbl_status_tag.setText("已开启 · 待添加音频")
            self.lbl_status_tag.setStyleSheet("""
                background-color: #fffbeb;
                color: #b45309;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            """)
        else:
            loop_desc = "循环" if self.combo_loop.currentIndex() == 0 else "播放单次"
            bgm_vol = self.slider_bgm.value()
            self.lbl_status_tag.setText(f"已启用：{cnt}首音频 · 音量{bgm_vol}% · {loop_desc}")
            self.lbl_status_tag.setStyleSheet("""
                background-color: #ecfdf5;
                color: #059669;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            """)

    def _choose_audio_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择背景音频", "",
            "音频文件 (*.mp3 *.wav *.aac *.m4a *.flac *.ogg *.wma *.opus);;所有文件 (*.*)"
        )
        if files:
            self._add_audio_paths(files)

    def _add_audio_paths(self, paths: list[str]):
        existing = {self.audio_list.item(i).text() for i in range(self.audio_list.count())}
        for p in paths:
            if p not in existing and os.path.exists(p):
                self.audio_list.addItem(p)
                existing.add(p)
        self._update_status_tag()
        self.config_changed.emit()

    def _remove_selected_audios(self):
        for item in self.audio_list.selectedItems():
            row = self.audio_list.row(item)
            self.audio_list.takeItem(row)
        self._update_status_tag()
        self.config_changed.emit()

    def _clear_audios(self):
        self.audio_list.clear()
        self._update_status_tag()
        self.config_changed.emit()

    def get_config(self) -> BgmConfig:
        """获取当前配置对象"""
        files = [self.audio_list.item(i).text() for i in range(self.audio_list.count())]
        return BgmConfig(
            enabled=self.chk_enable.isChecked(),
            audio_files=files,
            bgm_volume=self.slider_bgm.value() / 100.0,
            orig_volume=self.slider_orig.value() / 100.0,
            loop_mode="loop" if self.combo_loop.currentIndex() == 0 else "once",
            play_order="sequence" if self.combo_order.currentIndex() == 0 else "random"
        )

    def set_config(self, cfg: BgmConfig):
        """设置配置对象并更新控件展示"""
        self.blockSignals(True)
        self.chk_enable.setChecked(cfg.enabled)
        self.audio_list.clear()
        for f in cfg.audio_files:
            if os.path.exists(f):
                self.audio_list.addItem(f)
        
        bgm_val = int(round(cfg.bgm_volume * 100))
        self.slider_bgm.setValue(bgm_val)
        self.lbl_bgm_val.setText(f"{bgm_val}%")

        orig_val = int(round(cfg.orig_volume * 100))
        self.slider_orig.setValue(orig_val)
        if orig_val == 0:
            self.lbl_orig_val.setText("静音")
        else:
            self.lbl_orig_val.setText(f"{orig_val}%")

        self.combo_loop.setCurrentIndex(0 if cfg.loop_mode == "loop" else 1)
        self.combo_order.setCurrentIndex(0 if cfg.play_order == "sequence" else 1)
        self._update_status_tag()
        self.blockSignals(False)
        self.config_changed.emit()
