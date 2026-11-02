import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLabel, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from core.keyframe_helper import KeyframeHelper

class VideoPlayerWidget(QWidget):
    """
    轻量内嵌视频预览播放器
    支持播放/暂停、快进/快退、时间轴拖拽、打点标记起止点
    """
    mark_in_clicked = Signal(float)   # 起点打点 (秒)
    mark_out_clicked = Signal(float)  # 终点打点 (秒)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration_sec = 0.0
        self._is_slider_pressed = False

        # 播放器与音频后端
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        # 视频渲染控件
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #0b0c0e; border-radius: 6px;")
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.player.setVideoOutput(self.video_widget)

        # 信号绑定
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)

        # UI 构建
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 视频视口
        layout.addWidget(self.video_widget, stretch=1)

        # 控制栏卡片
        control_card = QFrame()
        control_card.setStyleSheet("background-color: #21252b; border-radius: 6px; padding: 4px;")
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(8, 4, 8, 4)
        control_layout.setSpacing(4)

        # 时间轴滑块 + 时间标签
        slider_layout = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.sliderMoved.connect(self._on_slider_moved)

        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.time_label.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; color: #abb2bf;")

        slider_layout.addWidget(self.slider, stretch=1)
        slider_layout.addWidget(self.time_label)
        control_layout.addLayout(slider_layout)

        # 操作按钮条
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

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
        self.btn_mark_in.setStyleSheet("background-color: #2c3e50; border: 1px solid #3498db; color: #3498db; font-weight: bold;")
        self.btn_mark_in.clicked.connect(self._trigger_mark_in)

        self.btn_mark_out = QPushButton("🏁 标记为裁切终点")
        self.btn_mark_out.setStyleSheet("background-color: #3b2a30; border: 1px solid #e06c75; color: #e06c75; font-weight: bold;")
        self.btn_mark_out.clicked.connect(self._trigger_mark_out)

        btn_layout.addWidget(self.btn_play)
        btn_layout.addWidget(self.btn_step_back)
        btn_layout.addWidget(self.btn_step_forward)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_mark_in)
        btn_layout.addWidget(self.btn_mark_out)

        control_layout.addLayout(btn_layout)
        layout.addWidget(control_card)

    def load_video(self, file_path: str):
        if not os.path.exists(file_path):
            return
        self.player.setSource(QUrl.fromLocalFile(file_path))
        # 暂停在第 0 帧
        self.player.pause()
        self.btn_play.setText("▶ 播放")

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.btn_play.setText("▶ 播放")
        else:
            self.player.play()
            self.btn_play.setText("⏸ 暂停")

    def seek_relative(self, delta_sec: float):
        cur_ms = self.player.position()
        target_ms = max(0, min(self.player.duration(), cur_ms + int(delta_sec * 1000)))
        self.player.setPosition(target_ms)

    def get_current_seconds(self) -> float:
        return self.player.position() / 1000.0

    def _trigger_mark_in(self):
        self.mark_in_clicked.emit(self.get_current_seconds())

    def _trigger_mark_out(self):
        self.mark_out_clicked.emit(self.get_current_seconds())

    def _on_slider_pressed(self):
        self._is_slider_pressed = True

    def _on_slider_released(self):
        self._is_slider_pressed = False
        val = self.slider.value()
        total_ms = self.player.duration()
        if total_ms > 0:
            target_ms = int((val / 1000.0) * total_ms)
            self.player.setPosition(target_ms)

    def _on_slider_moved(self, val):
        total_ms = self.player.duration()
        if total_ms > 0:
            cur_sec = (val / 1000.0) * (total_ms / 1000.0)
            self._update_time_label(cur_sec, self.duration_sec)

    def _on_duration_changed(self, dur_ms):
        self.duration_sec = dur_ms / 1000.0
        cur_sec = self.player.position() / 1000.0
        self._update_time_label(cur_sec, self.duration_sec)

    def _on_position_changed(self, pos_ms):
        if not self._is_slider_pressed and self.player.duration() > 0:
            val = int((pos_ms / self.player.duration()) * 1000)
            self.slider.setValue(val)
            self._update_time_label(pos_ms / 1000.0, self.duration_sec)

    def _update_time_label(self, cur_sec: float, total_sec: float):
        cur_fmt = KeyframeHelper.format_time(cur_sec, show_ms=False)
        tot_fmt = KeyframeHelper.format_time(total_sec, show_ms=False)
        self.time_label.setText(f"{cur_fmt} / {tot_fmt}")

    def close(self):
        self.player.stop()
        super().close()
