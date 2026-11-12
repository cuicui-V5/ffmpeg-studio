import os
from pathlib import Path
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSlider, QComboBox,
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

class BgmWidget(QGroupBox):
    """通用背景音乐配置组件"""
    config_changed = Signal()

    def __init__(self, title: str = "添加背景音乐", parent=None):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # 1. 音频列表与操作按钮区
        list_box = QHBoxLayout()
        list_box.setSpacing(6)

        self.audio_list = AudioListWidget()
        self.audio_list.setFixedHeight(65)
        self.audio_list.files_dropped.connect(self._add_audio_paths)
        self.audio_list.setStyleSheet(
            "QListWidget { background-color: #1a1d22; border: 1px solid #333842; border-radius: 4px; font-size: 11px; padding: 2px; }"
        )
        list_box.addWidget(self.audio_list, stretch=1)

        btn_vbox = QVBoxLayout()
        btn_vbox.setSpacing(4)
        
        self.btn_add = QPushButton("添加音频")
        self.btn_add.setFixedHeight(24)
        self.btn_add.clicked.connect(self._choose_audio_files)

        self.btn_remove = QPushButton("移除")
        self.btn_remove.setFixedHeight(24)
        self.btn_remove.clicked.connect(self._remove_selected_audios)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setFixedHeight(24)
        self.btn_clear.clicked.connect(self._clear_audios)

        btn_vbox.addWidget(self.btn_add)
        btn_vbox.addWidget(self.btn_remove)
        btn_vbox.addWidget(self.btn_clear)
        list_box.addLayout(btn_vbox)

        main_layout.addLayout(list_box)

        # 2. 控制参数网格布局 (音量、循环、顺序)
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(4)

        # 音乐音量
        lbl_bgm_vol = QLabel("音乐音量:")
        lbl_bgm_vol.setStyleSheet("color: #abb2bf; font-size: 12px;")
        self.slider_bgm = QSlider(Qt.Horizontal)
        self.slider_bgm.setRange(0, 200)
        self.slider_bgm.setValue(100)
        self.slider_bgm.setFixedHeight(18)
        self.lbl_bgm_val = QLabel("100%")
        self.lbl_bgm_val.setFixedWidth(40)
        self.lbl_bgm_val.setStyleSheet("color: #00d2ff; font-family: Consolas; font-size: 11px;")
        self.slider_bgm.valueChanged.connect(self._on_bgm_vol_changed)

        # 循环模式
        lbl_loop = QLabel("循环模式:")
        lbl_loop.setStyleSheet("color: #abb2bf; font-size: 12px;")
        self.combo_loop = QComboBox()
        self.combo_loop.setFixedHeight(22)
        self.combo_loop.addItems(["无限循环", "播放一次"])
        self.combo_loop.currentIndexChanged.connect(lambda: self.config_changed.emit())

        # 原声音量
        lbl_orig_vol = QLabel("原声音量:")
        lbl_orig_vol.setStyleSheet("color: #abb2bf; font-size: 12px;")
        self.slider_orig = QSlider(Qt.Horizontal)
        self.slider_orig.setRange(0, 200)
        self.slider_orig.setValue(100)
        self.slider_orig.setFixedHeight(18)
        self.lbl_orig_val = QLabel("100%")
        self.lbl_orig_val.setFixedWidth(40)
        self.lbl_orig_val.setStyleSheet("color: #00d2ff; font-family: Consolas; font-size: 11px;")
        self.slider_orig.valueChanged.connect(self._on_orig_vol_changed)

        # 播放顺序
        lbl_order = QLabel("播放顺序:")
        lbl_order.setStyleSheet("color: #abb2bf; font-size: 12px;")
        self.combo_order = QComboBox()
        self.combo_order.setFixedHeight(22)
        self.combo_order.addItems(["顺序播放", "随机播放"])
        self.combo_order.currentIndexChanged.connect(lambda: self.config_changed.emit())

        # 排布网格
        # 行 0: 音乐音量 [滑块] 100% | 循环模式 [下拉]
        grid_layout.addWidget(lbl_bgm_vol, 0, 0)
        grid_layout.addWidget(self.slider_bgm, 0, 1)
        grid_layout.addWidget(self.lbl_bgm_val, 0, 2)
        grid_layout.addWidget(lbl_loop, 0, 3)
        grid_layout.addWidget(self.combo_loop, 0, 4)

        # 行 1: 原声音量 [滑块] 100% | 播放顺序 [下拉]
        grid_layout.addWidget(lbl_orig_vol, 1, 0)
        grid_layout.addWidget(self.slider_orig, 1, 1)
        grid_layout.addWidget(self.lbl_orig_val, 1, 2)
        grid_layout.addWidget(lbl_order, 1, 3)
        grid_layout.addWidget(self.combo_order, 1, 4)

        grid_layout.setColumnStretch(1, 1)
        grid_layout.setColumnStretch(4, 0)

        main_layout.addLayout(grid_layout)

        self.toggled.connect(lambda: self.config_changed.emit())

    def _on_bgm_vol_changed(self, val: int):
        self.lbl_bgm_val.setText(f"{val}%")
        self.config_changed.emit()

    def _on_orig_vol_changed(self, val: int):
        if val == 0:
            self.lbl_orig_val.setText("静音")
        else:
            self.lbl_orig_val.setText(f"{val}%")
        self.config_changed.emit()

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
        self.config_changed.emit()

    def _remove_selected_audios(self):
        for item in self.audio_list.selectedItems():
            row = self.audio_list.row(item)
            self.audio_list.takeItem(row)
        self.config_changed.emit()

    def _clear_audios(self):
        self.audio_list.clear()
        self.config_changed.emit()

    def get_config(self) -> BgmConfig:
        """获取当前配置对象"""
        files = [self.audio_list.item(i).text() for i in range(self.audio_list.count())]
        return BgmConfig(
            enabled=self.isChecked(),
            audio_files=files,
            bgm_volume=self.slider_bgm.value() / 100.0,
            orig_volume=self.slider_orig.value() / 100.0,
            loop_mode="loop" if self.combo_loop.currentIndex() == 0 else "once",
            play_order="sequence" if self.combo_order.currentIndex() == 0 else "random"
        )

    def set_config(self, cfg: BgmConfig):
        """设置配置对象并更新控件展示"""
        self.blockSignals(True)
        self.setChecked(cfg.enabled)
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
        self.blockSignals(False)
        self.config_changed.emit()
