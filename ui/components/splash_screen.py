from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication, QFrame
)
from PySide6.QtCore import Qt

class AppSplashScreen(QWidget):
    """
    超轻量桌面启动视窗 (秒级响应)
    在双击打开软件的第一时间（< 100ms）呈现现代浅色流光启动卡片，杜绝无响应黑屏干等
    """

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.resize(460, 200)
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 26)
        layout.setSpacing(8)

        # 软件标题与副标
        title = QLabel("FFmpeg 视频工具箱")
        title.setStyleSheet("""
            color: #0f172a;
            font-size: 20px;
            font-weight: bold;
            border: none;
            font-family: "Source Han Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
        """)
        
        subtitle = QLabel("高效音视频桌面工作台 · 极速流复制无损处理")
        subtitle.setStyleSheet("color: #64748b; font-size: 12px; border: none;")

        # 动态状态提示
        self.lbl_status = QLabel("正在初始化运行环境...")
        self.lbl_status.setStyleSheet("color: #2563eb; font-size: 12px; font-weight: 600; border: none;")

        # 进度指示微动条
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #f1f5f9;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #2563eb;
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
