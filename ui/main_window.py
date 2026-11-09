from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel, QWidget, QVBoxLayout
)
from PySide6.QtCore import Qt
from ui.tabs.tab_compress import TabCompress
from ui.tabs.tab_cutter import TabCutter
from ui.tabs.tab_split import TabSplit
from ui.tabs.tab_merge import TabMerge
from ui.tabs.tab_settings import TabSettings
from core.tool_manager import tool_mgr
from core.hardware import HardwareDetector

class MainWindow(QMainWindow):
    """FFmpeg 视频工具箱主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFmpeg 视频工具箱")
        self.resize(1200, 820)
        self.setMinimumSize(1000, 680)
        self.setAcceptDrops(True)

        central_widget = QWidget()
        central_widget.setAcceptDrops(True)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 6)

        # 核心选项卡面板
        self.tab_widget = QTabWidget()
        
        self.tab_compress = TabCompress()
        self.tab_cutter = TabCutter()
        self.tab_split = TabSplit()
        self.tab_merge = TabMerge()
        self.tab_settings = TabSettings()

        self.tab_widget.addTab(self.tab_compress, "批量压制")
        self.tab_widget.addTab(self.tab_cutter, "视频裁剪")
        self.tab_widget.addTab(self.tab_split, "视频分段")
        self.tab_widget.addTab(self.tab_merge, "视频合并")
        self.tab_widget.addTab(self.tab_settings, "环境诊断")

        main_layout.addWidget(self.tab_widget)
        self.setCentralWidget(central_widget)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # 状态标签
        self._setup_status_bar()

    def _setup_status_bar(self):
        ffmpeg_ok = tool_mgr.is_available("ffmpeg")
        exif_ok = tool_mgr.is_available("exiftool")
        best_enc = HardwareDetector.get_best_hevc_encoder()

        status_text = (
            f"FFmpeg: {'已就绪' if ffmpeg_ok else '未找到'}  |  "
            f"ExifTool: {'已就绪' if exif_ok else '未找到'}  |  "
            f"推荐编码器: {best_enc}"
        )
        lbl_info = QLabel(status_text)
        lbl_info.setStyleSheet("padding-left: 10px; color: #abb2bf; font-size: 12px;")
        self.status_bar.addWidget(lbl_info)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        if not paths:
            return

        cur_idx = self.tab_widget.currentIndex()
        if cur_idx == 0:
            self.tab_compress._handle_dropped_paths(paths)
        elif cur_idx == 1:
            self.tab_cutter.load_video(paths[0])
        elif cur_idx == 2:
            self.tab_split._handle_dropped_paths(paths)
        elif cur_idx == 3:
            self.tab_merge._handle_dropped_paths(paths)

    def closeEvent(self, event):
        # 确保关闭窗口时停止播放器与后台诊断/合并线程
        if hasattr(self.tab_cutter, "player_widget"):
            self.tab_cutter.player_widget.close()
        if hasattr(self.tab_settings, "_worker") and self.tab_settings._worker and self.tab_settings._worker.isRunning():
            self.tab_settings._worker.wait(1000)
        if hasattr(self.tab_merge, "worker") and self.tab_merge.worker and self.tab_merge.worker.isRunning():
            self.tab_merge.worker.cancel()
            self.tab_merge.worker.wait(1000)
        event.accept()
