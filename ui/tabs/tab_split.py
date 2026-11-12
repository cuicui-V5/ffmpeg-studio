import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QSpinBox, QGroupBox, QFileDialog, QMessageBox,
    QProgressBar
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from core.tasks.split_task import PRESETS, SplitPlan, BatchSplitWorker
from core.keyframe_helper import KeyframeHelper
from core.tasks.compress_task import EXTENSIONS
from ui.components.bgm_widget import BgmWidget

class TabSplit(QWidget):
    """视频分段"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.files: list[str] = []
        self.worker: BatchSplitWorker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. 规则预设与自定义区域
        preset_box = QGroupBox("分段规则设置")
        preset_layout = QHBoxLayout(preset_box)
        preset_layout.setSpacing(12)

        lbl_preset = QLabel("预设规则:")
        self.combo_preset = QComboBox()
        for name in PRESETS.keys():
            self.combo_preset.addItem(name)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_changed)

        lbl_size = QLabel("大小上限:")
        self.spin_size_mb = QSpinBox()
        self.spin_size_mb.setRange(1, 102400)
        self.spin_size_mb.setValue(1024)
        self.spin_size_mb.setSuffix(" MB")
        self.spin_size_mb.valueChanged.connect(self._recalculate_plans)

        lbl_dur = QLabel("时长上限:")
        self.spin_dur_sec = QSpinBox()
        self.spin_dur_sec.setRange(5, 86400)
        self.spin_dur_sec.setValue(585)
        self.spin_dur_sec.setSuffix(" 秒")
        self.spin_dur_sec.valueChanged.connect(self._recalculate_plans)

        preset_layout.addWidget(lbl_preset)
        preset_layout.addWidget(self.combo_preset)
        preset_layout.addSpacing(15)
        preset_layout.addWidget(lbl_size)
        preset_layout.addWidget(self.spin_size_mb)
        preset_layout.addSpacing(10)
        preset_layout.addWidget(lbl_dur)
        preset_layout.addWidget(self.spin_dur_sec)
        preset_layout.addStretch()

        layout.addWidget(preset_box)

        # 2. 按钮栏
        btn_bar = QHBoxLayout()
        self.btn_add_files = QPushButton("添加文件")
        self.btn_add_files.clicked.connect(self._choose_files)

        self.btn_add_folder = QPushButton("添加文件夹")
        self.btn_add_folder.clicked.connect(self._choose_folder)

        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.clicked.connect(self._clear_list)

        btn_bar.addWidget(self.btn_add_files)
        btn_bar.addWidget(self.btn_add_folder)
        btn_bar.addWidget(self.btn_clear)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # 3. 预览表格
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "文件名", "原始大小", "原始时长", "判定结果", "分段预估", "处理状态"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setCornerButtonEnabled(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, stretch=1)

        # 4. 底部操作栏与双层进度面板
        bottom_box = QGroupBox("执行操作")
        bottom_box_layout = QVBoxLayout(bottom_box)
        bottom_box_layout.setContentsMargins(12, 10, 12, 10)
        bottom_box_layout.setSpacing(8)

        # 单文件进度
        cur_layout = QVBoxLayout()
        cur_header = QHBoxLayout()
        self.lbl_cur_split = QLabel("当前文件: 等待开始")
        self.lbl_cur_split.setStyleSheet("font-weight: 600; color: #2563eb;")
        cur_header.addWidget(self.lbl_cur_split)
        cur_layout.addLayout(cur_header)

        self.prog_cur_file = QProgressBar()
        self.prog_cur_file.setValue(0)
        cur_layout.addWidget(self.prog_cur_file)
        bottom_box_layout.addLayout(cur_layout)

        # 总任务进度与按钮
        bottom_layout = QHBoxLayout()
        self.lbl_overall = QLabel("总进度: 0 / 0")
        self.lbl_overall.setStyleSheet("font-weight: bold;")

        self.prog_overall = QProgressBar()
        self.prog_overall.setValue(0)

        self.btn_start = QPushButton("开始分段")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setFixedWidth(130)
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self._start_split)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_split)

        self.btn_open_dir = QPushButton("打开输出目录")
        self.btn_open_dir.setFixedHeight(36)
        self.btn_open_dir.clicked.connect(self._open_output_dir)

        bottom_layout.addWidget(self.lbl_overall)
        bottom_layout.addWidget(self.prog_overall, stretch=1)
        bottom_layout.addWidget(self.btn_open_dir)
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_start)
        bottom_box_layout.addLayout(bottom_layout)

        self.bgm_widget = BgmWidget()
        layout.addWidget(self.bgm_widget)

        layout.addWidget(bottom_box)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        if paths:
            self._handle_dropped_paths(paths)

    def _on_preset_changed(self):
        name = self.combo_preset.currentText()
        if name in PRESETS:
            cfg = PRESETS[name]
            self.spin_size_mb.blockSignals(True)
            self.spin_dur_sec.blockSignals(True)
            self.spin_size_mb.setValue(int(cfg["max_size"] / (1024 * 1024)))
            self.spin_dur_sec.setValue(int(cfg["max_duration"]))
            self.spin_size_mb.blockSignals(False)
            self.spin_dur_sec.blockSignals(False)
            self._recalculate_plans()

    def _choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.mov *.mkv *.avi *.flv *.m4v *.ts *.webm);;所有文件 (*.*)"
        )
        if files:
            self._add_files_to_list(files)

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择视频文件夹")
        if folder:
            self._handle_dropped_paths([folder])

    def _handle_dropped_paths(self, paths: list[str]):
        found = []
        for p_str in paths:
            p = Path(p_str)
            if p.is_file() and p.suffix.lower() in EXTENSIONS:
                found.append(str(p))
            elif p.is_dir():
                for root, _, files in os.walk(p):
                    for f in files:
                        if Path(f).suffix.lower() in EXTENSIONS:
                            found.append(os.path.join(root, f))
        if found:
            self._add_files_to_list(found)

    def _add_files_to_list(self, files: list[str]):
        existing = set(self.files)
        for f in files:
            if f not in existing:
                self.files.append(f)
                existing.add(f)
        self._recalculate_plans()

    def _clear_list(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "提示", "任务执行中，无法清空。")
            return
        self.files.clear()
        self.table.setRowCount(0)
        self.lbl_overall.setText("总进度: 0 / 0")
        self.prog_overall.setValue(0)
        self.prog_cur_file.setValue(0)
        self.lbl_cur_split.setText("当前文件: 等待开始")

    def _recalculate_plans(self):
        self.table.setRowCount(len(self.files))
        max_bytes = self.spin_size_mb.value() * 1024 * 1024
        max_sec = float(self.spin_dur_sec.value())

        for row, f_str in enumerate(self.files):
            plan = SplitPlan(f_str, max_bytes, max_sec)

            self.table.setItem(row, 0, QTableWidgetItem(plan.filename))
            self.table.setItem(row, 1, QTableWidgetItem(f"{plan.size / (1024*1024):.1f} MB"))
            self.table.setItem(row, 2, QTableWidgetItem(KeyframeHelper.format_time(plan.duration, show_ms=False)))

            if not plan.needs_split:
                res_item = QTableWidgetItem("符合限制")
                res_item.setForeground(QColor("#16a34a"))
                plan_desc = "保留原样，直接无损复制"
            else:
                res_item = QTableWidgetItem(f"需拆分: {plan.part_count} 段")
                res_item.setForeground(QColor("#d97706"))
                plan_desc = f"每段限时约 {KeyframeHelper.format_time(plan.split_time, show_ms=False)}，预估单段约 {plan.avg_part_size / (1024*1024):.1f} MB"

            self.table.setItem(row, 3, res_item)
            self.table.setItem(row, 4, QTableWidgetItem(plan_desc))
            self.table.setItem(row, 5, QTableWidgetItem("待处理"))

    def _start_split(self):
        if not self.files:
            QMessageBox.warning(self, "提示", "请先添加需要分段的视频。")
            return

        max_bytes = self.spin_size_mb.value() * 1024 * 1024
        max_sec = float(self.spin_dur_sec.value())

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        bgm_config = self.bgm_widget.get_config()
        self.worker = BatchSplitWorker(self.files, max_bytes, max_sec, bgm_config=bgm_config)
        self.worker.item_updated.connect(self._on_item_updated)
        self.worker.file_progress.connect(self._on_file_progress)
        self.worker.overall_progress.connect(self._on_overall_progress)
        self.worker.all_finished.connect(self._on_all_finished)
        self.worker.start()

    def _cancel_split(self):
        if self.worker:
            self.lbl_cur_split.setText("正在取消...")
            self.worker.cancel()

    def _on_item_updated(self, idx: int, status: str, pct: float):
        if 0 <= idx < self.table.rowCount():
            self.table.setItem(idx, 5, QTableWidgetItem(status))

    def _on_file_progress(self, filename: str, pct: float, status_desc: str):
        self.lbl_cur_split.setText(f"当前处理: {filename} - {status_desc}")
        self.prog_cur_file.setValue(int(pct))

    def _on_overall_progress(self, done: int, total: int):
        self.lbl_overall.setText(f"总进度: {done} / {total}")
        if total > 0:
            self.prog_overall.setValue(int((done / total) * 100))

    def _on_all_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.prog_cur_file.setValue(100)
        self.lbl_cur_split.setText("处理完毕")
        QMessageBox.information(self, "完成", "视频分段处理完成。")

    def _open_output_dir(self):
        if self.files:
            out_dir = Path(self.files[0]).parent / "output_split"
            out_dir.mkdir(parents=True, exist_ok=True)
            if os.name == 'nt':
                os.startfile(str(out_dir))
            else:
                subprocess.run(['xdg-open', str(out_dir)])
        else:
            QMessageBox.information(self, "提示", "请先添加文件以确定默认输出目录。")
