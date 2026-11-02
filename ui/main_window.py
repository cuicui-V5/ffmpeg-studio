from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel, QWidget, QVBoxLayout
)
from PySide6.QtCore import Qt
from ui.tabs.tab_compress import TabCompress
from ui.tabs.tab_cutter import TabCutter
from ui.tabs.tab_split import TabSplit
from ui.tabs.tab_settings import TabSettings
from core.tool_manager import tool_mgr
from core.hardware import HardwareDetector

class MainWindow(QMainWindow):
    """FFmpeg 智能音视频多功能桌面工具箱主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFmpeg Multi-Tool Studio — 智能音视频工作台")
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
        self.tab_settings = TabSettings()

        self.tab_widget.addTab(self.tab_compress, "🎬 批量压制 1080p (元数据保护)")
        self.tab_widget.addTab(self.tab_cutter, "✂️ 极速裁切 (内嵌预览·对齐关键帧)")
        self.tab_widget.addTab(self.tab_split, "📦 平台智能分段 (QQ/微信/社交限制)")
        self.tab_widget.addTab(self.tab_settings, "⚙️ 工具与硬件加速诊断")

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
            f"FFmpeg: {'🟢 就绪' if ffmpeg_ok else '🔴 未找到'}  |  "
            f"ExifTool: {'🟢 就绪' if exif_ok else '🔴 未找到'}  |  "
            f"硬件加速推荐: ⚡ {best_enc}"
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

    def closeEvent(self, event):
        # 确保关闭窗口时停止播放器
        if hasattr(self.tab_cutter, "player_widget"):
            self.tab_cutter.player_widget.close()
        event.accept()
