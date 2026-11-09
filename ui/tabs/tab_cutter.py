import os
import time
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QGroupBox, QFileDialog,
    QMessageBox, QSplitter, QFrame, QProgressBar
)
from PySide6.QtCore import Qt

from core.tasks.cutter_task import CutterWorker
from core.keyframe_helper import KeyframeHelper
from ui.components.video_player import VideoPlayerWidget

class TabCutter(QWidget):
    """视频裁剪"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.current_file = ""
        self.keyframes = []
        self.total_duration = 0.0
        self.worker: CutterWorker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. 顶部文件选择与拖拽区
        top_bar = QHBoxLayout()
        self.btn_select_file = QPushButton("选择视频")
        self.btn_select_file.clicked.connect(self._choose_video_file)
        self.lbl_file_path = QLabel("未载入视频")
        self.lbl_file_path.setStyleSheet("color: #8a919e; font-style: italic;")

        top_bar.addWidget(self.btn_select_file)
        top_bar.addWidget(self.lbl_file_path, stretch=1)
        layout.addLayout(top_bar)

        # 2. 主区域：左右分割器 (左边视频播放预览，右边裁切参数控制)
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：播放器
        player_container = QFrame()
        player_layout = QVBoxLayout(player_container)
        player_layout.setContentsMargins(0, 0, 0, 0)
        self.player_widget = VideoPlayerWidget()
        self.player_widget.mark_in_clicked.connect(self._on_player_mark_in)
        self.player_widget.mark_out_clicked.connect(self._on_player_mark_out)
        self.player_widget.range_changed.connect(self._on_player_range_changed)
        player_layout.addWidget(self.player_widget)
        splitter.addWidget(player_container)

        # 右侧：裁切参数与控制
        control_card = QFrame()
        control_card.setObjectName("cutterControlCard")
        control_card.setStyleSheet("QFrame#cutterControlCard { background-color: #1e2025; border-radius: 6px; }")
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(14, 14, 14, 14)
        control_layout.setSpacing(12)

        # 视频信息
        self.group_info = QGroupBox("视频属性")
        info_layout = QVBoxLayout(self.group_info)
        self.lbl_video_meta = QLabel("分辨率: --\n编码: --\n时长: --\n大小: --\n关键帧数量: 0")
        self.lbl_video_meta.setStyleSheet("font-family: Consolas, monospace; line-height: 1.4;")
        info_layout.addWidget(self.lbl_video_meta)
        control_layout.addWidget(self.group_info)

        # 时间截取设置
        group_time = QGroupBox("裁剪区间")
        time_layout = QVBoxLayout(group_time)
        time_layout.setSpacing(10)

        # 起始时间
        in_layout = QHBoxLayout()
        lbl_start = QLabel("起始时间:")
        lbl_start.setFixedWidth(70)
        self.edit_start = QLineEdit("00:00:00.00")
        self.edit_start.textChanged.connect(self._update_snap_preview)
        btn_set_in = QPushButton("当前时间")
        btn_set_in.clicked.connect(lambda: self._on_player_mark_in(self.player_widget.get_current_seconds()))
        in_layout.addWidget(lbl_start)
        in_layout.addWidget(self.edit_start, stretch=1)
        in_layout.addWidget(btn_set_in)
        time_layout.addLayout(in_layout)

        # 结束时间
        out_layout = QHBoxLayout()
        lbl_end = QLabel("结束时间:")
        lbl_end.setFixedWidth(70)
        self.edit_end = QLineEdit("00:00:00.00")
        self.edit_end.textChanged.connect(self._update_snap_preview)
        btn_set_out = QPushButton("当前时间")
        btn_set_out.clicked.connect(lambda: self._on_player_mark_out(self.player_widget.get_current_seconds()))
        out_layout.addWidget(lbl_end)
        out_layout.addWidget(self.edit_end, stretch=1)
        out_layout.addWidget(btn_set_out)
        time_layout.addLayout(out_layout)

        # 关键帧对齐状态指示
        self.lbl_snap_result = QLabel("关键帧自动对齐已就绪")
        self.lbl_snap_result.setStyleSheet("color: #00d2ff; font-weight: bold; font-family: Consolas; font-size: 12px;")
        time_layout.addWidget(self.lbl_snap_result)

        control_layout.addWidget(group_time)
        control_layout.addStretch()

        # 导出操作与独立单文件进度
        action_box = QGroupBox("执行操作")
        action_layout = QVBoxLayout(action_box)
        action_layout.setSpacing(8)

        self.lbl_cut_status = QLabel("就绪")
        self.lbl_cut_status.setStyleSheet("color: #abb2bf; font-size: 12px;")

        self.prog_cut = QProgressBar()
        self.prog_cut.setValue(0)
        self.prog_cut.setFixedHeight(18)

        self.btn_cut = QPushButton("开始裁剪")
        self.btn_cut.setObjectName("primaryBtn")
        self.btn_cut.setFixedHeight(40)
        self.btn_cut.clicked.connect(self._start_cut)

        self.btn_open_folder = QPushButton("打开输出目录")
        self.btn_open_folder.setFixedHeight(34)
        self.btn_open_folder.clicked.connect(self._open_output_dir)

        action_layout.addWidget(self.lbl_cut_status)
        action_layout.addWidget(self.prog_cut)
        action_layout.addWidget(self.btn_cut)
        action_layout.addWidget(self.btn_open_folder)
        control_layout.addWidget(action_box)

        splitter.addWidget(control_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        if paths:
            self.load_video(paths[0])

    def _choose_video_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择要裁切的视频文件", "",
            "视频文件 (*.mp4 *.mov *.mkv *.avi *.flv *.m4v *.ts *.webm);;所有文件 (*.*)"
        )
        if file_path:
            self.load_video(file_path)

    def load_video(self, file_path: str):
        if not os.path.exists(file_path):
            return

        self.current_file = file_path
        self.lbl_file_path.setText(file_path)
        self.lbl_file_path.setStyleSheet("color: #00d2ff; font-weight: bold;")

        # 1. 毫秒级提取基础视频媒体属性
        meta = KeyframeHelper.get_video_info(file_path)
        self.total_duration = meta.get("duration", 0.0)
        dur_str = KeyframeHelper.format_time(self.total_duration, show_ms=False)
        size_mb = meta.get("size", 0) / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB" if size_mb < 1024 else f"{size_mb/1024:.2f} GB"

        fps_val = meta.get("fps", 0.0)
        self.lbl_video_meta.setText(
            f"分辨率: {meta.get('width', 0)}x{meta.get('height', 0)}\n"
            f"编码格式: {meta.get('codec', 'unknown')} ({fps_val:.1f} fps)\n"
            f"视频时长: {dur_str} ({self.total_duration:.2f} 秒)\n"
            f"文件大小: {size_str}\n"
            f"关键帧对齐: 已就绪"
        )

        # 2. 初始化时间输入框 (阻塞信号，避免重复触发计算)
        self.edit_start.blockSignals(True)
        self.edit_end.blockSignals(True)
        self.edit_start.setText("00:00:00.00")
        self.edit_end.setText(KeyframeHelper.format_time(self.total_duration, show_ms=True))
        self.edit_start.blockSignals(False)
        self.edit_end.blockSignals(False)

        eff_dur = self.total_duration
        self.lbl_snap_result.setText(f"预估区间: 0.00s -> {self.total_duration:.2f}s ({eff_dur:.2f}s)")

        # 3. 后台异步载入视频流与首帧 (附带呼吸加载指示动画，零阻塞)
        self.player_widget.load_video_async(file_path, on_loaded=self._on_video_loaded)

    def _on_video_loaded(self):
        self._update_snap_preview()

    def _on_player_mark_in(self, seconds: float):
        self.edit_start.setText(KeyframeHelper.format_time(seconds, show_ms=True))
        end_s = KeyframeHelper.parse_time(self.edit_end.text()) or self.total_duration
        self.player_widget.set_range_values(seconds, end_s)

    def _on_player_mark_out(self, seconds: float):
        self.edit_end.setText(KeyframeHelper.format_time(seconds, show_ms=True))
        start_s = KeyframeHelper.parse_time(self.edit_start.text()) or 0.0
        self.player_widget.set_range_values(start_s, seconds)

    def _on_player_range_changed(self, in_sec: float, out_sec: float):
        self.edit_start.blockSignals(True)
        self.edit_end.blockSignals(True)
        self.edit_start.setText(KeyframeHelper.format_time(in_sec, show_ms=True))
        self.edit_end.setText(KeyframeHelper.format_time(out_sec, show_ms=True))
        self.edit_start.blockSignals(False)
        self.edit_end.blockSignals(False)
        self._update_snap_preview()

    def _update_snap_preview(self):
        s_text = self.edit_start.text().strip()
        e_text = self.edit_end.text().strip()

        s_val = KeyframeHelper.parse_time(s_text)
        e_val = KeyframeHelper.parse_time(e_text)

        if s_val is None or e_val is None:
            self.lbl_snap_result.setText("时间格式不正确")
            return

        if s_val >= e_val:
            self.lbl_snap_result.setText("起始时间必须小于结束时间")
            return

        container = getattr(self.player_widget, "container", None)
        stream = getattr(self.player_widget, "video_stream", None)

        if container and stream:
            try:
                s_snap, s_diff = KeyframeHelper.find_keyframe_instant(
                    container, stream, s_val, mode="floor", duration=self.total_duration
                )
                e_snap, e_diff = KeyframeHelper.find_keyframe_instant(
                    container, stream, e_val, mode="ceil", duration=self.total_duration
                )
                eff_dur = max(0.0, e_snap - s_snap)
                self.lbl_snap_result.setText(
                    f"起点吸附: {KeyframeHelper.format_time(s_snap)} ({s_diff:+.2f}s)\n"
                    f"终点吸附: {KeyframeHelper.format_time(e_snap)} ({e_diff:+.2f}s)\n"
                    f"裁剪后时长: {KeyframeHelper.format_time(eff_dur, show_ms=False)}"
                )
                return
            except Exception:
                pass

        eff_dur = max(0.0, e_val - s_val)
        self.lbl_snap_result.setText(f"预估区间: {s_val:.2f}s -> {e_val:.2f}s ({eff_dur:.2f}s)")

    def _start_cut(self):
        if not self.current_file or not os.path.exists(self.current_file):
            QMessageBox.warning(self, "未选择文件", "请先打开需要裁切的视频文件。")
            return

        s_val = KeyframeHelper.parse_time(self.edit_start.text())
        e_val = KeyframeHelper.parse_time(self.edit_end.text())

        if s_val is None or e_val is None or s_val >= e_val:
            QMessageBox.warning(self, "时间错误", "裁切起始时间必须小于结束时间，请检查输入格式。")
            return

        out_dir = Path(self.current_file).parent / "output_cut"
        
        self.btn_cut.setEnabled(False)
        self.btn_cut.setText("正在裁剪...")
        self.prog_cut.setValue(30)
        self.lbl_cut_status.setText("正在执行流复制裁剪...")
        self.start_time_cut = time.time()

        self.worker = CutterWorker(
            file_path=self.current_file,
            start_sec=s_val,
            end_sec=e_val,
            auto_snap=True,
            output_dir=str(out_dir)
        )
        self.worker.finished.connect(self._on_cut_finished)
        self.worker.start()

    def _on_cut_finished(self, success: bool, msg: str, out_path: str):
        self.btn_cut.setEnabled(True)
        self.btn_cut.setText("开始裁剪")
        elapsed = time.time() - getattr(self, "start_time_cut", time.time())

        if success:
            self.prog_cut.setValue(100)
            self.lbl_cut_status.setText(f"裁剪成功，耗时 {elapsed:.2f}s")
            QMessageBox.information(
                self, "完成",
                f"视频裁剪完成，耗时 {elapsed:.2f}s。\n\n输出文件已保存至:\n{out_path}"
            )
        else:
            self.prog_cut.setValue(0)
            self.lbl_cut_status.setText("裁剪发生错误")
            QMessageBox.critical(self, "裁切失败", f"FFmpeg 执行失败:\n{msg}")

    def _open_output_dir(self):
        if self.current_file:
            out_dir = Path(self.current_file).parent / "output_cut"
        else:
            out_dir = Path.cwd() / "output_cut"
        out_dir.mkdir(parents=True, exist_ok=True)

        if os.name == 'nt':
            os.startfile(out_dir)
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(out_dir)])
        else:
            subprocess.run(['xdg-open', str(out_dir)])
