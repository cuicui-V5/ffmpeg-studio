from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication
)
from PySide6.QtCore import Qt

class AppSplashScreen(QWidget):
    """
    超轻量桌面启动视窗 (秒级响应)
    在双击打开软件的第一时间（< 100ms）呈现现代深色流光启动卡片，杜绝无响应黑屏干等
    """

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.resize(460, 210)
        self.setStyleSheet("""
            QWidget {
                background-color: #1e2025;
                border: 1px solid #3e4451;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(8)

        # 软件标题与副标
        title = QLabel("FFmpeg 视频工具箱")
        title.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: bold; border: none; font-family: Microsoft YaHei, Segoe UI, sans-serif;")
        
        subtitle = QLabel("高效音视频桌面工作台")
        subtitle.setStyleSheet("color: #abb2bf; font-size: 12px; border: none;")

        # 动态状态提示
        self.lbl_status = QLabel("正在初始化运行环境...")
        self.lbl_status.setStyleSheet("color: #00d2ff; font-size: 12px; font-weight: 500; border: none;")

        # 流光微动进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #282c34;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #00d2ff;
                border-radius: 2px;
            }
        """)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.progress)

        # 居中显示于主屏幕中央
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            x = (geo.width() - self.width()) // 2
            y = (geo.height() - self.height()) // 2
            self.move(x, y)

    def set_status(self, text: str):
        """更新启动步骤状态文字并强制刷新事件循环"""
        self.lbl_status.setText(text)
        QApplication.processEvents()
