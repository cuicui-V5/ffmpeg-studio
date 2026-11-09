from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel, QWidget, QVBoxLayout
)
from PySide6.QtCore import Qt, QTimer
from ui.tabs.tab_compress import TabCompress
from core.tool_manager import tool_mgr
from core.hardware import HardwareDetector

class MainWindow(QMainWindow):
    """FFmpeg 视频工具箱主窗口 (支持首屏秒开与选项卡后台异步就绪架构)"""

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
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Tab 0: 批量压制 (首屏立即渲染，用户双击即见)
        self.tab_compress = TabCompress()
        self.tab_widget.addTab(self.tab_compress, "批量压制")

        # Tabs 1..4: 惰性轻量占位 (避免启动时无意义阻塞几百毫秒构建未展示视图)
        self.tab_cutter = None
        self.tab_split = None
        self.tab_merge = None
        self.tab_settings = None

        self._placeholder_cutter = QWidget()
        self._placeholder_split = QWidget()
        self._placeholder_merge = QWidget()
        self._placeholder_settings = QWidget()

        self.tab_widget.addTab(self._placeholder_cutter, "视频裁剪")
        self.tab_widget.addTab(self._placeholder_split, "视频分段")
        self.tab_widget.addTab(self._placeholder_merge, "视频合并")
        self.tab_widget.addTab(self._placeholder_settings, "环境诊断")

        main_layout.addWidget(self.tab_widget)
        self.setCentralWidget(central_widget)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._setup_status_bar()

        # 后台空闲队列静默预载队列：主窗口呈现后，空闲时按序预加载剩余 4 个选项卡
        self._preload_queue = [1, 2, 3, 4]
        QTimer.singleShot(80, self._step_preload_tabs)

    def _ensure_tab_loaded(self, index: int):
        """按需瞬时或后台预装载指定选项卡"""
        if index == 1 and self.tab_cutter is None:
            from ui.tabs.tab_cutter import TabCutter
            self.tab_cutter = TabCutter()
            cur_idx = self.tab_widget.currentIndex()
            self.tab_widget.removeTab(1)
            self.tab_widget.insertTab(1, self.tab_cutter, "视频裁剪")
            if cur_idx == 1:
                self.tab_widget.setCurrentIndex(1)

        elif index == 2 and self.tab_split is None:
            from ui.tabs.tab_split import TabSplit
            self.tab_split = TabSplit()
            cur_idx = self.tab_widget.currentIndex()
            self.tab_widget.removeTab(2)
            self.tab_widget.insertTab(2, self.tab_split, "视频分段")
            if cur_idx == 2:
                self.tab_widget.setCurrentIndex(2)

        elif index == 3 and self.tab_merge is None:
            from ui.tabs.tab_merge import TabMerge
            self.tab_merge = TabMerge()
            cur_idx = self.tab_widget.currentIndex()
            self.tab_widget.removeTab(3)
            self.tab_widget.insertTab(3, self.tab_merge, "视频合并")
            if cur_idx == 3:
                self.tab_widget.setCurrentIndex(3)

        elif index == 4 and self.tab_settings is None:
            from ui.tabs.tab_settings import TabSettings
            self.tab_settings = TabSettings()
            cur_idx = self.tab_widget.currentIndex()
            self.tab_widget.removeTab(4)
            self.tab_widget.insertTab(4, self.tab_settings, "环境诊断")
            if cur_idx == 4:
                self.tab_widget.setCurrentIndex(4)

    def _on_tab_changed(self, index: int):
        self._ensure_tab_loaded(index)

    def _step_preload_tabs(self):
        """后台空闲步进预载队列"""
        if self._preload_queue:
            next_tab_idx = self._preload_queue.pop(0)
            self._ensure_tab_loaded(next_tab_idx)
            if self._preload_queue:
                QTimer.singleShot(60, self._step_preload_tabs)

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
        self._ensure_tab_loaded(cur_idx)

        if cur_idx == 0:
            self.tab_compress._handle_dropped_paths(paths)
        elif cur_idx == 1 and self.tab_cutter:
            self.tab_cutter.load_video(paths[0])
        elif cur_idx == 2 and self.tab_split:
            self.tab_split._handle_dropped_paths(paths)
        elif cur_idx == 3 and self.tab_merge:
            self.tab_merge._handle_dropped_paths(paths)

    def closeEvent(self, event):
        # 确保关闭窗口时停止播放器与后台诊断/合并线程
        if self.tab_cutter and hasattr(self.tab_cutter, "player_widget"):
            self.tab_cutter.player_widget.close()
        if self.tab_settings and hasattr(self.tab_settings, "_worker") and self.tab_settings._worker and self.tab_settings._worker.isRunning():
            self.tab_settings._worker.wait(1000)
        if self.tab_merge and hasattr(self.tab_merge, "worker") and self.tab_merge.worker and self.tab_merge.worker.isRunning():
            self.tab_merge.worker.cancel()
            self.tab_merge.worker.wait(1000)
        event.accept()
