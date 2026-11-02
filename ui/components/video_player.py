import os
import sys
import av
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLabel, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor

from core.keyframe_helper import KeyframeHelper
from ui.components.range_slider import RangeSlider

class VideoCanvas(QLabel):
    """自适应宽高比例的视频画面渲染控件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #0b0c0e; border-radius: 6px; color: #5c6370; font-size: 14px;")
        self.setText("🎬 点击或拖入视频文件以开始预览")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._current_pixmap = None

    def display_pixmap(self, pixmap: QPixmap):
        self._current_pixmap = pixmap
        self._update_display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()

    def _update_display(self):
        if self._current_pixmap and not self._current_pixmap.isNull():
            scaled = self._current_pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.setPixmap(scaled)

class VideoPlayerWidget(QWidget):
    """
    通用视频预览播放器 (基于 PyAV / FFmpeg 核心解码)
    100% 独立于 Windows 系统编解码器，完美支持 HEVC/H.265、H.264、AV1 等任意格式
    内置视频时间轴进度条与双向裁切入点/出点滑块 (RangeSlider)
    """
    position_changed = Signal(float)       # 当前播放秒数
    range_changed = Signal(float, float)   # (in_sec, out_sec)
    mark_in_clicked = Signal(float)        # 起点打点
    mark_out_clicked = Signal(float)       # 终点打点

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = ""
        self.container = None
        self.video_stream = None
        self.duration_sec = 0.0
        self.fps = 30.0
        self.current_sec = 0.0
        self._is_playing = False
        self._is_scrubbing = False

        # 播放定时器
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._on_play_step)

        # UI 构建
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. 视频视口
        self.canvas = VideoCanvas()
        layout.addWidget(self.canvas, stretch=1)

        # 2. 控制面板卡片
        control_card = QFrame()
        control_card.setStyleSheet("background-color: #21252b; border-radius: 6px; padding: 6px;")
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(10, 6, 10, 6)
        control_layout.setSpacing(4)

        # A. 播放进度条与时间显示
        time_bar = QHBoxLayout()
        self.slider_play = QSlider(Qt.Horizontal)
        self.slider_play.setRange(0, 1000)
        self.slider_play.sliderPressed.connect(self._on_slider_pressed)
        self.slider_play.sliderReleased.connect(self._on_slider_released)
        self.slider_play.sliderMoved.connect(self._on_slider_moved)

        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.time_label.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; color: #abb2bf;")

        time_bar.addWidget(self.slider_play, stretch=1)
        time_bar.addWidget(self.time_label)
        control_layout.addLayout(time_bar)

        # B. 裁切区间滑块 (入点和出点双向拖拽)
        range_bar = QHBoxLayout()
        lbl_range_title = QLabel("裁切区间:")
        lbl_range_title.setStyleSheet("font-size: 11px; color: #8a919e; font-weight: bold;")

        self.range_slider = RangeSlider()
        self.range_slider.range_changed.connect(self._on_range_slider_changed)
        self.range_slider.handle_scrubbing.connect(self._on_range_scrubbing)

        range_bar.addWidget(lbl_range_title)
        range_bar.addWidget(self.range_slider, stretch=1)
        control_layout.addLayout(range_bar)

        # C. 操作按钮条
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_play = QPushButton("▶ 播放")
        self.btn_play.setFixedWidth(80)
        self.btn_play.clicked.connect(self.toggle_play)

        self.btn_step_back = QPushButton("-1s")
        self.btn_step_back.setFixedWidth(50)
        self.btn_step_back.clicked.connect(lambda: self.seek_relative(-1.0))

        self.btn_step_forward = QPushButton("+1s")
        self.btn_step_forward.setFixedWidth(50)
        self.btn_step_forward.clicked.connect(lambda: self.seek_relative(1.0))

        self.btn_mark_in = QPushButton("📍 标记为裁切起点")
        self.btn_mark_in.setStyleSheet("background-color: #2c3e50; border: 1px solid #00d2ff; color: #00d2ff; font-weight: bold;")
        self.btn_mark_in.clicked.connect(self._trigger_mark_in)

        self.btn_mark_out = QPushButton("🏁 标记为裁切终点")
        self.btn_mark_out.setStyleSheet("background-color: #3b2a30; border: 1px solid #e06c75; color: #e06c75; font-weight: bold;")
        self.btn_mark_out.clicked.connect(self._trigger_mark_out)

        btn_bar.addWidget(self.btn_play)
        btn_bar.addWidget(self.btn_step_back)
        btn_bar.addWidget(self.btn_step_forward)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_mark_in)
        btn_bar.addWidget(self.btn_mark_out)

        control_layout.addLayout(btn_bar)
        layout.addWidget(control_card)

    def load_video(self, file_path: str):
        if not os.path.exists(file_path):
            return

        self.pause()
        if self.container:
            try:
                self.container.close()
            except Exception:
                pass
            self.container = None

        self.current_file = file_path
        try:
            self.container = av.open(file_path)
            self.video_stream = self.container.streams.video[0]
            self.video_stream.thread_type = 'AUTO'

            # 估算时长与帧率
            dur = float(self.video_stream.duration * self.video_stream.time_base) if self.video_stream.duration else 0.0
            if dur <= 0:
                info = KeyframeHelper.get_video_info(file_path)
                dur = info.get("duration", 0.0)
            self.duration_sec = dur

            r_fps = self.video_stream.average_rate
            self.fps = float(r_fps) if r_fps and float(r_fps) > 0 else 30.0

            # 重设滑块
            self.slider_play.setValue(0)
            self.range_slider.set_range(0.0, self.duration_sec)
            self.range_slider.set_values(0.0, self.duration_sec)

            # 载入并显示第 0 帧
            self.seek_and_display(0.0)

        except Exception as e:
            self.canvas.setText(f"❌ 视频加载失败: {e}")

    def seek_and_display(self, seconds: float):
        """精准或快速定位到指定秒数并刷新渲染当前帧"""
        if not self.container or not self.video_stream:
            return

        seconds = max(0.0, min(self.duration_sec, seconds))
        self.current_sec = seconds

        try:
            pts = int(seconds / self.video_stream.time_base)
            # any_frame=False 定位关键帧，然后解码至目标帧
            self.container.seek(pts, stream=self.video_stream, any_frame=False)
            
            for frame in self.container.decode(self.video_stream):
                cur_pts_sec = float(frame.pts * self.video_stream.time_base)
                # 当靠近目标时间或已到第1帧有效画面
                if cur_pts_sec >= seconds - 0.05 or True:
                    rgb = frame.to_rgb().to_ndarray()
                    h, w, _ = rgb.shape
                    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
                    pix = QPixmap.fromImage(qimg)
                    self.canvas.display_pixmap(pix)
                    break
        except Exception:
            pass

        # 更新播放进度条与时间文本
        if not self._is_scrubbing and self.duration_sec > 0:
            val = int((self.current_sec / self.duration_sec) * 1000)
            self.slider_play.blockSignals(True)
            self.slider_play.setValue(val)
            self.slider_play.blockSignals(False)

        self._update_time_label()
        self.position_changed.emit(self.current_sec)

    def toggle_play(self):
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if not self.container:
            return
        self._is_playing = True
        self.btn_play.setText("⏸ 暂停")
        interval_ms = max(15, int(1000.0 / min(self.fps, 40.0)))
        self.play_timer.start(interval_ms)

    def pause(self):
        self._is_playing = False
        self.btn_play.setText("▶ 播放")
        self.play_timer.stop()

    def seek_relative(self, delta_sec: float):
        self.seek_and_display(self.current_sec + delta_sec)

    def get_current_seconds(self) -> float:
        return self.current_sec

    def set_range_values(self, start_sec: float, end_sec: float):
        self.range_slider.set_values(start_sec, end_sec)

    def _on_play_step(self):
        step_sec = 1.0 / self.fps
        next_sec = self.current_sec + step_sec
        if next_sec >= self.duration_sec:
            self.pause()
            self.seek_and_display(self.duration_sec)
        else:
            self.seek_and_display(next_sec)

    def _on_slider_pressed(self):
        self._is_scrubbing = True
        if self._is_playing:
            self.pause()

    def _on_slider_released(self):
        self._is_scrubbing = False
        val = self.slider_play.value()
        if self.duration_sec > 0:
            target_sec = (val / 1000.0) * self.duration_sec
            self.seek_and_display(target_sec)

    def _on_slider_moved(self, val):
        if self.duration_sec > 0:
            target_sec = (val / 1000.0) * self.duration_sec
            self.seek_and_display(target_sec)

    def _on_range_slider_changed(self, in_sec: float, out_sec: float):
        self.range_changed.emit(in_sec, out_sec)

    def _on_range_scrubbing(self, handle_name: str, sec: float):
        """拖拽裁切滑块的入点或出点时，即时预览对应时间点的画面"""
        if self._is_playing:
            self.pause()
        self.seek_and_display(sec)

    def _trigger_mark_in(self):
        self.range_slider.set_values(self.current_sec, self.range_slider.end_val)
        self.mark_in_clicked.emit(self.current_sec)
        self.range_changed.emit(self.current_sec, self.range_slider.end_val)

    def _trigger_mark_out(self):
        self.range_slider.set_values(self.range_slider.start_val, self.current_sec)
        self.mark_out_clicked.emit(self.current_sec)
        self.range_changed.emit(self.range_slider.start_val, self.current_sec)

    def _update_time_label(self):
        cur_fmt = KeyframeHelper.format_time(self.current_sec, show_ms=False)
        tot_fmt = KeyframeHelper.format_time(self.duration_sec, show_ms=False)
        self.time_label.setText(f"{cur_fmt} / {tot_fmt}")

    def close(self):
        self.pause()
        if self.container:
            try:
                self.container.close()
            except Exception:
                pass
            self.container = None
        super().close()
