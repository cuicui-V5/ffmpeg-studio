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
from ui.components.drop_area import DropArea

class TabSplit(QWidget):
    """选项卡 3：平台限制智能分段 (QQ / 微信 / 社交媒体 / 自定义阈值)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.files: list[str] = []
        self.worker: BatchSplitWorker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. 规则预设与自定义区域
        preset_box = QGroupBox("平台限制规则与阈值设置")
        preset_layout = QHBoxLayout(preset_box)
        preset_layout.setSpacing(12)

        lbl_preset = QLabel("平台预设:")
        self.combo_preset = QComboBox()
        for name in PRESETS.keys():
            self.combo_preset.addItem(name)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_changed)

        lbl_size = QLabel("单文件上限 (MB):")
        self.spin_size_mb = QSpinBox()
        self.spin_size_mb.setRange(1, 102400) # 1MB - 100GB
        self.spin_size_mb.setValue(1024)
        self.spin_size_mb.valueChanged.connect(self._recalculate_plans)

        lbl_dur = QLabel("单文件上限 (秒):")
        self.spin_dur_sec = QSpinBox()
        self.spin_dur_sec.setRange(5, 86400)
        self.spin_dur_sec.setValue(585)
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
        self.btn_add_files = QPushButton("➕ 添加视频文件")
        self.btn_add_files.clicked.connect(self._choose_files)

        self.btn_add_folder = QPushButton("📁 添加整个文件夹")
        self.btn_add_folder.clicked.connect(self._choose_folder)

        self.btn_clear = QPushButton("🗑 清空列表")
        self.btn_clear.clicked.connect(self._clear_list)

        btn_bar.addWidget(self.btn_add_files)
        btn_bar.addWidget(self.btn_add_folder)
        btn_bar.addWidget(self.btn_clear)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # 3. 拖拽区域
        self.drop_area = DropArea(
            title="拖入需要分段的视频或文件夹",
            subtitle="自动按设定规则计算最优切片时间与预计段数（采用 FFmpeg 极速流复制无损分割）"
        )
        self.drop_area.files_dropped.connect(self._handle_dropped_paths)
        layout.addWidget(self.drop_area)

        # 4. 预览表格
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "文件名", "原始大小", "原始时长", "判定结果", "切片方案预估", "处理状态"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.table, stretch=1)

        # 5. 底部操作栏
        bottom_layout = QHBoxLayout()
        self.prog_overall = QProgressBar()
        self.prog_overall.setValue(0)
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #00d2ff;")

        self.btn_start = QPushButton("⚡ 开始智能分段")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setFixedWidth(140)
        self.btn_start.clicked.connect(self._start_split)

        self.btn_cancel = QPushButton("⏹ 取消")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_split)

        self.btn_open_dir = QPushButton("📂 打开输出目录")
        self.btn_open_dir.clicked.connect(self._open_output_dir)

        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addWidget(self.prog_overall, stretch=1)
        bottom_layout.addWidget(self.btn_open_dir)
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_start)

        layout.addLayout(bottom_layout)

    def _on_preset_changed(self):
        name = self.combo_preset.currentText()
        if name in PRESETS:
            cfg = PRESETS[name]
            # 临时阻断信号避免重复重算
            self.spin_size_mb.blockSignals(True)
            self.spin_dur_sec.blockSignals(True)
            self.spin_size_mb.setValue(int(cfg["max_size"] / (1024 * 1024)))
            self.spin_dur_sec.setValue(int(cfg["max_duration"]))
            self.spin_size_mb.blockSignals(False)
            self.spin_dur_sec.blockSignals(False)
            self._recalculate_plans()

    def _choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.mov *.mkv *.avi *.flv *.ts *.webm);;所有文件 (*.*)"
        )
        if files:
            self._add_files(files)

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择视频文件夹")
        if folder:
            self._handle_dropped_paths([folder])

    def _handle_dropped_paths(self, paths: list[str]):
        found_files = []
        for p_str in paths:
            p = Path(p_str)
            if p.is_file() and p.suffix.lower() in EXTENSIONS:
                found_files.append(str(p))
            elif p.is_dir():
                for root, _, files in os.walk(p):
                    for f in files:
                        if Path(f).suffix.lower() in EXTENSIONS:
                            found_files.append(os.path.join(root, f))
        if found_files:
            self._add_files(found_files)

    def _add_files(self, new_files: list[str]):
        cur_set = set(self.files)
        for f in new_files:
            if f not in cur_set:
                self.files.append(f)
                cur_set.add(f)
        self._recalculate_plans()

    def _clear_list(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "提示", "任务执行中，无法清空！")
            return
        self.files.clear()
        self.table.setRowCount(0)
        self.prog_overall.setValue(0)
        self.lbl_status.setText("就绪")

    def _recalculate_plans(self):
        max_bytes = self.spin_size_mb.value() * 1024 * 1024
        max_sec = float(self.spin_dur_sec.value())

        self.table.setRowCount(len(self.files))

        for row, f_str in enumerate(self.files):
            plan = SplitPlan(f_str, max_bytes, max_sec)

            # 0. 文件名
            self.table.setItem(row, 0, QTableWidgetItem(plan.filename))
            # 1. 原始大小
            self.table.setItem(row, 1, QTableWidgetItem(f"{plan.size / (1024*1024):.1f} MB"))
            # 2. 原始时长
            self.table.setItem(row, 2, QTableWidgetItem(KeyframeHelper.format_time(plan.duration, show_ms=False)))

            # 3. 判定结果
            if not plan.needs_split:
                res_item = QTableWidgetItem("✅ 符合限制 (无需拆分)")
                res_item.setForeground(QColor("#98c379"))
                plan_desc = "保留原样，直接无损复制"
            else:
                res_item = QTableWidgetItem(f"✂ 需拆分 ({plan.part_count} 段)")
                res_item.setForeground(QColor("#e5c07b"))
                plan_desc = f"每段限时约 {KeyframeHelper.format_time(plan.split_time, show_ms=False)}，预估单段约 {plan.avg_part_size / (1024*1024):.1f} MB"

            self.table.setItem(row, 3, res_item)
            # 4. 方案预估
            self.table.setItem(row, 4, QTableWidgetItem(plan_desc))
            # 5. 处理状态
            self.table.setItem(row, 5, QTableWidgetItem("待处理"))

    def _start_split(self):
        if not self.files:
            QMessageBox.warning(self, "提示", "请先添加需要分段的视频！")
            return

        max_bytes = self.spin_size_mb.value() * 1024 * 1024
        max_sec = float(self.spin_dur_sec.value())

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.lbl_status.setText("正在执行智能切片与处理...")

        self.worker = BatchSplitWorker(self.files, max_bytes, max_sec)
        self.worker.item_updated.connect(self._on_item_updated)
        self.worker.overall_progress.connect(self._on_overall_progress)
        self.worker.all_finished.connect(self._on_all_finished)
        self.worker.start()

    def _cancel_split(self):
        if self.worker:
            self.lbl_status.setText("正在取消...")
            self.worker.cancel()

    def _on_item_updated(self, idx: int, status: str, pct: float):
        if 0 <= idx < self.table.rowCount():
            self.table.setItem(idx, 5, QTableWidgetItem(status))

    def _on_overall_progress(self, done: int, total: int):
        if total > 0:
            self.prog_overall.setValue(int((done / total) * 100))
            self.lbl_status.setText(f"处理进度: {done} / {total}")

    def _on_all_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText("🎉 分段任务处理完毕！")
        QMessageBox.information(self, "完成", "所选视频的分段与复制操作已全部完成！")

    def _open_output_dir(self):
        if self.files:
            out_dir = Path(self.files[0]).parent / "output_split"
            out_dir.mkdir(parents=True, exist_ok=True)
            if os.name == 'nt':
                os.startfile(str(out_dir))
            else:
                subprocess.run(['xdg-open', str(out_dir)])
        else:
            QMessageBox.information(self, "提示", "请先添加文件以确定默认同级输出目录。")
