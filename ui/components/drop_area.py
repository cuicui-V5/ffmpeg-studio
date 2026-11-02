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

        self.title_label = QLabel(f"📂  {title}")
        self.title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #00d2ff;")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.sub_label = QLabel(subtitle)
        self.sub_label.setStyleSheet("font-size: 12px; color: #8a919e;")
        self.sub_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title_label)
        layout.addWidget(self.sub_label)

        self.setStyleSheet("""
            QFrame#dropArea {
                border: 2px dashed #3e4451;
                border-radius: 8px;
                background-color: #1a1b1f;
            }
            QFrame#dropArea:hover {
                border-color: #00d2ff;
                background-color: #20232a;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("""
                QFrame#dropArea {
                    border: 2px dashed #00d2ff;
                    border-radius: 8px;
                    background-color: #242b35;
                }
            """)

    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            QFrame#dropArea {
                border: 2px dashed #3e4451;
                border-radius: 8px;
                background-color: #1a1b1f;
            }
            QFrame#dropArea:hover {
                border-color: #00d2ff;
                background-color: #20232a;
            }
        """)

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
