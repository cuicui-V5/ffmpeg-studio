import os
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.components.splash_screen import AppSplashScreen

def main():
    # 设置 Windows 任务栏应用分组
    if os.name == 'nt':
        import ctypes
        myappid = 'antigravity.ffmpeg.multitool.v1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # 启用高 DPI 缩放支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    # 1. 瞬时呈现启动视窗 (< 100ms 给出视觉响应与加载动画，彻底消除干等感)
    splash = AppSplashScreen()
    splash.show()
    app.processEvents()

    # 2. 状态更新并装载主题样式
    splash.set_status("正在载入硬件加速与系统主题...")
    from ui.theme import DARK_THEME_QSS
    app.setStyleSheet(DARK_THEME_QSS)

    # 3. 装载主工作台并呈现
    splash.set_status("正在载入工作台界面...")
    from ui.main_window import MainWindow
    window = MainWindow()

    window.show()
    app.processEvents()

    # 4. 平滑关闭启动视窗
    splash.close()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
