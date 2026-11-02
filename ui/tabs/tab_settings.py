from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PySide6.QtGui import QColor
from core.tool_manager import tool_mgr
from core.hardware import HardwareDetector

class TabSettings(QWidget):
    """选项卡 4：工具检测、硬件加速诊断与运行日志中心"""

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
        self.lbl_hw_desc = QLabel("正在诊断当前显卡驱动支持情况...")
        self.lbl_hw_desc.setStyleSheet("font-family: Consolas; line-height: 1.5;")
        hw_layout.addWidget(self.lbl_hw_desc)
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

        self._refresh_status()

    def _refresh_status(self):
        # 刷新工具表格
        tools = tool_mgr.get_status_dict()
        self.table_tools.setRowCount(len(tools))
        
        for row, (name, info) in enumerate(tools.items()):
            self.table_tools.setItem(row, 0, QTableWidgetItem(name))
            
            is_ok = info["available"]
            status_item = QTableWidgetItem("✅ 已就绪" if is_ok else "❌ 未找到")
            status_item.setForeground(QColor("#98c379") if is_ok else QColor("#e06c75"))
            self.table_tools.setItem(row, 1, status_item)

            self.table_tools.setItem(row, 2, QTableWidgetItem(info["version"]))
            self.table_tools.setItem(row, 3, QTableWidgetItem(info["path"]))

        # 刷新硬件加速
        hw_support = HardwareDetector.detect_encoders()
        best = HardwareDetector.get_best_hevc_encoder()
        
        lines = [f"🏆 推荐 HEVC 编码器: 【{best}】", "--------------------------------------"]
        for enc, data in hw_support.items():
            status = "✅ 支持并可用" if data.get("supported") else "❌ 不支持 / 未检测到对应硬件"
            lines.append(f"• {data.get('desc', enc):<35} : {status}")
        
        self.lbl_hw_desc.setText("\n".join(lines))

    def append_log(self, text: str):
        self.log_text.appendPlainText(text)
