from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, Signal, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont

class RangeSlider(QWidget):
    """
    双端裁切区间选择滑块 (In-Point & Out-Point Range Slider)
    支持拖拽入点与出点，并在拖动时发射实时位置信号用于视频画面预览
    """
    range_changed = Signal(float, float)       # (start_sec, end_sec)
    handle_scrubbing = Signal(str, float)      # ("start" 或 "end", 当前秒数) - 用于拖动时实时画面预览

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setMouseTracking(True)

        self.min_val = 0.0
        self.max_val = 100.0
        self.start_val = 0.0
        self.end_val = 100.0

        self._active_handle = None  # 'start', 'end', or None
        self._hover_handle = None
        self.handle_width = 14
        self.handle_height = 24

    def set_range(self, min_val: float, max_val: float):
        self.min_val = max(0.0, min_val)
        self.max_val = max(self.min_val + 0.1, max_val)
        self.start_val = self.min_val
        self.end_val = self.max_val
        self.update()

    def set_values(self, start_val: float, end_val: float):
        self.start_val = max(self.min_val, min(start_val, self.max_val))
        self.end_val = max(self.start_val, min(end_val, self.max_val))
        self.update()

    def _val_to_x(self, val: float) -> float:
        margin = self.handle_width / 2
        track_w = self.width() - 2 * margin
        if self.max_val <= self.min_val:
            return margin
        ratio = (val - self.min_val) / (self.max_val - self.min_val)
        return margin + ratio * track_w

    def _x_to_val(self, x: float) -> float:
        margin = self.handle_width / 2
        track_w = self.width() - 2 * margin
        if track_w <= 0:
            return self.min_val
        ratio = max(0.0, min(1.0, (x - margin) / track_w))
        return self.min_val + ratio * (self.max_val - self.min_val)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = self.handle_width / 2
        track_y = h / 2 - 3
        track_h = 6

        # 1. 轨道底色
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.setBrush(QBrush(QColor("#e2e8f0")))
        painter.drawRoundedRect(QRectF(margin, track_y, w - 2 * margin, track_h), 3, 3)

        # 2. 选中裁切区间高亮色
        x_start = self._val_to_x(self.start_val)
        x_end = self._val_to_x(self.end_val)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#3b82f6")))
        painter.drawRoundedRect(QRectF(x_start, track_y, max(2.0, x_end - x_start), track_h), 3, 3)

        # 3. 绘制起点 Handle (Blue)
        self._draw_handle(painter, x_start, is_start=True, is_active=(self._active_handle == 'start' or self._hover_handle == 'start'))

        # 4. 绘制终点 Handle (Red/Coral)
        self._draw_handle(painter, x_end, is_start=False, is_active=(self._active_handle == 'end' or self._hover_handle == 'end'))

    def _draw_handle(self, painter: QPainter, center_x: float, is_start: bool, is_active: bool):
        hw = self.handle_width
        hh = self.handle_height
        y = (self.height() - hh) / 2
        rect = QRectF(center_x - hw / 2, y, hw, hh)

        base_color = QColor("#2563eb") if is_start else QColor("#ef4444")
        if is_active:
            painter.setBrush(QBrush(base_color.darker(110)))
            painter.setPen(QPen(QColor("#ffffff"), 2))
        else:
            painter.setBrush(QBrush(base_color))
            painter.setPen(QPen(QColor("#ffffff"), 1.5))

        painter.drawRoundedRect(rect, 4, 4)

        # 绘制标志 ▶ 或 ◀
        painter.setPen(QPen(QColor("#ffffff"), 1.5))
        font = QFont("Consolas", 9, QFont.Bold)
        painter.setFont(font)
        mark = "▶" if is_start else "◀"
        painter.drawText(rect, Qt.AlignCenter, mark)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            x = event.position().x()
            x_start = self._val_to_x(self.start_val)
            x_end = self._val_to_x(self.end_val)
            dist_start = abs(x - x_start)
            dist_end = abs(x - x_end)

            if dist_start <= dist_end and dist_start < 25:
                self._active_handle = 'start'
            elif dist_end < 25:
                self._active_handle = 'end'
            else:
                # 点击在空白区域，将较近的 handle 移至点击处
                click_val = self._x_to_val(x)
                if abs(click_val - self.start_val) < abs(click_val - self.end_val):
                    self._active_handle = 'start'
                    self.start_val = min(click_val, self.end_val - 0.1)
                else:
                    self._active_handle = 'end'
                    self.end_val = max(click_val, self.start_val + 0.1)
                self.range_changed.emit(self.start_val, self.end_val)
                self.handle_scrubbing.emit(self._active_handle, self.start_val if self._active_handle == 'start' else self.end_val)
                self.update()

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if self._active_handle:
            val = self._x_to_val(x)
            if self._active_handle == 'start':
                self.start_val = max(self.min_val, min(val, self.end_val - 0.05))
                self.range_changed.emit(self.start_val, self.end_val)
                self.handle_scrubbing.emit('start', self.start_val)
            elif self._active_handle == 'end':
                self.end_val = min(self.max_val, max(val, self.start_val + 0.05))
                self.range_changed.emit(self.start_val, self.end_val)
                self.handle_scrubbing.emit('end', self.end_val)
            self.update()
        else:
            # 鼠标悬停检测
            x_start = self._val_to_x(self.start_val)
            x_end = self._val_to_x(self.end_val)
            if abs(x - x_start) < 15:
                self._hover_handle = 'start'
                self.setCursor(Qt.SizeHorCursor)
            elif abs(x - x_end) < 15:
                self._hover_handle = 'end'
                self.setCursor(Qt.SizeHorCursor)
            else:
                self._hover_handle = None
                self.setCursor(Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._active_handle = None
            self.update()
