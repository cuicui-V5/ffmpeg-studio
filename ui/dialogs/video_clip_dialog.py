import os
import av
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QGroupBox, QMessageBox, QSplitter, QFrame
)
from PySide6.QtCore import Qt

from core.tasks.merge_task import MergeItem
from core.keyframe_helper import KeyframeHelper
from ui.components.video_player import VideoPlayerWidget

class VideoClipDialog(QDialog):
    """
    视频合并 - 单视频精准裁剪弹窗
    界面与处理逻辑对齐“视频裁剪”模块，支持关键帧自动吸附、实时拖拽预览
    """

    def __init__(self, item: MergeItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle(f"裁剪视频 - {item.filename}")
        self.setMinimumSize(1020, 680)
        self.resize(1100, 720)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 左右分割器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：视频播放器与双轨滑块
        player_container = QFrame()
        player_layout = QVBoxLayout(player_container)
        player_layout.setContentsMargins(0, 0, 0, 0)
        self.player_widget = VideoPlayerWidget(self)
        self.player_widget.mark_in_clicked.connect(self._on_player_mark_in)
        self.player_widget.mark_out_clicked.connect(self._on_player_mark_out)
        self.player_widget.range_changed.connect(self._on_player_range_changed)
        player_layout.addWidget(self.player_widget)
        splitter.addWidget(player_container)

        # 右侧：控制与参数卡片
        control_card = QFrame()
        control_card.setObjectName("dialogControlCard")
        control_card.setStyleSheet("QFrame#dialogControlCard { background-color: #1e2025; border-radius: 6px; }")
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(14, 14, 14, 14)
        control_layout.setSpacing(12)

        # 1. 视频属性
        self.group_info = QGroupBox("视频属性")
        info_layout = QVBoxLayout(self.group_info)
        size_mb = item.size / (1024 * 1024)
        size_str = f"{size_mb / 1024:.2f} GB" if size_mb >= 1024 else f"{size_mb:.1f} MB"
        aud_str = f"{item.audio_codec} {item.sample_rate}Hz {item.channels}ch" if item.audio_codec != "none" else "无音频"
        self.lbl_video_meta = QLabel(
            f"分辨率: {item.width}x{item.height}\n"
            f"编码: {item.codec} ({item.pix_fmt})\n"
            f"帧率: {item.fps:.1f} fps\n"
            f"音频: {aud_str}\n"
            f"原始时长: {KeyframeHelper.format_time(item.duration, show_ms=True)}\n"
            f"文件大小: {size_str}"
        )
        self.lbl_video_meta.setStyleSheet("font-family: Consolas, monospace; line-height: 1.4;")
        info_layout.addWidget(self.lbl_video_meta)
        control_layout.addWidget(self.group_info)

        # 2. 裁剪区间设置
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
        self.edit_end = QLineEdit(KeyframeHelper.format_time(item.duration, show_ms=True))
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

        # 3. 操作按钮卡片
        action_box = QGroupBox("执行操作")
        action_layout = QVBoxLayout(action_box)
        action_layout.setSpacing(8)

        self.btn_confirm = QPushButton("确定")
        self.btn_confirm.setObjectName("primaryBtn")
        self.btn_confirm.setFixedHeight(38)
        self.btn_confirm.clicked.connect(self._apply_crop)

        self.btn_reset = QPushButton("重置为全片")
        self.btn_reset.setFixedHeight(34)
        self.btn_reset.clicked.connect(self._reset_to_full)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.clicked.connect(self.reject)

        action_layout.addWidget(self.btn_confirm)
        action_layout.addWidget(self.btn_reset)
        action_layout.addWidget(self.btn_cancel)
        control_layout.addWidget(action_box)

        splitter.addWidget(control_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

        # 加载视频与初始化裁剪范围
        self._init_video_and_range()

    def _init_video_and_range(self):
        file_path_str = str(self.item.filepath)
        if os.path.exists(file_path_str):
            self.player_widget.load_video(file_path_str)

        if self.item.is_cropped:
            s_val = self.item.crop_start
            e_val = self.item.crop_end
        else:
            s_val = 0.0
            e_val = self.item.duration

        self.edit_start.setText(KeyframeHelper.format_time(s_val, show_ms=True))
        self.edit_end.setText(KeyframeHelper.format_time(e_val, show_ms=True))
        self.player_widget.range_slider.set_range(0.0, self.item.duration)
        self.player_widget.range_slider.set_values(s_val, e_val)
        self._update_snap_preview()

    def _on_player_mark_in(self, sec: float):
        self.edit_start.setText(KeyframeHelper.format_time(sec, show_ms=True))
        e_sec = KeyframeHelper.parse_time(self.edit_end.text()) or self.item.duration
        self.player_widget.range_slider.set_values(sec, max(sec, e_sec))

    def _on_player_mark_out(self, sec: float):
        self.edit_end.setText(KeyframeHelper.format_time(sec, show_ms=True))
        s_sec = KeyframeHelper.parse_time(self.edit_start.text()) or 0.0
        self.player_widget.range_slider.set_values(min(sec, s_sec), sec)

    def _on_player_range_changed(self, in_sec: float, out_sec: float):
        self.edit_start.blockSignals(True)
        self.edit_end.blockSignals(True)
        self.edit_start.setText(KeyframeHelper.format_time(in_sec, show_ms=True))
        self.edit_end.setText(KeyframeHelper.format_time(out_sec, show_ms=True))
        self.edit_start.blockSignals(False)
        self.edit_end.blockSignals(False)
        self._update_snap_preview()

    def _update_snap_preview(self):
        s_val = KeyframeHelper.parse_time(self.edit_start.text())
        e_val = KeyframeHelper.parse_time(self.edit_end.text())

        if s_val is None or e_val is None or s_val >= e_val:
            self.lbl_snap_result.setText("时间格式不正确或区间无效")
            return

        container = getattr(self.player_widget, "container", None)
        stream = getattr(self.player_widget, "video_stream", None)

        if container and stream:
            try:
                s_snap, s_diff = KeyframeHelper.find_keyframe_instant(container, stream, s_val, mode="floor")
                e_snap, e_diff = KeyframeHelper.find_keyframe_instant(container, stream, e_val, mode="ceil")
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

    def _apply_crop(self):
        s_val = KeyframeHelper.parse_time(self.edit_start.text())
        e_val = KeyframeHelper.parse_time(self.edit_end.text())

        if s_val is None or e_val is None:
            QMessageBox.warning(self, "格式错误", "请输入有效的时间格式，如 00:00:10.50。")
            return

        s_val = max(0.0, s_val)
        e_val = min(self.item.duration, e_val)

        if s_val >= e_val:
            QMessageBox.warning(self, "时间错误", "起始时间必须小于结束时间。")
            return

        container = getattr(self.player_widget, "container", None)
        stream = getattr(self.player_widget, "video_stream", None)

        if container and stream:
            try:
                s_snap, _ = KeyframeHelper.find_keyframe_instant(container, stream, s_val, mode="floor")
                e_snap, _ = KeyframeHelper.find_keyframe_instant(container, stream, e_val, mode="ceil")
            except Exception:
                s_snap, e_snap = s_val, e_val
        else:
            s_snap, e_snap = s_val, e_val

        # 判断是否几乎等于全片
        if s_val <= 0.08 and e_val >= (self.item.duration - 0.08):
            self.item.is_cropped = False
            self.item.crop_start = 0.0
            self.item.crop_end = self.item.duration
            self.item.snapped_start = 0.0
            self.item.snapped_end = self.item.duration
        else:
            self.item.is_cropped = True
            self.item.crop_start = s_val
            self.item.crop_end = e_val
            self.item.snapped_start = s_snap
            self.item.snapped_end = e_snap

        self.player_widget.close()
        self.accept()

    def _reset_to_full(self):
        self.item.is_cropped = False
        self.item.crop_start = 0.0
        self.item.crop_end = self.item.duration
        self.item.snapped_start = 0.0
        self.item.snapped_end = self.item.duration
        self.player_widget.close()
        self.accept()

    def closeEvent(self, event):
        self.player_widget.close()
        super().closeEvent(event)

    def reject(self):
        self.player_widget.close()
        super().reject()
