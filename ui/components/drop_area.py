from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from pathlib import Path

class DropArea(QFrame):
    """文件/文件夹拖拽容器 (支持点击打开选择器与拖拽)"""
    files_dropped = Signal(list)  # list[str]
    clicked = Signal()

    def __init__(self, title: str = "拖入视频文件或文件夹至此处", subtitle: str = "支持多选拖拽 / 点击直接浏览"):
        super().__init__()
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("dropArea")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(20, 24, 20, 24)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #2563eb;")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.sub_label = QLabel(subtitle)
        self.sub_label.setStyleSheet("font-size: 12px; color: #64748b;")
        self.sub_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title_label)
        layout.addWidget(self.sub_label)

        self._style_normal = """
            QFrame#dropArea {
                border: 2px dashed #cbd5e1;
                border-radius: 8px;
                background-color: #f8fafc;
            }
            QFrame#dropArea:hover {
                border-color: #3b82f6;
                background-color: #eff6ff;
            }
        """
        self._style_active = """
            QFrame#dropArea {
                border: 2px dashed #2563eb;
                border-radius: 8px;
                background-color: #dbeafe;
            }
        """
        self.setStyleSheet(self._style_normal)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self._style_active)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._style_normal)

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = []
        for url in urls:
            local_path = url.toLocalFile()
            if local_path:
                paths.append(local_path)
        
        self.dragLeaveEvent(None)
        if paths:
            self.files_dropped.emit(paths)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
