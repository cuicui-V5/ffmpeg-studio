import os
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLabel, QFrame, QSizePolicy, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtGui import QImage, QPixmap

from core.keyframe_helper import KeyframeHelper
from ui.components.range_slider import RangeSlider

class VideoCanvas(QLabel):
    """自适应宽高比例的视频画面渲染控件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #0f172a; border: 1px solid #e2e8f0; border-radius: 8px; color: #94a3b8; font-size: 14px;")
        self.setText("拖入或选择视频预览")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._current_pixmap = None

    def display_pixmap(self, pixmap: QPixmap):
        self._current_pixmap = pixmap
        self.setText("")
        self._update_display()

    def show_loading(self, text: str = "正在载入视频..."):
        self._current_pixmap = None
        self.setPixmap(QPixmap())
        self.setText(text)
        self.setStyleSheet(
            "background-color: #0f172a; border: 1px solid #e2e8f0; border-radius: 8px; color: #94a3b8; font-size: 13px;"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()

    def _update_display(self):
        if self._current_pixmap and not self._current_pixmap.isNull():
            scaled = self._current_pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.setPixmap(scaled)

class VideoLoadWorker(QThread):
    """后台视频异步加载线程，避免打开大型文件时阻塞主 UI"""
    loaded = Signal(object, object, float, float) # (container, stream, duration, fps)
    failed = Signal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            import av
            container = av.open(self.file_path)
            if self._is_cancelled:
                container.close()
                return
            stream = container.streams.video[0]
            stream.thread_type = 'AUTO'
            dur = float(stream.duration * stream.time_base) if stream.duration else 0.0
            r_fps = stream.average_rate
            fps = float(r_fps) if r_fps and float(r_fps) > 0 else 30.0
            self.loaded.emit(container, stream, dur, fps)
        except Exception as e:
            if not self._is_cancelled:
                self.failed.emit(str(e))

class VideoPlayerWidget(QWidget):
    """
    通用视频预览播放器 (基于 PyAV / FFmpeg 核心解码)
    100% 独立于 Windows 系统编解码器，完美支持 HEVC/H.265、H.264、AV1 等任意格式
    内置视频时间轴进度条与双向裁切入点/出点滑块 (RangeSlider)，两轴像素级垂直严格对齐
    具备高频拖拽节流消抖机制，滑动预览丝滑流畅不卡顿
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
        self._load_worker = None
        self._on_loaded_callback = None
        self._initial_range = None

        # 播放定时器
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._on_play_step)

        # 拖拽节流定时器 (避免高频拖拽连续解码导致界面假死或卡顿)
        self._pending_seek_sec = None
        self._seek_throttle_timer = QTimer(self)
        self._seek_throttle_timer.setSingleShot(True)
        self._seek_throttle_timer.setInterval(20)  # ~50 FPS 渲染速率
        self._seek_throttle_timer.timeout.connect(self._do_pending_seek)

        # UI 构建
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. 视频视口
        self.canvas = VideoCanvas()
        layout.addWidget(self.canvas, stretch=1)

        # 2. 控制面板卡片
        control_card = QFrame()
        control_card.setStyleSheet("QFrame#playerControlCard { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }")
        control_card.setObjectName("playerControlCard")
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(10, 8, 10, 8)
        control_layout.setSpacing(6)

        # A. 播放进度条 (左标 65px + 滑块 stretch=1 + 右标 145px)
        time_bar = QHBoxLayout()
        time_bar.setContentsMargins(0, 0, 0, 0)
        time_bar.setSpacing(8)

        lbl_play = QLabel("播放位置:")
        lbl_play.setFixedWidth(65)
        lbl_play.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_play.setStyleSheet("color: #475569; font-weight: bold; font-size: 12px;")

        self.slider_play = QSlider(Qt.Horizontal)
        self.slider_play.setRange(0, 1000)
        self.slider_play.sliderPressed.connect(self._on_slider_pressed)
        self.slider_play.sliderReleased.connect(self._on_slider_released)
        self.slider_play.sliderMoved.connect(self._on_slider_moved)

        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.time_label.setFixedWidth(145)
        self.time_label.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; color: #0f172a;")

        time_bar.addWidget(lbl_play)
        time_bar.addWidget(self.slider_play, stretch=1)
        time_bar.addWidget(self.time_label)
        control_layout.addLayout(time_bar)

        # B. 裁切区间滑块 (左标 65px + 滑块 stretch=1 + 右标 145px，与播放进度条完美对齐)
        range_bar = QHBoxLayout()
        range_bar.setContentsMargins(0, 0, 0, 0)
        range_bar.setSpacing(8)

        lbl_range_title = QLabel("裁切区间:")
        lbl_range_title.setFixedWidth(65)
        lbl_range_title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_range_title.setStyleSheet("color: #2563eb; font-weight: bold; font-size: 12px;")

        self.range_slider = RangeSlider()
        self.range_slider.range_changed.connect(self._on_range_slider_changed)
        self.range_slider.handle_scrubbing.connect(self._on_range_scrubbing)

        self.range_time_label = QLabel("00:00:00 -> 00:00:00")
        self.range_time_label.setFixedWidth(145)
        self.range_time_label.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; color: #2563eb; font-weight: 500;")

        range_bar.addWidget(lbl_range_title)
        range_bar.addWidget(self.range_slider, stretch=1)
        range_bar.addWidget(self.range_time_label)
        control_layout.addLayout(range_bar)

        # C. 操作按钮条
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_play = QPushButton("播放")
        self.btn_play.setFixedWidth(80)
        self.btn_play.clicked.connect(self.toggle_play)

        self.btn_step_back = QPushButton("-1s")
        self.btn_step_back.setFixedWidth(50)
        self.btn_step_back.clicked.connect(lambda: self.seek_relative(-1.0))

        self.btn_step_forward = QPushButton("+1s")
        self.btn_step_forward.setFixedWidth(50)
        self.btn_step_forward.clicked.connect(lambda: self.seek_relative(1.0))

        self.btn_mark_in = QPushButton("设置起点")
        self.btn_mark_in.setStyleSheet("background-color: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; font-weight: bold; border-radius: 4px; padding: 4px 10px;")
        self.btn_mark_in.clicked.connect(self._trigger_mark_in)

        self.btn_mark_out = QPushButton("设置终点")
        self.btn_mark_out.setStyleSheet("background-color: #fef2f2; border: 1px solid #fecaca; color: #dc2626; font-weight: bold; border-radius: 4px; padding: 4px 10px;")
        self.btn_mark_out.clicked.connect(self._trigger_mark_out)

        btn_bar.addWidget(self.btn_play)
        btn_bar.addWidget(self.btn_step_back)
        btn_bar.addWidget(self.btn_step_forward)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_mark_in)
        btn_bar.addWidget(self.btn_mark_out)

        control_layout.addLayout(btn_bar)
        layout.addWidget(control_card)

    def load_video_async(self, file_path: str, on_loaded=None, initial_range: tuple[float, float] = None):
        """后台异步加载视频，主 UI 保持响应不卡死，并带有加载动画指示"""
        if not os.path.exists(file_path):
            self.canvas.setText("未找到视频文件")
            return

        self.pause()
        if self._load_worker and self._load_worker.isRunning():
            self._load_worker.cancel()
            self._load_worker.wait()
            self._load_worker = None

        if self.container:
            try:
                self.container.close()
            except Exception:
                pass
            self.container = None

        self.current_file = file_path
        self._initial_range = initial_range
        self.canvas.show_loading("正在载入视频...")

        self._on_loaded_callback = on_loaded
        self._load_worker = VideoLoadWorker(file_path, self)
        self._load_worker.loaded.connect(self._on_async_loaded)
        self._load_worker.failed.connect(self._on_async_failed)
        self._load_worker.start()

    def _on_async_loaded(self, container, stream, dur, fps):
        self.container = container
        self.video_stream = stream
        if dur <= 0:
            info = KeyframeHelper.get_video_info(self.current_file)
            dur = info.get("duration", 0.0)
        self.duration_sec = dur
        self.fps = fps

        self.range_slider.set_range(0.0, self.duration_sec)
        if self._initial_range:
            init_s, init_e = self._initial_range
            init_s = max(0.0, min(self.duration_sec, init_s))
            init_e = max(init_s, min(self.duration_sec, init_e))
            self.range_slider.set_values(init_s, init_e)
            self._update_range_time_label(init_s, init_e)
            self.seek_and_display(init_s)
        else:
            self.slider_play.setValue(0)
            self.range_slider.set_values(0.0, self.duration_sec)
            self._update_range_time_label(0.0, self.duration_sec)
            self.seek_and_display(0.0)

        if self._on_loaded_callback:
            cb = self._on_loaded_callback
            self._on_loaded_callback = None
            cb()

    def _on_async_failed(self, err_msg: str):
        self.canvas.setText(f"视频加载失败: {err_msg}")
        self.canvas.setStyleSheet("background-color: #0b0c0e; border-radius: 6px; color: #e06c75; font-size: 13px;")

    def load_video(self, file_path: str, initial_range: tuple[float, float] = None):
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
        self._initial_range = initial_range
        try:
            import av
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
            self.range_slider.set_range(0.0, self.duration_sec)
            if initial_range:
                init_s, init_e = initial_range
                init_s = max(0.0, min(self.duration_sec, init_s))
                init_e = max(init_s, min(self.duration_sec, init_e))
                self.range_slider.set_values(init_s, init_e)
                self._update_range_time_label(init_s, init_e)
                self.seek_and_display(init_s)
            else:
                self.slider_play.setValue(0)
                self.range_slider.set_values(0.0, self.duration_sec)
                self._update_range_time_label(0.0, self.duration_sec)
                self.seek_and_display(0.0)

            # 载入并显示第 0 帧
            self.seek_and_display(0.0 if not initial_range else initial_range[0])

        except Exception as e:
            self.canvas.setText(f"视频加载失败: {e}")

    def _decode_and_render_frame(self, seconds: float):
        """核心底层解码并上屏单帧画面"""
        if not self.container or not self.video_stream:
            return

        seconds = max(0.0, min(self.duration_sec, seconds))
        self.current_sec = seconds

        try:
            pts = int(seconds / self.video_stream.time_base)
            # any_frame=False 高速定位到邻近关键帧解码
            self.container.seek(pts, stream=self.video_stream, any_frame=False)
            
            for frame in self.container.decode(self.video_stream):
                rgb = frame.to_rgb().to_ndarray()
                h, w, _ = rgb.shape
                qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
                pix = QPixmap.fromImage(qimg)
                self.canvas.display_pixmap(pix)
                break
        except Exception:
            pass

        self._update_time_label()
        self.position_changed.emit(self.current_sec)

    def seek_and_display(self, seconds: float):
        """即时定位并更新画面（用于点击、释放、暂停时）"""
        self._decode_and_render_frame(seconds)
        if not self._is_scrubbing and self.duration_sec > 0:
            val = int((self.current_sec / self.duration_sec) * 1000)
            self.slider_play.blockSignals(True)
            self.slider_play.setValue(val)
            self.slider_play.blockSignals(False)

    def _request_throttled_seek(self, seconds: float):
        """节流请求，高频拖拽时消除卡顿"""
        self.current_sec = max(0.0, min(self.duration_sec, seconds))
        self._update_time_label()

        self._pending_seek_sec = seconds
        if not self._seek_throttle_timer.isActive():
            self._seek_throttle_timer.start()

    def _do_pending_seek(self):
        if self._pending_seek_sec is not None:
            sec = self._pending_seek_sec
            self._pending_seek_sec = None
            self._decode_and_render_frame(sec)

    def toggle_play(self):
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if not self.container:
            return
        self._is_playing = True
        self.btn_play.setText("暂停")
        interval_ms = max(15, int(1000.0 / min(self.fps, 40.0)))
        self.play_timer.start(interval_ms)

    def pause(self):
        self._is_playing = False
        self.btn_play.setText("播放")
        self.play_timer.stop()

    def seek_relative(self, delta_sec: float):
        self.seek_and_display(self.current_sec + delta_sec)

    def get_current_seconds(self) -> float:
        return self.current_sec

    def set_range_values(self, start_sec: float, end_sec: float):
        self.range_slider.set_values(start_sec, end_sec)
        self._update_range_time_label(start_sec, end_sec)

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
            self._request_throttled_seek(target_sec)

    def _on_range_slider_changed(self, in_sec: float, out_sec: float):
        self._update_range_time_label(in_sec, out_sec)
        self.range_changed.emit(in_sec, out_sec)

    def _on_range_scrubbing(self, handle_name: str, sec: float):
        """拖拽裁切滑块入点或出点时，防抖节流实时渲染对应位置画面"""
        if self._is_playing:
            self.pause()
        self._request_throttled_seek(sec)

    def _trigger_mark_in(self):
        self.range_slider.set_values(self.current_sec, self.range_slider.end_val)
        self._update_range_time_label(self.current_sec, self.range_slider.end_val)
        self.mark_in_clicked.emit(self.current_sec)
        self.range_changed.emit(self.current_sec, self.range_slider.end_val)

    def _trigger_mark_out(self):
        self.range_slider.set_values(self.range_slider.start_val, self.current_sec)
        self._update_range_time_label(self.range_slider.start_val, self.current_sec)
        self.mark_out_clicked.emit(self.current_sec)
        self.range_changed.emit(self.range_slider.start_val, self.current_sec)

    def _update_time_label(self):
        cur_fmt = KeyframeHelper.format_time(self.current_sec, show_ms=False)
        tot_fmt = KeyframeHelper.format_time(self.duration_sec, show_ms=False)
        self.time_label.setText(f"{cur_fmt} / {tot_fmt}")

    def _update_range_time_label(self, in_sec: float, out_sec: float):
        in_fmt = KeyframeHelper.format_time(in_sec, show_ms=False)
        out_fmt = KeyframeHelper.format_time(out_sec, show_ms=False)
        self.range_time_label.setText(f"{in_fmt} -> {out_fmt}")

    def close(self):
        self.pause()
        if self._load_worker and self._load_worker.isRunning():
            self._load_worker.cancel()
            self._load_worker.wait()
            self._load_worker = None
        if self.container:
            try:
                self.container.close()
            except Exception:
                pass
            self.container = None
        super().close()
