import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QInputDialog, QMessageBox, QProgressBar,
    QComboBox, QGroupBox, QMenu
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor

from core.tasks.compress_task import (
    CompressItem, BatchCompressWorker, EXTENSIONS, parse_gps_input
)
from core.hardware import HardwareDetector
from core.keyframe_helper import KeyframeHelper
from ui.components.bgm_widget import BgmWidget

class TabCompress(QWidget):
    """批量压制"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.items: list[CompressItem] = []
        self.worker: BatchCompressWorker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. 顶部控制栏
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.btn_add_files = QPushButton("添加文件")
        self.btn_add_files.clicked.connect(self._choose_files)

        self.btn_add_folder = QPushButton("添加文件夹")
        self.btn_add_folder.clicked.connect(self._choose_folder)

        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.clicked.connect(self._clear_list)

        top_bar.addWidget(self.btn_add_files)
        top_bar.addWidget(self.btn_add_folder)
        top_bar.addWidget(self.btn_clear)
        top_bar.addStretch()

        # 编码设置
        lbl_enc = QLabel("编码器:")
        self.combo_encoder = QComboBox()
        self._populate_encoders()

        lbl_cq = QLabel("画质预设:")
        self.combo_quality = QComboBox()
        self.combo_quality.addItem("高画质", 23)
        self.combo_quality.addItem("标准画质", 28)
        self.combo_quality.addItem("小体积", 32)
        self.combo_quality.setCurrentIndex(1)

        top_bar.addWidget(lbl_enc)
        top_bar.addWidget(self.combo_encoder)
        top_bar.addSpacing(10)
        top_bar.addWidget(lbl_cq)
        top_bar.addWidget(self.combo_quality)

        layout.addLayout(top_bar)

        # 2. 批量元数据快捷操作按钮栏
        meta_bar = QHBoxLayout()
        meta_bar.setSpacing(8)

        self.btn_batch_gps = QPushButton("批量填充GPS")
        self.btn_batch_gps.clicked.connect(self._batch_fill_gps)

        self.btn_batch_date = QPushButton("批量填充日期")
        self.btn_batch_date.clicked.connect(self._batch_fill_date)

        lbl_tips = QLabel("双击表格单元格可修改日期或GPS坐标")
        lbl_tips.setStyleSheet("color: #64748b; font-size: 12px;")

        meta_bar.addWidget(self.btn_batch_gps)
        meta_bar.addWidget(self.btn_batch_date)
        meta_bar.addStretch()
        meta_bar.addWidget(lbl_tips)
        layout.addLayout(meta_bar)

        # 3. 表格视图
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "文件名", "原始分辨率", "时长", "大小", "拍摄日期", "GPS 坐标", "当前状态", "压制进度"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setCornerButtonEnabled(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.table, stretch=1)

        # 4. 底部执行面板
        bottom_box = QGroupBox("执行操作")
        bottom_layout = QVBoxLayout(bottom_box)
        bottom_layout.setContentsMargins(12, 10, 12, 10)
        bottom_layout.setSpacing(8)

        # 单文件处理进度
        cur_layout = QVBoxLayout()
        cur_header = QHBoxLayout()
        self.lbl_cur_title = QLabel("当前文件: 等待开始")
        self.lbl_cur_title.setStyleSheet("font-weight: 600; color: #2563eb;")
        self.lbl_cur_stats = QLabel("进度: 0.0%  |  速率: --  |  帧率: -- fps  |  预计剩余: --:--")
        self.lbl_cur_stats.setStyleSheet("color: #64748b; font-family: Consolas, monospace; font-size: 12px;")
        cur_header.addWidget(self.lbl_cur_title)
        cur_header.addStretch()
        cur_header.addWidget(self.lbl_cur_stats)
        cur_layout.addLayout(cur_header)

        self.prog_current = QProgressBar()
        self.prog_current.setValue(0)
        cur_layout.addWidget(self.prog_current)
        bottom_layout.addLayout(cur_layout)

        # 总任务进度
        prog_layout = QHBoxLayout()
        self.lbl_overall = QLabel("总进度: 0 / 0")
        self.lbl_overall.setStyleSheet("font-weight: 600; color: #0f172a;")
        self.prog_overall = QProgressBar()
        self.prog_overall.setValue(0)
        prog_layout.addWidget(self.lbl_overall)
        prog_layout.addWidget(self.prog_overall, stretch=1)
        bottom_layout.addLayout(prog_layout)

        action_layout = QHBoxLayout()
        self.lbl_status_desc = QLabel("准备就绪")
        self.lbl_status_desc.setStyleSheet("color: #2563eb; font-weight: 500;")

        self.btn_start = QPushButton("开始压制")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setFixedWidth(130)
        self.btn_start.clicked.connect(self._start_compress)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_compress)

        self.btn_open_dir = QPushButton("打开输出目录")
        self.btn_open_dir.clicked.connect(self._open_output_dir)

        action_layout.addWidget(self.lbl_status_desc)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_open_dir)
        action_layout.addWidget(self.btn_cancel)
        action_layout.addWidget(self.btn_start)
        bottom_layout.addLayout(action_layout)

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

    def _populate_encoders(self):
        support = HardwareDetector.detect_encoders()
        best = HardwareDetector.get_best_hevc_encoder()
        
        encoder_options = [
            ("自动选择", "auto"),
            ("NVIDIA NVENC H.265", "hevc_nvenc"),
            ("NVIDIA NVENC H.264", "h264_nvenc"),
            ("Intel QuickSync H.265", "hevc_qsv"),
            ("CPU 软编 H.265", "libx265"),
            ("CPU 软编 H.264", "libx264")
        ]

        for text, key in encoder_options:
            if key == "auto":
                self.combo_encoder.addItem(f"{text}: {best}", key)
            else:
                is_sup = support.get(key, {}).get("supported", False)
                status_suffix = " 可用" if is_sup else " 不可用"
                self.combo_encoder.addItem(text + status_suffix, key)

    def _choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.mov *.mkv *.avi *.flv *.m4v *.ts *.webm);;所有文件 (*.*)"
        )
        if files:
            self._add_files_to_queue(files)

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
            self._add_files_to_queue(found_files)

    def _add_files_to_queue(self, files: list[str]):
        new_items = []
        existing_paths = {str(item.filepath) for item in self.items}
        for f in files:
            if f not in existing_paths:
                item = CompressItem(f)
                item.probe_media_info()
                item.probe_metadata()
                self.items.append(item)
                new_items.append(item)
                existing_paths.add(f)

        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            self.table.setItem(row, 0, QTableWidgetItem(item.filename))
            self.table.setItem(row, 1, QTableWidgetItem(item.resolution))
            
            dur_str = KeyframeHelper.format_time(item.duration, show_ms=False)
            self.table.setItem(row, 2, QTableWidgetItem(dur_str))
            
            size_mb = f"{item.filesize / (1024*1024):.1f} MB"
            self.table.setItem(row, 3, QTableWidgetItem(size_mb))
            
            # 拍摄日期
            date_item = QTableWidgetItem(item.final_date or "缺失")
            if item.date_source == 'exif':
                date_item.setForeground(QColor("#16a34a"))
            elif item.date_source == 'filename':
                date_item.setForeground(QColor("#d97706"))
            elif item.date_source == 'user':
                date_item.setForeground(QColor("#2563eb"))
            else:
                date_item.setForeground(QColor("#dc2626"))
            self.table.setItem(row, 4, date_item)

            # GPS
            gps_str = f"{item.final_lat:.4f}, {item.final_lon:.4f}" if (item.final_lat is not None and item.final_lon is not None) else "缺失"
            gps_item = QTableWidgetItem(gps_str)
            if item.gps_source in ['exif', 'user_copy']:
                gps_item.setForeground(QColor("#16a34a"))
            elif item.gps_source == 'user':
                gps_item.setForeground(QColor("#2563eb"))
            else:
                gps_item.setForeground(QColor("#dc2626"))
            self.table.setItem(row, 5, gps_item)

            self.table.setItem(row, 6, QTableWidgetItem(item.status))
            self.table.setItem(row, 7, QTableWidgetItem(f"{item.progress:.1f}%"))

        self.lbl_overall.setText(f"总进度: 0 / {len(self.items)}")

    def _clear_list(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "提示", "任务正在执行中，无法清空列表。")
            return
        self.items.clear()
        self.table.setRowCount(0)
        self.lbl_overall.setText("总进度: 0 / 0")
        self.prog_overall.setValue(0)
        self.prog_current.setValue(0)
        self.lbl_cur_title.setText("当前文件: 等待开始")
        self.lbl_cur_stats.setText("进度: 0.0%  |  速率: --  |  帧率: -- fps  |  预计剩余: --:--")

    def _batch_fill_gps(self):
        text, ok = QInputDialog.getText(
            self, "批量设置 GPS 坐标",
            "请输入经纬度 (例如: 39.9042, 116.4074)\n或粘贴地图坐标链接:"
        )
        if ok and text.strip():
            lat, lon = parse_gps_input(text.strip())
            if lat is None or lon is None:
                QMessageBox.warning(self, "解析失败", "无法解析有效的经纬度坐标，请检查格式。")
                return

            selected_rows = [i.row() for i in self.table.selectionModel().selectedRows()]
            target_items = [self.items[r] for r in selected_rows] if selected_rows else [it for it in self.items if it.final_lat is None]
            
            for it in target_items:
                it.final_lat = lat
                it.final_lon = lon
                it.gps_source = 'user'

            self._refresh_table()
            QMessageBox.information(self, "完成", f"已更新 {len(target_items)} 个视频的 GPS 坐标。")

    def _batch_fill_date(self):
        text, ok = QInputDialog.getText(
            self, "批量设置拍摄日期",
            "请输入拍摄日期与时间 (格式: 2026:08:04 12:00:00):"
        )
        if ok and text.strip():
            selected_rows = [i.row() for i in self.table.selectionModel().selectedRows()]
            target_items = [self.items[r] for r in selected_rows] if selected_rows else [it for it in self.items if not it.final_date]

            for it in target_items:
                it.final_date = text.strip()
                it.date_source = 'user'

            self._refresh_table()
            QMessageBox.information(self, "完成", f"已更新 {len(target_items)} 个视频的拍摄日期。")

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        col = item.column()
        target = self.items[row]

        if col == 4:
            text, ok = QInputDialog.getText(
                self, "编辑日期", f"编辑 {target.filename} 的拍摄日期:", text=target.final_date or ""
            )
            if ok and text.strip():
                target.final_date = text.strip()
                target.date_source = 'user'
                self._refresh_table()
        elif col == 5:
            cur = f"{target.final_lat}, {target.final_lon}" if target.final_lat else ""
            text, ok = QInputDialog.getText(
                self, "编辑 GPS", f"编辑 {target.filename} 的 GPS 坐标:", text=cur
            )
            if ok and text.strip():
                lat, lon = parse_gps_input(text.strip())
                if lat and lon:
                    target.final_lat = lat
                    target.final_lon = lon
                    target.gps_source = 'user'
                    self._refresh_table()

    def _show_context_menu(self, pos: QPoint):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()

        menu = QMenu(self)
        act_edit_date = menu.addAction("编辑拍摄日期")
        act_edit_gps = menu.addAction("编辑 GPS 坐标")
        menu.addSeparator()
        act_remove = menu.addAction("从列表移除")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == act_edit_date:
            self._on_item_double_clicked(self.table.item(row, 4))
        elif action == act_edit_gps:
            self._on_item_double_clicked(self.table.item(row, 5))
        elif action == act_remove:
            self.items.pop(row)
            self._refresh_table()

    def _start_compress(self):
        if not self.items:
            QMessageBox.warning(self, "提示", "请先添加要压制的视频文件。")
            return

        encoder_key = self.combo_encoder.currentData()
        cq_val = self.combo_quality.currentData()

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.lbl_status_desc.setText("正在执行批量压制任务...")

        bgm_config = self.bgm_widget.get_config()
        self.worker = BatchCompressWorker(self.items, encoder=encoder_key, cq=cq_val, bgm_config=bgm_config)
        self.worker.item_updated.connect(self._on_item_updated)
        self.worker.file_progress.connect(self._on_file_progress)
        self.worker.overall_progress.connect(self._on_overall_progress)
        self.worker.all_finished.connect(self._on_all_finished)
        self.worker.start()

    def _cancel_compress(self):
        if self.worker:
            self.lbl_status_desc.setText("正在中止当前任务...")
            self.worker.cancel()

    def _on_file_progress(self, filename: str, pct: float, fps: float, speed: str, eta_str: str):
        self.lbl_cur_title.setText(f"当前处理: {filename}")
        self.prog_current.setValue(int(pct))
        self.lbl_cur_stats.setText(f"进度: {pct:.1f}%  |  速率: {speed}  |  帧率: {fps:.0f} fps  |  预计剩余: {eta_str}")

    def _on_item_updated(self, idx: int, status: str, pct: float):
        if 0 <= idx < self.table.rowCount():
            self.table.setItem(idx, 6, QTableWidgetItem(status))
            self.table.setItem(idx, 7, QTableWidgetItem(f"{pct:.1f}%"))

    def _on_overall_progress(self, done: int, total: int):
        self.lbl_overall.setText(f"总进度: {done} / {total}")
        if total > 0:
            self.prog_overall.setValue(int((done / total) * 100))

    def _on_all_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_status_desc.setText("任务处理完成")
        self.prog_current.setValue(100)
        self.lbl_cur_title.setText("当前文件: 全部处理完毕")
        QMessageBox.information(self, "完成", "批量压制处理完成。")

    def _open_output_dir(self):
        if self.items:
            out_dir = self.items[0].output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            if os.name == 'nt':
                os.startfile(str(out_dir))
            else:
                subprocess.run(['xdg-open', str(out_dir)])
        else:
            QMessageBox.information(self, "提示", "请先添加文件以确定默认输出目录。")
