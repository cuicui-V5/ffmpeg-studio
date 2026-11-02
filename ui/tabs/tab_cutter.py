import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QCheckBox, QGroupBox, QFileDialog,
    QMessageBox, QSplitter, QFrame
)
from PySide6.QtCore import Qt

from core.tasks.cutter_task import CutterWorker
from core.keyframe_helper import KeyframeHelper
from ui.components.video_player import VideoPlayerWidget
from ui.components.drop_area import DropArea

class TabCutter(QWidget):
    """选项卡 2：极速视频裁切 + 内嵌播放预览 + 关键帧智能吸附（杜绝黑屏）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = ""
        self.keyframes = []
        self.total_duration = 0.0
        self.worker: CutterWorker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. 顶部文件选择与拖拽区
        top_bar = QHBoxLayout()
        self.btn_select_file = QPushButton("📂 打开要裁切的视频")
        self.btn_select_file.clicked.connect(self._choose_video_file)
        self.lbl_file_path = QLabel("未载入视频 (请选择或拖入文件)")
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
        player_layout.addWidget(self.player_widget)
        splitter.addWidget(player_container)

        # 右侧：裁切参数与关键帧指示器
        control_card = QFrame()
        control_card.setStyleSheet("background-color: #1e2025; border-radius: 6px; padding: 10px;")
        control_layout = QVBoxLayout(control_card)
        control_layout.setSpacing(12)

        # 视频信息
        self.group_info = QGroupBox("视频属性")
        info_layout = QVBoxLayout(self.group_info)
        self.lbl_video_meta = QLabel("分辨率: --\n编码: --\n时长: --\n大小: --\n关键帧数量: 0")
        self.lbl_video_meta.setStyleSheet("font-family: Consolas, monospace; line-height: 1.4;")
        info_layout.addWidget(self.lbl_video_meta)
        control_layout.addWidget(self.group_info)

        # 时间截取设置
        group_time = QGroupBox("裁切区间设置")
        time_layout = QVBoxLayout(group_time)
        time_layout.setSpacing(10)

        # 起始时间
        in_layout = QHBoxLayout()
        lbl_start = QLabel("起始时间:")
        lbl_start.setFixedWidth(70)
        self.edit_start = QLineEdit("00:00:00.00")
        self.edit_start.textChanged.connect(self._update_snap_preview)
        btn_set_in = QPushButton("⏱ 取当前点")
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
        btn_set_out = QPushButton("⏱ 取当前点")
        btn_set_out.clicked.connect(lambda: self._on_player_mark_out(self.player_widget.get_current_seconds()))
        out_layout.addWidget(lbl_end)
        out_layout.addWidget(self.edit_end, stretch=1)
        out_layout.addWidget(btn_set_out)
        time_layout.addLayout(out_layout)

        control_layout.addWidget(group_time)

        # 关键帧智能吸附卡片
        group_snap = QGroupBox("智能关键帧对齐 (杜绝黑屏)")
        snap_layout = QVBoxLayout(group_snap)
        snap_layout.setSpacing(6)

        self.chk_auto_snap = QCheckBox("启用关键帧自动吸附 (强烈推荐)")
        self.chk_auto_snap.setChecked(True)
        self.chk_auto_snap.stateChanged.connect(self._update_snap_preview)

        self.lbl_snap_desc = QLabel(
            "💡 原理：FFmpeg 极速裁切（流复制模式）必须从关键帧（I帧）开始解码，否则会产生黑屏/花屏。"
            "开启吸附将自动把时间对齐到临近关键帧，保证秒级导出且画面第一帧完美流畅！"
        )
        self.lbl_snap_desc.setWordWrap(True)
        self.lbl_snap_desc.setStyleSheet("color: #8a919e; font-size: 11px;")

        self.lbl_snap_result = QLabel("吸附状态: 等待输入时间...")
        self.lbl_snap_result.setStyleSheet("color: #00d2ff; font-weight: bold; font-family: Consolas;")

        snap_layout.addWidget(self.chk_auto_snap)
        snap_layout.addWidget(self.lbl_snap_desc)
        snap_layout.addWidget(self.lbl_snap_result)
        control_layout.addWidget(group_snap)

        control_layout.addStretch()

        # 导出操作
        action_layout = QVBoxLayout()
        self.btn_cut = QPushButton("⚡ 极速无损裁切 (毫秒级导出)")
        self.btn_cut.setObjectName("primaryBtn")
        self.btn_cut.setFixedHeight(42)
        self.btn_cut.clicked.connect(self._start_cut)

        btn_open_folder = QPushButton("📂 打开输出目录 (默认同级 output_cut)")
        btn_open_folder.clicked.connect(self._open_output_dir)

        action_layout.addWidget(self.btn_cut)
        action_layout.addWidget(btn_open_folder)
        control_layout.addLayout(action_layout)

        splitter.addWidget(control_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

        # 拖拽支持
        self.drop_area = DropArea(title="拖拽单个视频文件到这里立即开始预览与裁切")
        self.drop_area.setFixedHeight(75)
        self.drop_area.files_dropped.connect(self._on_dropped_file)
        layout.addWidget(self.drop_area)

    def _choose_video_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.mov *.mkv *.avi *.flv *.ts *.webm);;所有文件 (*.*)"
        )
        if file_path:
            self.load_video(file_path)

    def _on_dropped_file(self, paths: list[str]):
        if paths:
            self.load_video(paths[0])

    def load_video(self, file_path: str):
        if not os.path.isfile(file_path):
            return

        self.current_file = file_path
        self.lbl_file_path.setText(file_path)
        self.lbl_file_path.setStyleSheet("color: #00d2ff; font-weight: bold;")

        # 读取元信息
        info = KeyframeHelper.get_video_info(file_path)
        self.total_duration = info.get("duration", 0.0)
        dur_str = KeyframeHelper.format_time(self.total_duration)
        size_mb = f"{info.get('size', 0) / (1024*1024):.2f} MB"
        
        # 读取关键帧
        self.keyframes = KeyframeHelper.get_keyframes(file_path)

        meta_text = (
            f"分辨率: {info.get('width', 0)}x{info.get('height', 0)}\n"
            f"编码格式: {info.get('codec', '未知')} ({info.get('fps', 0)} fps)\n"
            f"视频时长: {dur_str} ({self.total_duration:.2f} 秒)\n"
            f"文件大小: {size_mb}\n"
            f"关键帧总数: {len(self.keyframes)} 个 (平均间隔: {(self.total_duration/max(1, len(self.keyframes))):.2f}s)"
        )
        self.lbl_video_meta.setText(meta_text)

        # 初始化裁切时间
        self.edit_start.setText("00:00:00.00")
        self.edit_end.setText(dur_str)

        # 加载至播放器
        self.player_widget.load_video(file_path)
        self._update_snap_preview()

    def _on_player_mark_in(self, seconds: float):
        self.edit_start.setText(KeyframeHelper.format_time(seconds))

    def _on_player_mark_out(self, seconds: float):
        self.edit_end.setText(KeyframeHelper.format_time(seconds))

    def _update_snap_preview(self):
        if not self.current_file or not self.keyframes:
            return

        s_val = KeyframeHelper.parse_time(self.edit_start.text()) or 0.0
        e_val = KeyframeHelper.parse_time(self.edit_end.text()) or self.total_duration

        if not self.chk_auto_snap.isChecked():
            self.lbl_snap_result.setText(f"吸附已关闭：将直接按精确时间截取")
            return

        s_snap, s_diff = KeyframeHelper.snap_to_keyframe(s_val, self.keyframes, mode="floor")
        e_snap, e_diff = KeyframeHelper.snap_to_keyframe(e_val, self.keyframes, mode="ceil")

        self.lbl_snap_result.setText(
            f"起点对齐: {KeyframeHelper.format_time(s_snap)} ({s_diff:+.2f}s)\n"
            f"终点对齐: {KeyframeHelper.format_time(e_snap)} ({e_diff:+.2f}s)\n"
            f"实际片段时长: {KeyframeHelper.format_time(max(0.0, e_snap - s_snap))}"
        )

    def _start_cut(self):
        if not self.current_file:
            QMessageBox.warning(self, "提示", "请先载入需要裁切的视频文件！")
            return

        s_sec = KeyframeHelper.parse_time(self.edit_start.text())
        e_sec = KeyframeHelper.parse_time(self.edit_end.text())

        if s_sec is None or e_sec is None:
            QMessageBox.warning(self, "输入错误", "请检查起始时间或结束时间格式！")
            return

        if e_sec <= s_sec:
            QMessageBox.warning(self, "逻辑错误", "结束时间必须大于起始时间！")
            return

        self.btn_cut.setEnabled(False)
        self.btn_cut.setText("⏳ 正在毫秒级流复制裁切...")

        auto_snap = self.chk_auto_snap.isChecked()
        self.worker = CutterWorker(
            self.current_file,
            start_sec=s_sec,
            end_sec=e_sec,
            auto_snap=auto_snap
        )
        self.worker.finished.connect(self._on_cut_finished)
        self.worker.start()

    def _on_cut_finished(self, success: bool, msg: str, out_path: str):
        self.btn_cut.setEnabled(True)
        self.btn_cut.setText("⚡ 极速无损裁切 (毫秒级导出)")
        if success:
            QMessageBox.information(
                self, "裁切成功",
                f"🎉 视频极速截取成功！\n\n已保存至:\n{out_path}"
            )
        else:
            QMessageBox.critical(self, "裁切失败", f"处理过程中发生错误:\n{msg}")

    def _open_output_dir(self):
        if self.current_file:
            out_dir = Path(self.current_file).parent / "output_cut"
            out_dir.mkdir(parents=True, exist_ok=True)
            if os.name == 'nt':
                os.startfile(str(out_dir))
            else:
                subprocess.run(['xdg-open', str(out_dir)])
        else:
            QMessageBox.information(self, "提示", "请先载入视频以确定同级输出目录。")
