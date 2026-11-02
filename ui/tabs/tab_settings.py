from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QColor
from core.tool_manager import tool_mgr
from core.hardware import HardwareDetector

class DiagnosticsWorker(QThread):
    """后台异步诊断线程，绝不阻塞 UI 主线程"""
    diagnostics_ready = Signal(dict, dict, str)

    def __init__(self, force_refresh: bool = False, parent=None):
        super().__init__(parent)
        self.force_refresh = force_refresh

    def run(self):
        # 1. 异步查询工具版本 (内部使用 CREATE_NO_WINDOW)
        tools = tool_mgr.get_status_dict()

        # 2. 异步检测硬件编码支持 (内部使用 CREATE_NO_WINDOW)
        hw_support = HardwareDetector.detect_encoders(force_refresh=self.force_refresh)
        best = HardwareDetector.get_best_hevc_encoder()

        self.diagnostics_ready.emit(tools, hw_support, best)

class TabSettings(QWidget):
    """选项卡 4：工具检测、硬件加速诊断与运行日志中心 (100% 异步零冻结)"""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 1. 工具与依赖状态
        group_tools = QGroupBox("外部依赖工具就绪状态 (优先读取程序所在目录)")
        tools_layout = QVBoxLayout(group_tools)
        
        self.table_tools = QTableWidget(0, 4)
        self.table_tools.setHorizontalHeaderLabels(["工具名称", "状态", "版本信息", "程序所在绝对路径"])
        self.table_tools.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_tools.setFixedHeight(160)
        tools_layout.addWidget(self.table_tools)
        layout.addWidget(group_tools)

        # 2. 硬件加速检测结果
        group_hw = QGroupBox("显卡硬件加速 (NVENC / QSV / AMF) 诊断")
        hw_layout = QVBoxLayout(group_hw)
        self.lbl_hw_desc = QLabel("⚡ 正在诊断当前显卡驱动与硬件编码支持情况...")
        self.lbl_hw_desc.setStyleSheet("font-family: Consolas; line-height: 1.5; color: #abb2bf;")
        hw_layout.addWidget(self.lbl_hw_desc)

        hw_btn_bar = QHBoxLayout()
        self.btn_recheck = QPushButton("🔄 重新深度诊断")
        self.btn_recheck.setFixedHeight(28)
        self.btn_recheck.clicked.connect(self._run_force_refresh)
        hw_btn_bar.addStretch()
        hw_btn_bar.addWidget(self.btn_recheck)
        hw_layout.addLayout(hw_btn_bar)

        layout.addWidget(group_hw)

        # 3. 运行日志面板
        group_log = QGroupBox("运行日志输出 (实时捕获 FFmpeg / ExifTool 终端流)")
        log_layout = QVBoxLayout(group_log)
        
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        log_btn_bar = QHBoxLayout()
        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.clicked.connect(self.log_text.clear)
        log_btn_bar.addStretch()
        log_btn_bar.addWidget(btn_clear_log)
        log_layout.addLayout(log_btn_bar)

        layout.addWidget(group_log, stretch=1)

        self._worker = None
        self._diagnostics_started = False

        # 初始微秒级快速填充表格 (根据本地可执行文件存在性快速打底，0ms 零阻塞)
        self._populate_fast_initial_table()

    def _populate_fast_initial_table(self):
        """利用已有路径瞬间填充骨架数据，界面点击即开，无任何假死"""
        tool_names = ["ffmpeg", "ffprobe", "ffplay", "exiftool"]
        self.table_tools.setRowCount(len(tool_names))
        for row, name in enumerate(tool_names):
            path = tool_mgr.get_path(name)
            is_ok = tool_mgr.is_available(name)
            
            self.table_tools.setItem(row, 0, QTableWidgetItem(name))
            
            status_item = QTableWidgetItem("✅ 已就绪" if is_ok else "❌ 未找到")
            status_item.setForeground(QColor("#98c379") if is_ok else QColor("#e06c75"))
            self.table_tools.setItem(row, 1, status_item)

            # 版本信息先显示读取中，随后由后台线程异步填补
            self.table_tools.setItem(row, 2, QTableWidgetItem("⏳ 检测中..."))
            self.table_tools.setItem(row, 3, QTableWidgetItem(path or "未在目录或 PATH 中找到"))

    def showEvent(self, event):
        super().showEvent(event)
        if not self._diagnostics_started:
            self._start_diagnostics_thread(force=False)
            self._diagnostics_started = True

    def _start_diagnostics_thread(self, force: bool = False):
        if self._worker and self._worker.isRunning():
            return
        self.btn_recheck.setEnabled(False)
        self.btn_recheck.setText("⏳ 正在诊断中...")
        self._worker = DiagnosticsWorker(force_refresh=force, parent=self)
        self._worker.diagnostics_ready.connect(self._on_diagnostics_ready)
        self._worker.start()

    def _run_force_refresh(self):
        self._start_diagnostics_thread(force=True)

    def _on_diagnostics_ready(self, tools: dict, hw_support: dict, best: str):
        # 刷新工具表格中的真实版本号
        for row, (name, info) in enumerate(tools.items()):
            self.table_tools.setItem(row, 0, QTableWidgetItem(name))
            is_ok = info["available"]
            status_item = QTableWidgetItem("✅ 已就绪" if is_ok else "❌ 未找到")
            status_item.setForeground(QColor("#98c379") if is_ok else QColor("#e06c75"))
            self.table_tools.setItem(row, 1, status_item)

            self.table_tools.setItem(row, 2, QTableWidgetItem(info.get("version", "已就绪")))
            self.table_tools.setItem(row, 3, QTableWidgetItem(info.get("path", "")))

        # 刷新硬件加速文本
        lines = [f"🏆 推荐 HEVC 编码器: 【{best}】", "--------------------------------------"]
        for enc, data in hw_support.items():
            status = "✅ 支持并可用" if data.get("supported") else "❌ 不支持 / 未检测到对应硬件"
            lines.append(f"• {data.get('desc', enc):<35} : {status}")
        
        self.lbl_hw_desc.setText("\n".join(lines))
        self.btn_recheck.setEnabled(True)
        self.btn_recheck.setText("🔄 重新深度诊断")

    def append_log(self, text: str):
        self.log_text.appendPlainText(text)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.wait(1000)
        super().closeEvent(event)

