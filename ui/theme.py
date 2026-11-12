"""
FFmpeg 视频工具箱 - 优雅浅色界面设计规范 (Light Elegant Theme)
字体规范：思源黑体回退微软雅黑与无衬线系统字体
色彩规范：Tailwind Slate 现代灰阶 + 经典科技蓝作为主强调色
"""

LIGHT_THEME_QSS = """
/* 全局基础设置与字体栈规范 (思源黑体优先，回退微软雅黑) */
QWidget {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
    selection-background-color: #dbeafe;
    selection-color: #1d4ed8;
}

/* 主窗口背景 */
QMainWindow {
    background-color: #f8fafc;
}

/* 顶部标签页 QTabWidget */
QTabWidget::pane {
    border: 1px solid #e2e8f0;
    background-color: #ffffff;
    border-radius: 8px;
    margin-top: -1px;
}

QTabBar {
    background: transparent;
    qproperty-drawBase: 0;
}

QTabBar::tab {
    background: #f1f5f9;
    color: #64748b;
    padding: 8px 22px;
    font-weight: 600;
    font-size: 13px;
    border: 1px solid #e2e8f0;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
}

QTabBar::tab:hover {
    color: #0f172a;
    background: #e2e8f0;
}

QTabBar::tab:selected {
    color: #2563eb;
    background: #ffffff;
    border-top: 2px solid #2563eb;
    border-left: 1px solid #e2e8f0;
    border-right: 1px solid #e2e8f0;
    border-bottom: 1px solid #ffffff;
}

/* 分组面板 QGroupBox */
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
    padding-bottom: 10px;
    padding-left: 10px;
    padding-right: 10px;
    font-weight: 600;
    color: #0f172a;
    font-size: 13px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: #ffffff;
    color: #1e293b;
    font-weight: 600;
    font-size: 13px;
}

/* 按钮基础样式 */
QPushButton {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    color: #1e293b;
    padding: 6px 14px;
    border-radius: 6px;
    font-weight: 500;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #f8fafc;
    border-color: #94a3b8;
    color: #0f172a;
}

QPushButton:pressed {
    background-color: #f1f5f9;
    border-color: #64748b;
}

QPushButton:disabled {
    background-color: #f8fafc;
    border-color: #e2e8f0;
    color: #94a3b8;
}

/* 主要操作按钮 (强调蓝主操作) */
QPushButton#primaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
    border: 1px solid #1d4ed8;
    font-weight: 600;
    color: #ffffff;
    border-radius: 6px;
}

QPushButton#primaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #60a5fa, stop:1 #3b82f6);
    border-color: #2563eb;
}

QPushButton#primaryBtn:pressed {
    background-color: #1e40af;
    border-color: #1e40af;
}

QPushButton#primaryBtn:disabled {
    background-color: #93c5fd;
    border-color: #93c5fd;
    color: #ffffff;
}

/* 危险/取消按钮 */
QPushButton#dangerBtn {
    background-color: #fef2f2;
    border: 1px solid #fecaca;
    color: #dc2626;
    font-weight: 600;
    border-radius: 6px;
}

QPushButton#dangerBtn:hover {
    background-color: #fee2e2;
    border-color: #f87171;
    color: #b91c1c;
}

QPushButton#dangerBtn:pressed {
    background-color: #fecaca;
    border-color: #ef4444;
}

QPushButton#dangerBtn:disabled {
    background-color: #f8fafc;
    border-color: #e2e8f0;
    color: #94a3b8;
}

/* 输入框、下拉选择框与微调框 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 5px 10px;
    color: #0f172a;
    font-size: 13px;
    min-height: 22px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #2563eb;
    background-color: #ffffff;
}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background-color: #f8fafc;
    border-color: #e2e8f0;
    color: #94a3b8;
}

/* 下拉菜单 QComboBox 详尽适配 (彻底杜绝文字裁切问题) */
QComboBox {
    padding-right: 26px;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #e2e8f0;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background: #f8fafc;
}

QComboBox::drop-down:hover {
    background: #f1f5f9;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #64748b;
    width: 0;
    height: 0;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    color: #0f172a;
    selection-background-color: #eff6ff;
    selection-color: #1d4ed8;
    padding: 4px;
    outline: none;
}

/* 表格控件 QTableWidget */
QTableWidget {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    gridline-color: #f1f5f9;
    color: #1e293b;
    font-size: 13px;
    outline: none;
}

QTableCornerButton::section {
    background-color: #f8fafc;
    border: none;
    border-right: 1px solid #e2e8f0;
    border-bottom: 1px solid #e2e8f0;
}

QHeaderView::section {
    background-color: #f8fafc;
    color: #475569;
    padding: 8px 10px;
    border: none;
    border-right: 1px solid #e2e8f0;
    border-bottom: 1px solid #e2e8f0;
    font-weight: 600;
    font-size: 12px;
}

QTableWidget::item {
    padding: 6px 10px;
    border-bottom: 1px solid #f1f5f9;
    color: #1e293b;
}

QTableWidget::item:hover {
    background-color: #f8fafc;
}

QTableWidget::item:selected {
    background-color: #eff6ff;
    color: #1d4ed8;
    font-weight: 500;
}

/* 进度条 QProgressBar */
QProgressBar {
    background-color: #e2e8f0;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #1e293b;
    font-weight: 600;
    font-size: 11px;
    height: 14px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
    border-radius: 4px;
}

/* 日志框 QPlainTextEdit */
QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    color: #1e293b;
    padding: 8px;
}

/* 滑块 QSlider */
QSlider::groove:horizontal {
    border: none;
    height: 4px;
    background: #e2e8f0;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: #2563eb;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #2563eb;
    width: 14px;
    height: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background: #eff6ff;
    border-color: #1d4ed8;
    width: 16px;
    height: 16px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 8px;
}

/* 滚动条 QScrollBar */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: transparent;
    height: 8px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #cbd5e1;
    min-width: 24px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* 状态栏 QStatusBar */
QStatusBar {
    background-color: #f8fafc;
    border-top: 1px solid #e2e8f0;
    color: #64748b;
    font-size: 12px;
}

/* 菜单 QMenu */
QMenu {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 4px;
    color: #0f172a;
}

QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #eff6ff;
    color: #1d4ed8;
}

QMenu::separator {
    height: 1px;
    background-color: #f1f5f9;
    margin: 4px 6px;
}

/* 提示气泡 Tooltip */
QToolTip {
    background-color: #1e293b;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}

/* 复选框 QCheckBox */
QCheckBox {
    spacing: 8px;
    color: #0f172a;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    background-color: #ffffff;
}

QCheckBox::indicator:hover {
    border-color: #2563eb;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border-color: #2563eb;
    image: none;
}
"""

# 保留深色备用
DARK_THEME_QSS = LIGHT_THEME_QSS
