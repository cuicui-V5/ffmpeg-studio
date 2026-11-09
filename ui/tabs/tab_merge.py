import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QFileDialog, QMessageBox, QProgressBar,
    QGroupBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from core.tasks.merge_task import (
    MergeItem, MergeWorker, validate_merge_consistency, EXTENSIONS
)
from core.keyframe_helper import KeyframeHelper

class TabMerge(QWidget):
    """选项卡：视频无损合并 (基于 FFmpeg Concat Demuxer + 自动参数一致性校验)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.items: list[MergeItem] = []
        self.worker: MergeWorker = None
        self._user_custom_output = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. 顶部操作工具栏
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.btn_add_files = QPushButton("➕ 添加视频文件")
        self.btn_add_files.clicked.connect(self._choose_files)

        self.btn_add_folder = QPushButton("📁 添加整个文件夹")
        self.btn_add_folder.clicked.connect(self._choose_folder)

        self.btn_move_up = QPushButton("⬆️ 上移")
        self.btn_move_up.setToolTip("将选中的视频在合并序列中上移")
        self.btn_move_up.clicked.connect(self._move_up)

        self.btn_move_down = QPushButton("⬇️ 下移")
        self.btn_move_down.setToolTip("将选中的视频在合并序列中下移")
        self.btn_move_down.clicked.connect(self._move_down)

        self.btn_remove = QPushButton("🗑 移除选中")
        self.btn_remove.clicked.connect(self._remove_selected)

        self.btn_clear = QPushButton("🗑 清空列表")
        self.btn_clear.clicked.connect(self._clear_list)

        top_bar.addWidget(self.btn_add_files)
        top_bar.addWidget(self.btn_add_folder)
        top_bar.addSpacing(10)
        top_bar.addWidget(self.btn_move_up)
        top_bar.addWidget(self.btn_move_down)
        top_bar.addWidget(self.btn_remove)
        top_bar.addWidget(self.btn_clear)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # 2. 参数一致性检测指示看板 (动态颜色切换)
        self.card_status = QFrame()
        self.card_status.setObjectName("cardStatus")
        card_layout = QHBoxLayout(self.card_status)
        card_layout.setContentsMargins(14, 10, 14, 10)

        self.lbl_status_icon = QLabel("💡")
        self.lbl_status_icon.setStyleSheet("font-size: 18px;")
        self.lbl_status_text = QLabel("请添加或拖入待合并的视频文件，系统将自动校验编码、分辨率、帧率及音频参数。")
        self.lbl_status_text.setStyleSheet("font-size: 13px; font-weight: 500;")
        self.lbl_status_text.setWordWrap(True)

        card_layout.addWidget(self.lbl_status_icon)
        card_layout.addSpacing(6)
        card_layout.addWidget(self.lbl_status_text, stretch=1)
        self._apply_banner_style("neutral")
        layout.addWidget(self.card_status)

        # 3. 待合并视频列表表格
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "序号", "文件名", "分辨率", "编码格式", "帧率", "音频流", "时长", "大小", "一致性状态"
        ])
        self.table.setCornerButtonEnabled(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(6, 90)
        self.table.setColumnWidth(7, 90)
        self.table.setColumnWidth(8, 120)
        layout.addWidget(self.table, stretch=1)

        # 4. 底部执行控制面板
        bottom_box = QGroupBox("执行进度与合并设置")
        bottom_layout = QVBoxLayout(bottom_box)
        bottom_layout.setContentsMargins(14, 10, 14, 10)
        bottom_layout.setSpacing(8)

        # 统计信息
        self.lbl_summary = QLabel("统计：暂无待合并文件")
        self.lbl_summary.setStyleSheet("color: #abb2bf; font-weight: bold; font-size: 12px;")
        bottom_layout.addWidget(self.lbl_summary)

        # 输出目标文件配置
        out_layout = QHBoxLayout()
        lbl_out = QLabel("输出文件:")
        lbl_out.setStyleSheet("font-weight: bold; color: #abb2bf;")
        self.edit_output = QLineEdit()
        self.edit_output.setPlaceholderText("添加视频后自动生成默认输出路径...")
        self.edit_output.textChanged.connect(self._on_output_path_edited)
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_output)
        out_layout.addWidget(lbl_out)
        out_layout.addWidget(self.edit_output, stretch=1)
        out_layout.addWidget(btn_browse)
        bottom_layout.addLayout(out_layout)

        # 进度条与状态
        prog_header = QHBoxLayout()
        self.lbl_prog_title = QLabel("合并进度: 等待开始")
        self.lbl_prog_title.setStyleSheet("font-weight: bold; color: #00d2ff;")
        self.lbl_prog_stats = QLabel("进度: 0.0%  |  速率: --  |  预计剩余: --:--")
        self.lbl_prog_stats.setStyleSheet("color: #abb2bf; font-family: Consolas, monospace; font-size: 12px;")
        prog_header.addWidget(self.lbl_prog_title)
        prog_header.addStretch()
        prog_header.addWidget(self.lbl_prog_stats)
        bottom_layout.addLayout(prog_header)

        self.prog_bar = QProgressBar()
        self.prog_bar.setValue(0)
        bottom_layout.addWidget(self.prog_bar)

        # 按钮操作栏
        action_layout = QHBoxLayout()
        self.lbl_exec_status = QLabel("准备就绪")
        self.lbl_exec_status.setStyleSheet("color: #98c379;")

        self.btn_open_dir = QPushButton("📂 打开输出目录")
        self.btn_open_dir.clicked.connect(self._open_output_dir)

        self.btn_cancel = QPushButton("⏹ 取消合并")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_merge)

        self.btn_start = QPushButton("⚡ 开始极速无损合并")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self._start_merge)

        action_layout.addWidget(self.lbl_exec_status)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_open_dir)
        action_layout.addWidget(self.btn_cancel)
        action_layout.addWidget(self.btn_start)
        bottom_layout.addLayout(action_layout)

        layout.addWidget(bottom_box)

    def _apply_banner_style(self, state: str):
        if state == "success":
            self.card_status.setStyleSheet(
                "QFrame#cardStatus { background-color: #1a2e22; border: 1px solid #98c379; border-radius: 6px; }"
            )
            self.lbl_status_icon.setText("✅")
            self.lbl_status_text.setStyleSheet("color: #98c379; font-size: 13px; font-weight: bold;")
        elif state == "warning":
            self.card_status.setStyleSheet(
                "QFrame#cardStatus { background-color: #38241e; border: 1px solid #e5c07b; border-radius: 6px; }"
            )
            self.lbl_status_icon.setText("⚠️")
            self.lbl_status_text.setStyleSheet("color: #e5c07b; font-size: 13px; font-weight: bold;")
        elif state == "error":
            self.card_status.setStyleSheet(
                "QFrame#cardStatus { background-color: #381e23; border: 1px solid #e06c75; border-radius: 6px; }"
            )
            self.lbl_status_icon.setText("❌")
            self.lbl_status_text.setStyleSheet("color: #e06c75; font-size: 13px; font-weight: bold;")
        else: # neutral
            self.card_status.setStyleSheet(
                "QFrame#cardStatus { background-color: #21252b; border: 1px solid #3e4451; border-radius: 6px; }"
            )
            self.lbl_status_icon.setText("💡")
            self.lbl_status_text.setStyleSheet("color: #abb2bf; font-size: 13px;")

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

    def _handle_dropped_paths(self, paths: list[str]):
        all_files = []
        for p in paths:
            pth = Path(p)
            if pth.is_file() and pth.suffix.lower() in EXTENSIONS:
                all_files.append(pth)
            elif pth.is_dir():
                for root, _, files in os.walk(pth):
                    for f in files:
                        fp = Path(root) / f
                        if fp.suffix.lower() in EXTENSIONS:
                            all_files.append(fp)
        if all_files:
            self._add_files_to_list(all_files)

    def _choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择待合并视频文件", "",
            "视频文件 (*.mp4 *.mov *.mkv *.avi *.flv *.m4v *.ts *.webm);;所有文件 (*.*)"
        )
        if files:
            self._add_files_to_list([Path(f) for f in files])

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择包含待合并视频的文件夹")
        if folder:
            self._handle_dropped_paths([folder])

    def _add_files_to_list(self, new_paths: list[Path]):
        existing = {item.filepath.resolve() for item in self.items}
        added_count = 0

        for p in new_paths:
            resolved = p.resolve()
            if resolved in existing:
                continue
            
            # 读取元数据
            info = KeyframeHelper.get_video_info(str(resolved))
            if not info or info.get("duration", 0) <= 0:
                continue

            item = MergeItem(
                filepath=resolved,
                filename=resolved.name,
                duration=info.get("duration", 0.0),
                size=info.get("size", 0),
                width=info.get("width", 0),
                height=info.get("height", 0),
                codec=info.get("codec", "unknown"),
                pix_fmt=info.get("pix_fmt", ""),
                fps=info.get("fps", 0.0),
                audio_codec=info.get("audio_codec", "none"),
                sample_rate=info.get("sample_rate", 0),
                channels=info.get("channels", 0)
            )
            self.items.append(item)
            existing.add(resolved)
            added_count += 1

        if added_count > 0:
            self._update_default_output_path()
            self._refresh_ui()

    def _update_default_output_path(self):
        if not self._user_custom_output and self.items:
            first_path = self.items[0].filepath
            out_dir = first_path.parent / "output_merge"
            out_file = out_dir / f"{first_path.stem}_merged{first_path.suffix}"
            self.edit_output.setText(str(out_file))

    def _on_output_path_edited(self, text: str):
        # 用户手动修改后不再自动覆盖
        if text.strip():
            self._user_custom_output = True

    def _browse_output(self):
        cur_text = self.edit_output.text().strip()
        default_dir = str(Path(cur_text).parent) if cur_text else ""
        default_name = Path(cur_text).name if cur_text else "merged_video.mp4"

        save_path, _ = QFileDialog.getSaveFileName(
            self, "选择合并视频保存位置",
            os.path.join(default_dir, default_name),
            "视频文件 (*.mp4 *.mov *.mkv *.ts);;所有文件 (*.*)"
        )
        if save_path:
            self.edit_output.setText(save_path)
            self._user_custom_output = True

    def _move_up(self):
        row = self.table.currentRow()
        if row > 0:
            self.items[row - 1], self.items[row] = self.items[row], self.items[row - 1]
            self._update_default_output_path()
            self._refresh_ui()
            self.table.selectRow(row - 1)

    def _move_down(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.items) - 1:
            self.items[row + 1], self.items[row] = self.items[row], self.items[row + 1]
            self._update_default_output_path()
            self._refresh_ui()
            self.table.selectRow(row + 1)

    def _remove_selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.items):
            del self.items[row]
            if not self.items:
                self.edit_output.clear()
                self._user_custom_output = False
            else:
                self._update_default_output_path()
            self._refresh_ui()

    def _clear_list(self):
        self.items.clear()
        self.edit_output.clear()
        self._user_custom_output = False
        self._refresh_ui()

    def _refresh_ui(self):
        # 1. 运行参数校验
        is_consistent, summary, warnings = validate_merge_consistency(self.items)

        # 2. 更新状态指示卡片
        if not self.items:
            self._apply_banner_style("neutral")
            self.lbl_status_text.setText("请添加或拖入待合并的视频文件，系统将自动校验编码、分辨率、帧率及音频参数。")
        elif len(self.items) == 1:
            self._apply_banner_style("neutral")
            self.lbl_status_text.setText("💡 当前仅添加了 1 个视频文件，请至少添加 2 个文件进行合并。")
        elif is_consistent:
            self._apply_banner_style("success")
            self.lbl_status_text.setText(summary)
        else:
            self._apply_banner_style("warning")
            self.lbl_status_text.setText(summary)

        # 3. 填充表格
        self.table.setRowCount(len(self.items))
        total_sec = 0.0
        total_bytes = 0

        for row, item in enumerate(self.items):
            total_sec += item.duration
            total_bytes += item.size

            # 序号
            item_no = QTableWidgetItem(str(row + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_no)

            # 文件名
            self.table.setItem(row, 1, QTableWidgetItem(item.filename))

            # 分辨率
            res_str = f"{item.width}x{item.height}"
            res_item = QTableWidgetItem(res_str)
            res_item.setTextAlignment(Qt.AlignCenter)
            if row > 0 and (item.width != self.items[0].width or item.height != self.items[0].height):
                res_item.setForeground(QColor("#e06c75"))
                res_item.setToolTip(f"与基准视频分辨率 ({self.items[0].width}x{self.items[0].height}) 不一致！")
            self.table.setItem(row, 2, res_item)

            # 编码格式
            codec_str = f"{item.codec} ({item.pix_fmt})" if item.pix_fmt else item.codec
            codec_item = QTableWidgetItem(codec_str)
            codec_item.setTextAlignment(Qt.AlignCenter)
            if row > 0 and item.codec != self.items[0].codec:
                codec_item.setForeground(QColor("#e06c75"))
                codec_item.setToolTip(f"与基准视频编码 ({self.items[0].codec}) 不一致！")
            self.table.setItem(row, 3, codec_item)

            # 帧率
            fps_str = f"{item.fps:.1f} fps"
            fps_item = QTableWidgetItem(fps_str)
            fps_item.setTextAlignment(Qt.AlignCenter)
            if row > 0 and abs(item.fps - self.items[0].fps) >= 0.5:
                fps_item.setForeground(QColor("#e5c07b"))
                fps_item.setToolTip(f"帧率与基准 ({self.items[0].fps:.1f} fps) 存在差异")
            self.table.setItem(row, 4, fps_item)

            # 音频流
            if item.audio_codec != "none":
                aud_str = f"{item.audio_codec} ({item.sample_rate}Hz, {item.channels}ch)"
            else:
                aud_str = "无音频流"
            aud_item = QTableWidgetItem(aud_str)
            aud_item.setTextAlignment(Qt.AlignCenter)
            if row > 0 and item.audio_codec != self.items[0].audio_codec:
                aud_item.setForeground(QColor("#e06c75"))
            self.table.setItem(row, 5, aud_item)

            # 时长
            dur_item = QTableWidgetItem(KeyframeHelper.format_time(item.duration, show_ms=False))
            dur_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 6, dur_item)

            # 大小
            size_mb = item.size / (1024 * 1024)
            size_str = f"{size_mb / 1024:.2f} GB" if size_mb >= 1024 else f"{size_mb:.1f} MB"
            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 7, size_item)

            # 一致性状态
            if row == 0:
                status_item = QTableWidgetItem("👑 基准参考")
                status_item.setForeground(QColor("#00d2ff"))
            elif item.is_consistent:
                status_item = QTableWidgetItem("✅ 参数一致")
                status_item.setForeground(QColor("#98c379"))
            else:
                status_item = QTableWidgetItem("❌ 参数差异")
                status_item.setForeground(QColor("#e06c75"))
                status_item.setToolTip("\n".join(item.mismatched_reasons))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 8, status_item)

        # 4. 统计文本
        if self.items:
            tot_dur_str = KeyframeHelper.format_time(total_sec, show_ms=False)
            tot_mb = total_bytes / (1024 * 1024)
            tot_size_str = f"{tot_mb / 1024:.2f} GB" if tot_mb >= 1024 else f"{tot_mb:.1f} MB"
            self.lbl_summary.setText(
                f"已就绪：共 {len(self.items)} 个待合并视频  |  预计合并后总时长: {tot_dur_str}  |  总文件大小: {tot_size_str}"
            )
        else:
            self.lbl_summary.setText("统计：暂无待合并文件")

    def _start_merge(self):
        if len(self.items) < 2:
            QMessageBox.warning(self, "数量不足", "请至少添加 2 个视频文件进行无损合并！")
            return

        out_str = self.edit_output.text().strip()
        if not out_str:
            QMessageBox.warning(self, "路径未指定", "请指定合并后视频的输出路径！")
            return

        out_path = Path(out_str)

        # 检查参数一致性
        is_consistent, _, warnings = validate_merge_consistency(self.items)
        if not is_consistent:
            warn_msg = "检测到以下视频与基准视频（第 1 项）参数不一致：\n\n"
            warn_msg += "\n".join(warnings[:5])
            if len(warnings) > 5:
                warn_msg += f"\n... 以及其他 {len(warnings) - 5} 项差异"
            warn_msg += "\n\n⚠️ 免重编码无损合并（-c copy）要求所有视频的分辨率和编码完全一致，强制合并极可能导致播放黑屏、花屏或画面撕裂！\n\n是否仍然强制尝试合并？"
            
            reply = QMessageBox.question(
                self, "参数不一致警告", warn_msg,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # 锁定 UI
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_add_files.setEnabled(False)
        self.btn_add_folder.setEnabled(False)
        self.btn_move_up.setEnabled(False)
        self.btn_move_down.setEnabled(False)
        self.btn_remove.setEnabled(False)
        self.btn_clear.setEnabled(False)

        self.lbl_prog_title.setText(f"正在无损合并 ({len(self.items)} 个片段)...")
        self.prog_bar.setValue(0)
        self.lbl_exec_status.setText("🚀 正在执行极速流复制...")

        total_sec = sum(item.duration for item in self.items)
        file_paths = [item.filepath for item in self.items]

        self.worker = MergeWorker(file_paths, out_path, total_sec, parent=self)
        self.worker.progress_changed.connect(self._on_worker_progress)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_progress(self, percent: float, speed: str, eta_str: str):
        self.prog_bar.setValue(int(percent))
        self.lbl_prog_stats.setText(f"进度: {percent:.1f}%  |  速率: {speed}  |  预计剩余: {eta_str}")

    def _on_worker_finished(self, success: bool, msg: str, out_path: str):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_add_files.setEnabled(True)
        self.btn_add_folder.setEnabled(True)
        self.btn_move_up.setEnabled(True)
        self.btn_move_down.setEnabled(True)
        self.btn_remove.setEnabled(True)
        self.btn_clear.setEnabled(True)

        if success:
            self.prog_bar.setValue(100)
            self.lbl_prog_title.setText("合并完成！")
            self.lbl_prog_stats.setText("进度: 100%  |  耗时: 毫秒级极速导出完成")
            self.lbl_exec_status.setText(f"✅ {msg}")
            QMessageBox.information(self, "合并成功", f"🎉 视频极速无损合并完成！\n\n输出文件已保存至：\n{out_path}")
        else:
            self.lbl_prog_title.setText("合并中止或失败")
            self.lbl_exec_status.setText(f"❌ {msg}")
            QMessageBox.critical(self, "合并失败", f"合并过程中出现问题：\n{msg}")

    def _cancel_merge(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_exec_status.setText("正在取消合并...")

    def _open_output_dir(self):
        out_str = self.edit_output.text().strip()
        out_dir = Path(out_str).parent if out_str else Path.cwd()
        if not out_dir.exists():
            out_dir.mkdir(parents=True, exist_ok=True)

        if os.name == 'nt':
            os.startfile(out_dir)
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(out_dir)])
        else:
            subprocess.run(['xdg-open', str(out_dir)])
