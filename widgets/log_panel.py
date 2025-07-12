# app/widgets/log_panel.py
import logging
from collections import deque
from typing import List, Tuple

from PySide6.QtWidgets import (
    QTextEdit, QDockWidget, QVBoxLayout, QWidget,
    QComboBox, QHBoxLayout, QLabel, QSizePolicy, QStyle, QPushButton   
)
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtCore import Signal, Slot, Qt, QObject

from syntax.styles import SyntaxStyleDark


class QtLogHandler(QObject, logging.Handler):
    """
    Handler → GUI. Теперь отправляем: msg, levelno, logger_name
    """
    log_received = Signal(str, int, str)   # message, level, logger_name

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s '
                '- [%(filename)s:%(lineno)d] - %(message)s'
            )
        )

    def emit(self, record: logging.LogRecord):
        try:
            # --- КОРОТКИЙ ФОРМАТ ДЛЯ dsl_script ---
            if record.name == "dsl_script":
                msg = record.getMessage()    
            else:
                msg = self.format(record)
            # ---------------------------------------
            self.log_received.emit(msg, record.levelno, record.name)
        except Exception:
            self.handleError(record)


class LogPanel(QDockWidget):
    """
    Панель логов с фильтрами по уровню и имени логгера
    """
    MAX_LOG_LINES = 2_000
    _LEVELS = [
        ("Debug",   logging.DEBUG),
        ("Info",    logging.INFO),
        ("Warning", logging.WARNING),
        ("Error",   logging.ERROR),
    ]
    ALL_LOGGERS_SENTINEL = "<Все>"

    # ---------------------------------------
    #               init
    # ---------------------------------------
    def __init__(self, title: str = "Логи", parent=None):
        super().__init__(title, parent)
        self.setObjectName("LogPanelDock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea
        )

        # ---------- state ----------
        self._current_level_filter: int = logging.DEBUG
        self._current_logger_filter: str = self.ALL_LOGGERS_SENTINEL
        self._error_cnt: int = 0
        self._warn_cnt: int = 0
        self._buffer: deque[Tuple[str, int, str]] = deque(maxlen=10_000)  # (msg, lvl, logger)

        # ---------- UI ----------
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(4, 4, 4, 4)

        # --- level combobox ---
        self.level_box = QComboBox()
        self.level_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for name, _lvl in self._LEVELS:
            self.level_box.addItem(name)
        self.level_box.currentIndexChanged.connect(self._on_level_changed)

        # --- logger combobox ---
        self.logger_box = QComboBox()
        self.logger_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.logger_box.addItem(self.ALL_LOGGERS_SENTINEL)
        self.logger_box.currentIndexChanged.connect(self._on_logger_changed)

        # (2) кнопка очистки -------------------------
        clear_btn = QPushButton()
        clear_icon = self.style().standardIcon(QStyle.SP_TrashIcon)
        clear_btn.setIcon(clear_icon)
        clear_btn.setToolTip("Очистить логи")
        clear_btn.clicked.connect(self._clear_logs)

        # --- counters ---
        warn_icon: QIcon = self.style().standardIcon(QStyle.SP_MessageBoxWarning)
        err_icon:  QIcon = self.style().standardIcon(QStyle.SP_MessageBoxCritical)

        self.warn_lbl = QLabel()
        self.warn_lbl.setPixmap(warn_icon.pixmap(16, 16))
        self.warn_cnt_lbl = QLabel("0")

        self.err_lbl = QLabel()
        self.err_lbl.setPixmap(err_icon.pixmap(16, 16))
        self.err_cnt_lbl = QLabel("0")

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        top.addWidget(QLabel("Уровень:"))
        top.addWidget(self.level_box)
        top.addSpacing(10)
        top.addWidget(QLabel("Логгер:"))
        top.addWidget(self.logger_box)
        top.addWidget(spacer)
        top.addWidget(clear_btn)
        top.addWidget(self.warn_lbl)
        top.addWidget(self.warn_cnt_lbl)
        top.addSpacing(8)
        top.addWidget(self.err_lbl)
        top.addWidget(self.err_cnt_lbl)

        # --- text area ---
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 9))
        self.text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {SyntaxStyleDark.TextEditBackground.name()};
                color: {SyntaxStyleDark.DefaultText.name()};
                border: 1px solid #3E4451;
            }}
        """)

        outer.addLayout(top)
        outer.addWidget(self.text)
        self.setWidget(central)

        # ---------- handler ----------
        self._qt_handler = QtLogHandler()
        self._qt_handler.log_received.connect(self._on_log)

    # ---------------------------------------------------------------- filters
    @Slot(int)
    def _on_level_changed(self, idx: int):
        _, self._current_level_filter = self._LEVELS[idx]
        self._repaint()

    @Slot(int)
    def _on_logger_changed(self, _idx: int):
        self._current_logger_filter = self.logger_box.currentText()
        self._repaint()

    # ---------------------------------------------------------------- receive
    @Slot(str, int, str)
    def _on_log(self, msg: str, lvl: int, logger_name: str):
        # записываем в буфер
        self._buffer.append((msg, lvl, logger_name))

        # counters
        if lvl >= logging.ERROR:
            self._error_cnt += 1
            self.err_cnt_lbl.setText(str(self._error_cnt))
        elif lvl >= logging.WARNING:
            self._warn_cnt += 1
            self.warn_cnt_lbl.setText(str(self._warn_cnt))

        # dynamic logger list
        if logger_name not in self._iter_logger_items():
            self.logger_box.addItem(logger_name)

        # соответствуем ли фильтрам?
        if self._passes_filters(lvl, logger_name):
            self._append_line(msg, lvl)

    @Slot()
    def _clear_logs(self):
        """Полностью очищает журнал"""
        self.text.clear()
        self._buffer.clear()
        self._error_cnt = 0
        self._warn_cnt = 0
        self.err_cnt_lbl.setText("0")
        self.warn_cnt_lbl.setText("0")

    # ---------------------------------------------------------------- helpers
    def _iter_logger_items(self):
        return [self.logger_box.itemText(i) for i in range(self.logger_box.count())]

    def _passes_filters(self, level: int, logger_name: str) -> bool:
        by_level = level >= self._current_level_filter
        by_logger = (
            self._current_logger_filter == self.ALL_LOGGERS_SENTINEL or
            logger_name == self._current_logger_filter
        )
        return by_level and by_logger

    def _append_line(self, msg: str, lvl: int):
        # limit
        if self.text.document().blockCount() > self.MAX_LOG_LINES:
            cursor = self.text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deletePreviousChar()

        color = SyntaxStyleDark.DefaultText
        if lvl >= logging.ERROR:
            color = QColor("red")
        elif lvl >= logging.WARNING:
            color = QColor("orange")
        elif lvl == logging.INFO:
            color = QColor("#61AFEF")

        self.text.moveCursor(self.text.textCursor().MoveOperation.End)
        self.text.setTextColor(color)
        self.text.insertPlainText(msg + "\n")
        self.text.setTextColor(SyntaxStyleDark.DefaultText)

        # autoscroll
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    def _repaint(self):
        self.text.clear()
        to_show: List[Tuple[str, int, str]] = [
            t for t in self._buffer if self._passes_filters(t[1], t[2])
        ][-self.MAX_LOG_LINES:]

        for msg, lvl, _ in to_show:
            self._append_line(msg, lvl)

    # ------------------------------------------------ API
    def get_handler(self) -> QtLogHandler:
        return self._qt_handler
