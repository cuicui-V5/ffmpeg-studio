DARK_THEME_QSS = """
/* 全局基础设置 */
QWidget {
    background-color: #18191c;
    color: #e4e6eb;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    selection-background-color: #007acc;
    selection-color: #ffffff;
}

/* 顶部标签页 QTabWidget */
QTabWidget::pane {
    border: 1px solid #2d3139;
    background-color: #1e2025;
    border-radius: 6px;
    margin-top: -1px;
}

QTabBar::tab {
    background: #18191c;
    color: #9ba1a6;
    padding: 10px 24px;
    font-weight: bold;
    font-size: 14px;
    border: 1px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
}

QTabBar::tab:hover {
    color: #ffffff;
    background: #252830;
}

QTabBar::tab:selected {
    color: #00d2ff;
    background: #1e2025;
    border-top: 2px solid #00d2ff;
    border-left: 1px solid #2d3139;
    border-right: 1px solid #2d3139;
    border-bottom: 1px solid #1e2025;
}

/* 按钮样式 */
QPushButton {
    background-color: #2c313a;
    border: 1px solid #3e4451;
    color: #ffffff;
    padding: 7px 16px;
    border-radius: 5px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #353b45;
    border-color: #4b5263;
}

QPushButton:pressed {
    background-color: #21252b;
}

QPushButton:disabled {
    background-color: #1e2024;
    border-color: #2c3138;
    color: #5c6370;
}

/* 主要操作按钮 (强调色) */
QPushButton#primaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007acc, stop:1 #00b4d8);
    border: none;
    font-weight: bold;
    color: #ffffff;
}

QPushButton#primaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0098ff, stop:1 #00c6ee);
}

QPushButton#dangerBtn {
    background-color: #e06c75;
    border: none;
    color: #ffffff;
}

QPushButton#dangerBtn:hover {
    background-color: #e8838b;
}

/* 输入框与微调框 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #21252b;
    border: 1px solid #3e4451;
    border-radius: 5px;
    padding: 6px 10px;
    color: #abb2bf;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #00d2ff;
    color: #ffffff;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 25px;
    border-left: 1px solid #3e4451;
}

QComboBox QAbstractItemView {
    background-color: #21252b;
    border: 1px solid #3e4451;
    color: #abb2bf;
    selection-background-color: #007acc;
}

/* 表格控件 QTableWidget */
QTableWidget {
    background-color: #1e2025;
    border: 1px solid #2d3139;
    border-radius: 6px;
    gridline-color: #2b2e37;
}

QHeaderView::section {
    background-color: #252830;
    color: #9ba1a6;
    padding: 8px;
    border: none;
    border-right: 1px solid #2d3139;
    border-bottom: 1px solid #2d3139;
    font-weight: bold;
}

QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #262932;
}

QTableWidget::item:selected {
    background-color: #2d3342;
    color: #00d2ff;
}

/* 进度条 QProgressBar */
QProgressBar {
    background-color: #21252b;
    border: 1px solid #3e4451;
    border-radius: 5px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    height: 18px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007acc, stop:1 #00e5ff);
    border-radius: 4px;
}

/* 日志框 QPlainTextEdit */
QPlainTextEdit {
    background-color: #121316;
    border: 1px solid #2d3139;
    border-radius: 5px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    color: #98c379;
}

/* 滑块 QSlider */
QSlider::groove:horizontal {
    border: 1px solid #3e4451;
    height: 6px;
    background: #21252b;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #00d2ff;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #007acc;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background: #00d2ff;
    border-color: #ffffff;
}

/* 滚动条 QScrollBar */
QScrollBar:vertical {
    border: none;
    background: #18191c;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #3e4451;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #5c6370;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
