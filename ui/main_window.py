import os, logging, re
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QLabel, QMessageBox, QStackedWidget, QPushButton,
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPlainTextEdit,
)
from PySide6.QtCore import Qt, QSettings, QItemSelectionModel, QTimer
from PySide6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor

# ---------- локальные блоки ----------
from ui.tree_panel          import FileTreePanel
from ui.tab_manager         import TabManager
from ui.dsl_variables_dock  import DslVariablesDock
from widgets.log_panel import LogPanel
from widgets.info_editor_widget import InfoEditorDock
from widgets.template_panel_widget import TemplatePanelDock

# ---------- утилиты / константы -------
from config import PROMPTS_DIR_NAME, SETTINGS_ORG_NAME, SETTINGS_APP_NAME
from utils.path_helpers import find_or_ask_prompts_root, select_prompts_directory_dialog
from utils.logger       import add_editor_log_handler, get_dsl_execution_logger, editor_logger, get_dsl_script_logger
from dsl_manager        import DSL_ENGINE_AVAILABLE, CharacterClass
from widgets.dsl_result_dialog import DslResultDialog
from widgets.post_dsl_test_dialog import PostDslTestDialog

# ---------- модели персонажей ----------
from models.character import Character
from models.characters import (
    CrazyMita, KindMita, ShortHairMita,
    CappyMita, MilaMita, CreepyMita, SleepyMita
)

_log = logging.getLogger(__name__)


class FileTextView(QWidget):
    """Текстовый вид для файлов при drill-down навигации."""

    def __init__(self, path: str, tag: str = "", parent=None):
        super().__init__(parent)
        self._path = path
        self._modified = False

        from ui.node_graph.preview_highlighter import SimplePromptHighlighter

        self._edit = QPlainTextEdit()
        self._edit.setFont(QFont("Consolas", 10))
        self._edit.setStyleSheet("background:#1f2329;color:#e6edf3;")
        SimplePromptHighlighter(self._edit.document())
        self._edit.textChanged.connect(lambda: setattr(self, "_modified", True))

        btn_save = QPushButton("💾 Сохранить")
        btn_save.setFixedHeight(24)
        btn_save.setStyleSheet(
            "QPushButton{background:#21262d;color:#4a9eff;border:1px solid #30363d;"
            "border-radius:3px;padding:1px 10px;font-size:11px;}"
            "QPushButton:hover{background:#1f6feb;color:#fff;}"
        )
        btn_save.clicked.connect(self._save)

        top = QHBoxLayout()
        top.setContentsMargins(4, 4, 4, 2)
        top.addStretch()
        top.addWidget(btn_save)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(top)
        lay.addWidget(self._edit, 1)

        try:
            with open(path, encoding="utf-8") as f:
                self._edit.setPlainText(f.read())
            self._modified = False
        except Exception as e:
            self._edit.setPlainText(f"[Ошибка чтения файла: {e}]")

        if tag:
            self._scroll_to_tag(tag)

    def _scroll_to_tag(self, tag: str):
        text = self._edit.toPlainText()
        pattern = re.compile(r"\[#\s*" + re.escape(tag) + r"\s*\]", re.IGNORECASE)
        m = pattern.search(text)
        if not m:
            return

        # Ищем закрывающий маркер [/TAG]
        end_pat = re.compile(r"\[/\s*" + re.escape(tag) + r"\s*\]", re.IGNORECASE)
        m_end = end_pat.search(text, m.end())
        if m_end:
            hl_end = m_end.end()
        else:
            nl = text.find('\n', m.start())
            hl_end = nl + 1 if nl >= 0 else m.end()

        # Применяем подсветку
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#2a3a2a"))
        cursor = self._edit.textCursor()
        cursor.setPosition(m.start())
        cursor.setPosition(hl_end, QTextCursor.KeepAnchor)
        cursor.mergeCharFormat(fmt)

        # Перемещаем курсор к тегу (без выделения)
        cursor2 = self._edit.textCursor()
        cursor2.setPosition(m.start())
        self._edit.setTextCursor(cursor2)
        self._edit.ensureCursorVisible()

        # Снимаем подсветку через 3 секунды
        QTimer.singleShot(3000, lambda: self._clear_tag_highlight(m.start(), hl_end))

    def _clear_tag_highlight(self, start: int, end: int):
        try:
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("transparent"))
            cursor = self._edit.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.mergeCharFormat(fmt)
        except Exception:
            pass

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(self._edit.toPlainText())
            self._modified = False
            QMessageBox.information(self, "Сохранено", f"Файл сохранён:\n{self._path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить:\n{e}")


_LEGACY_CLASSES = [
    CrazyMita, KindMita, ShortHairMita,
    CappyMita, MilaMita, CreepyMita, SleepyMita
]


class PromptEditorWindow(QMainWindow):
    # -------------------------- helpers --------------------------
    @staticmethod
    def _dict2txt(d: dict) -> str:
        return "\n".join(
            f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in d.items()
        )

    def _char_part(self) -> str | None:
        """Возвращает только имя персонажа (первая часть 'Crazy/DefaultJson' → 'Crazy')."""
        return self.selected_char.split("/")[0] if self.selected_char else None

    def _set_display_name(self) -> str | None:
        """Возвращает имя набора (последняя часть 'Crazy/DefaultJson' → 'DefaultJson')."""
        return self.selected_char.split("/")[-1] if self.selected_char else None

    def _vars_key(self) -> str:
        """Ключ QSettings для хранения переменных текущего набора."""
        return self.selected_char.lower().replace("/", "_") + "_vars" if self.selected_char else ""

    def _defaults_for(self, char_id: str | None) -> dict:
        if not char_id:
            return Character.BASE_DEFAULTS.copy()
        char_part = char_id.split("/")[0]  # только имя персонажа, без набора
        for cls in _LEGACY_CLASSES:
            if cls.__name__.lower().startswith(char_part.lower()):
                merged = Character.BASE_DEFAULTS.copy()
                merged.update(getattr(cls, "DEFAULT_OVERRIDES", {}))
                return merged
        return Character.BASE_DEFAULTS.copy()

    # -------------------------- init -----------------------------
    def __init__(self):
        super().__init__()
        self.resize(1280, 840)
        self.setMinimumSize(960, 600)
        # Заголовок окна установим после определения prompts_root

        self.settings = QSettings(SETTINGS_ORG_NAME, SETTINGS_APP_NAME)
        self.selected_char: str | None = None
        self.prompts_root: str | None = None # Инициализируем prompts_root

        # --- Определяем окончательный prompts_root ---
        # 1. Пытаемся загрузить из настроек
        last_dir_from_settings = self.settings.value("lastPromptsDir")
        if last_dir_from_settings and os.path.isdir(last_dir_from_settings):
            self.prompts_root = str(Path(last_dir_from_settings).resolve())
            editor_logger.info(f"Используется папка Prompts из настроек: {self.prompts_root}")
        else:
            # 2. Если нет в настройках или путь недействителен, пытаемся найти/запросить
            if last_dir_from_settings:
                editor_logger.warning(f"Сохраненный путь Prompts '{last_dir_from_settings}' недействителен.")
            else:
                editor_logger.info("Путь к папке Prompts не найден в настройках.")
            
            editor_logger.info("Попытка автоматического определения папки Prompts или запрос у пользователя.")
            try:
                import config as cfg_mod
                cfg_path = cfg_mod.__file__
            except Exception:
                cfg_path = os.getcwd()
            
            # find_or_ask_prompts_root теперь сохранит в настройки, если найдет автоматически или пользователь выберет
            self.prompts_root = find_or_ask_prompts_root(
                self, self.settings, PROMPTS_DIR_NAME, cfg_path
            )

        self.setWindowTitle(f"Редактор Промптов — {SETTINGS_APP_NAME}") # Устанавливаем базовый заголовок

        # --- Строим UI (FileTreePanel получит уже определенный self.prompts_root) ---
        self._build_ui() 

        # --- Загружаем остальные настройки UI (состояние окна, разделителя) ---
        self._load_window_layout_settings() # Новый метод вместо части старого _load_settings

        # Восстанавливаем последнего персонажа или показываем выбор персонажа
        last_char = self.settings.value("lastChar", "")
        last_opened_file = self.settings.value("lastOpenedFile", "")
        if last_char and self.prompts_root:
            editor_logger.info(f"Восстанавливаем последнего персонажа: {last_char}")
            self._show_editor()
            self._on_char_selected(last_char)
            self._select_char_in_tree(last_char)
            if last_opened_file and os.path.isfile(last_opened_file):
                self.tabs.open_file(last_opened_file)
        else:
            editor_logger.info("Нет последнего персонажа — показываем выбор персонажа.")
            self._stack.setCurrentIndex(0)
        self._update_title()

        if not self.prompts_root:
            QMessageBox.warning(self, "Prompts", "Корневая папка Prompts не выбрана. Функциональность будет ограничена.")
        if not DSL_ENGINE_AVAILABLE:
            QMessageBox.warning(self, "DSL", "DSL-движок недоступен. Функциональность будет ограничена.")

    def _load_window_layout_settings(self): # Новый метод
        if (st := self.settings.value("windowState")): self.restoreState(st)
        if (sp := self.settings.value("splitter")):    self.splitter.restoreState(sp)

    # --------------------- UI construction ----------------------
    def _build_ui(self):
        from ui.character_selector import CharacterSelector
        from ui.global_graph.global_graph_widget import GlobalGraphWidget

        # Внешний QStackedWidget: страница 0 = CharacterSelector, страница 1 = редактор
        self._stack = QStackedWidget(self)
        self.setCentralWidget(self._stack)

        # --- Страница 0: выбор персонажа ---
        self.char_selector = CharacterSelector(self.prompts_root, self)
        self.char_selector.character_chosen.connect(self._on_char_chosen_from_selector)
        self.char_selector.open_folder_requested.connect(self._change_prompts_dir)
        self._stack.addWidget(self.char_selector)       # index 0

        # --- Страница 1: основной редактор ---
        editor_page = QSplitter(Qt.Horizontal)
        self.splitter = editor_page

        # Левая панель: файловое дерево
        self.tree = FileTreePanel(self.prompts_root, lambda: self.tabs.modified_paths(), self)
        editor_page.addWidget(self.tree)

        # Центральный стек: GlobalGraph (0) ↔ TabManager (1)
        self._center_stack = QStackedWidget()

        self.global_graph = GlobalGraphWidget()
        self.global_graph.open_text_requested.connect(self._open_file_in_tabs)
        self.global_graph.open_nodes_requested.connect(self._open_nodes_for_path)
        self.global_graph.open_code_requested.connect(self._open_file_in_tabs)
        self.global_graph.open_postscript_requested.connect(self._open_postscript_rules)
        self._center_stack.addWidget(self.global_graph)   # index 0

        self.tabs = TabManager(lambda: self.prompts_root, self)
        self._center_stack.addWidget(self.tabs)           # index 1

        self._center_stack.setCurrentIndex(0)

        # Обёртка: навбар (кнопка "← Граф") + центральный стек
        center_wrapper = QWidget()
        cw_layout = QVBoxLayout(center_wrapper)
        cw_layout.setContentsMargins(0, 0, 0, 0)
        cw_layout.setSpacing(0)

        self._nav_bar = QFrame()
        self._nav_bar.setFixedHeight(32)
        self._nav_bar.setStyleSheet(
            "QFrame { background: #161b22; border-bottom: 1px solid #30363d; }"
        )
        self._nb_row = QHBoxLayout(self._nav_bar)
        self._nb_row.setContentsMargins(6, 2, 6, 2)
        self._nb_row.setSpacing(6)

        self._btn_nav_graph = QPushButton("🗺 ← Граф")
        self._btn_nav_graph.setFixedHeight(24)
        self._btn_nav_graph.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #4a9eff;
                border: 1px solid #30363d; border-radius: 4px;
                padding: 1px 12px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #1f6feb; color: #ffffff; border-color: #1f6feb; }
        """)
        self._btn_nav_graph.clicked.connect(self._show_graph_view)
        self._nb_row.addWidget(self._btn_nav_graph)

        self._nav_char_lbl = QLabel("")
        self._nav_char_lbl.setStyleSheet("color: #6e7681; font-size: 11px;")
        self._nb_row.addWidget(self._nav_char_lbl)
        self._nb_row.addStretch()

        # Навигационный стек (drill-down в скрипты)
        self._drill_pages: list[tuple] = []   # list of (widget, title, file_path)
        self._crumb_btns: list = []
        self._prompt_sets_view = None

        self._nav_bar.setVisible(False)   # виден только когда открыт текстовый редактор / drill-down
        cw_layout.addWidget(self._nav_bar)
        cw_layout.addWidget(self._center_stack, 1)

        editor_page.addWidget(center_wrapper)
        editor_page.setStretchFactor(1, 1)

        self._stack.addWidget(editor_page)               # index 1
        self._stack.setCurrentIndex(0)

        # Dock-и (общие для обеих страниц)
        self.vars_dock = DslVariablesDock(self); self.addDockWidget(Qt.RightDockWidgetArea, self.vars_dock)
        self.info_dock = InfoEditorDock(self); self.addDockWidget(Qt.RightDockWidgetArea, self.info_dock)
        self.tmpl_dock = TemplatePanelDock(self); self.addDockWidget(Qt.LeftDockWidgetArea, self.tmpl_dock)
        self.log_dock  = LogPanel(parent=self); self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)

        sb = QStatusBar(); self.setStatusBar(sb)
        self.path_lbl = QLabel("Нет открытых файлов"); sb.addPermanentWidget(self.path_lbl)

        # Кнопка "← Персонажи" в статусбаре
        self._btn_back_to_selector = QPushButton("← Персонажи")
        self._btn_back_to_selector.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #8b949e;
                border: 1px solid #30363d; border-radius: 4px;
                padding: 2px 10px; font-size: 11px;
            }
            QPushButton:hover { background: #30363d; color: #e6edf3; }
        """)
        self._btn_back_to_selector.clicked.connect(self._show_selector)
        self._btn_back_to_selector.setVisible(False)
        sb.addWidget(self._btn_back_to_selector)

        self.tree.file_open_requested.connect(self._on_file_open_requested)
        self.tree.character_selected.connect(self._on_char_selected)
        self.tmpl_dock.file_open_requested.connect(self._on_file_open_requested)
        self.tabs.file_saved.connect(self._on_file_saved)
        self.tabs.modified_set_changed.connect(lambda: self.tree.viewport().update())
        self.tabs.currentChanged.connect(self._update_title)
        self.tabs.currentChanged.connect(self._update_postdsl_action_state)
        self.vars_dock.reset_requested.connect(self._reset_vars)
        self.vars_dock.set_on_save_clicked(self._save_config_json_for_current_vars)
        self.vars_dock.editor().textChanged.connect(self._on_vars_text_changed)

        tb = self.addToolBar("DSL")
        # Кнопка "← Граф" для возврата из текстового редактора к графу
        self._act_show_graph = tb.addAction("🗺 Граф", self._show_graph_view)
        self._act_show_graph.setToolTip("Показать граф промпта (структуру main_template)")
        self._act_show_graph.setVisible(False)
        tb.addSeparator()
        self.run_act = tb.addAction("Скомпоновать промпт", self._run_dsl)
        self._update_run_dsl_state()

        title = "Параметры DSL" + (f" — {self.selected_char}" if self.selected_char else "")
        self.vars_dock.setWindowTitle(title)

        self._build_menu()
        self._setup_loggers()

        self._baseline_cfg_dict = None
        self._update_save_button_state()

    def _on_char_chosen_from_selector(self, char_id: str):
        """Пользователь выбрал персонажа на стартовом экране → переходим в редактор."""
        self._show_editor()
        self._on_char_selected(char_id)

    def _show_editor(self):
        """Переключает на страницу редактора."""
        self._stack.setCurrentIndex(1)
        self._btn_back_to_selector.setVisible(True)

    def _show_selector(self):
        """Переключает на стартовый экран."""
        self._stack.setCurrentIndex(0)
        self._btn_back_to_selector.setVisible(False)
        if self.prompts_root:
            self.char_selector.reload(self.prompts_root)
        self.char_selector.set_active_char(self.selected_char)


    def _build_menu(self):
        mb = self.menuBar()

        # -------- Файл --------
        fm = mb.addMenu("&Файл")
        fm.addAction("Выбрать папку Prompts…", self._change_prompts_dir)
        fm.addSeparator()
        fm.addAction("Сохранить",        self.tabs.save_current    ).setShortcut("Ctrl+S")
        fm.addAction("Сохранить как…",   self.tabs.save_current_as ).setShortcut("Ctrl+Shift+S")
        fm.addAction("Сохранить все",    self.tabs.save_all        ).setShortcut("Ctrl+Alt+S")
        fm.addSeparator()
        fm.addAction("Выход", self.close).setShortcut("Ctrl+Q")

        # -------- Инструменты --------
        tm = mb.addMenu("&Инструменты")
        tm.addAction("Проверить синтаксис", self._check_syntax).setShortcut("Ctrl+Shift+C")
        tm.addAction("Визуальный редактор .script (ноды)", self._open_node_editor).setShortcut("Ctrl+Shift+N")
        self._test_postdsl_act = tm.addAction("Тестировать PostDSL…", self._test_postdsl)
        self._test_postdsl_act.setShortcut("Ctrl+Shift+P")
        self._test_postdsl_act.setEnabled(False)

        # -------- Вид --------
        vm = mb.addMenu("&Вид")

        vars_toggle = self.vars_dock.toggleViewAction()
        vars_toggle.setText("Панель переменных DSL")
        vm.addAction(vars_toggle)

        info_toggle = self.info_dock.toggleViewAction()
        info_toggle.setText("Информация о промпте")
        vm.addAction(info_toggle)

        tmpl_toggle = self.tmpl_dock.toggleViewAction()
        tmpl_toggle.setText("Файлы шаблона")
        vm.addAction(tmpl_toggle)

        log_toggle = self.log_dock.toggleViewAction()
        log_toggle.setText("Панель логов")
        vm.addAction(log_toggle)

    # --------------------- tree -> персонаж ---------------------
    def _on_char_selected(self, char_id: str):
        new_char = char_id or None
        char_changed = (new_char != self.selected_char)
        self.selected_char = new_char
        self._sync_vars_panel()
        self._update_run_dsl_state()

        display = self._set_display_name()
        title = "Параметры DSL" + (f" — {display}" if display else "")
        self.vars_dock.setWindowTitle(title)

        # Обновляем панель info.json и файлов шаблона
        self.info_dock.load_for_char(self.prompts_root, self.selected_char)
        self.tmpl_dock.load_for_char(self.prompts_root, self.selected_char)

        if not self.selected_char or not self.prompts_root:
            return

        # Сохраняем последнего персонажа/набор
        if char_id:
            self.settings.setValue("lastChar", char_id)

        # Определяем: CharName или CharName/SetName?
        has_set = "/" in char_id
        if not has_set:
            # Только имя персонажа — показываем экран наборов промтов
            if self._stack.currentIndex() == 1:
                self._show_prompt_sets(char_id)
        elif char_changed:
            # Конкретный набор — загружаем граф шаблона
            self.global_graph.load_character(self.prompts_root, self.selected_char)
            if self._stack.currentIndex() == 1:
                self._show_graph_view()

    def _select_char_in_tree(self, char_id: str):
        """Программно выделяет персонажа/набор в дереве без триггера сигнала."""
        if not self.prompts_root or not char_id:
            return
        path = os.path.join(self.prompts_root, char_id.replace("/", os.sep))
        model = self.tree._model
        idx = model.index(path)
        if idx.isValid():
            self.tree.selectionModel().blockSignals(True)
            self.tree.selectionModel().setCurrentIndex(idx, QItemSelectionModel.ClearAndSelect)
            self.tree.selectionModel().blockSignals(False)

    # ---------- переключение центральных видов ----------

    def _show_graph_view(self):
        """Показывает глобальный граф промпта, удаляя все drill-down страницы."""
        # Убираем все drill-down страницы
        for widget, _title, _path in list(self._drill_pages):
            try:
                self._center_stack.removeWidget(widget)
                widget.deleteLater()
            except Exception:
                pass
        self._drill_pages.clear()
        # Убираем экран наборов если был
        if self._prompt_sets_view is not None:
            try:
                self._center_stack.removeWidget(self._prompt_sets_view)
                self._prompt_sets_view.deleteLater()
            except Exception:
                pass
            self._prompt_sets_view = None
        self._update_breadcrumb()
        self._center_stack.setCurrentIndex(0)
        self._act_show_graph.setVisible(False)
        self._nav_bar.setVisible(False)

    def _show_prompt_sets(self, char_name: str):
        """Показывает экран наборов промтов для персонажа (без конкретного набора)."""
        from ui.prompt_sets_view import PromptSetsView

        # Убираем старый drill-down если был
        for widget, _title, _path in list(self._drill_pages):
            try:
                self._center_stack.removeWidget(widget)
                widget.deleteLater()
            except Exception:
                pass
        self._drill_pages.clear()

        # Удаляем старый PromptSetsView если есть
        if self._prompt_sets_view is not None:
            try:
                self._center_stack.removeWidget(self._prompt_sets_view)
                self._prompt_sets_view.deleteLater()
            except Exception:
                pass
            self._prompt_sets_view = None

        view = PromptSetsView(self.prompts_root, char_name, parent=None)
        view.set_chosen.connect(self._on_char_selected)
        self._prompt_sets_view = view
        self._center_stack.addWidget(view)
        self._center_stack.setCurrentWidget(view)
        self._act_show_graph.setVisible(False)
        self._nav_bar.setVisible(False)

    def _show_tabs_view(self):
        """Показывает текстовый редактор (TabManager)."""
        self._center_stack.setCurrentIndex(1)
        self._act_show_graph.setVisible(True)
        self._nav_bar.setVisible(True)
        char_label = self.selected_char or ""
        self._nav_char_lbl.setText(char_label if char_label else "")
        # В режиме текстового редактора показываем метку персонажа, не breadcrumb
        self._nav_char_lbl.setVisible(True)
        for item in self._crumb_btns:
            try:
                item.setVisible(False)
            except Exception:
                pass

    # ---------- drill-down навигация (провалиться в скрипт) ----------

    def _push_drill_view(self, widget, title: str, file_path: str = ""):
        """Провалиться в новый вид: добавляет страницу в center_stack с breadcrumb."""
        self._drill_pages.append((widget, title, file_path))
        self._center_stack.addWidget(widget)
        self._center_stack.setCurrentWidget(widget)
        self._act_show_graph.setVisible(True)
        self._nav_bar.setVisible(True)
        self._nav_char_lbl.setVisible(False)
        self._update_breadcrumb()

    def _pop_to_drill_depth(self, depth: int):
        """Вернуться на уровень depth в стеке (0 = на главный граф)."""
        if depth == 0:
            self._show_graph_view()
            return
        while len(self._drill_pages) > depth:
            widget, _title, _path = self._drill_pages.pop()
            try:
                self._center_stack.removeWidget(widget)
                widget.deleteLater()
            except Exception:
                pass
        if self._drill_pages:
            last_widget, _, _ = self._drill_pages[-1]
            self._center_stack.setCurrentWidget(last_widget)
        self._update_breadcrumb()

    def _update_breadcrumb(self):
        """Перестраивает breadcrumb-кнопки в nav_bar."""
        # Убираем старые crumb-кнопки
        for item in self._crumb_btns:
            self._nb_row.removeWidget(item)
            try:
                item.deleteLater()
            except Exception:
                pass
        self._crumb_btns.clear()

        if not self._drill_pages:
            self._nav_char_lbl.setVisible(True)
            return

        self._nav_char_lbl.setVisible(False)
        _crumb_btn_style = (
            "background: transparent; border: none; color: #4a9eff; font-size: 11px;"
            " padding: 1px 4px;"
        )
        _crumb_cur_style = (
            "background: transparent; border: none; color: #e6edf3; font-size: 11px;"
            " font-weight: bold; padding: 1px 4px;"
        )

        # Удалим stretch перед вставкой (он последний)
        stretch_idx = self._nb_row.count() - 1
        self._nb_row.removeItem(self._nb_row.itemAt(stretch_idx))

        for i, (_widget, title, _path) in enumerate(self._drill_pages):
            sep = QLabel("›")
            sep.setStyleSheet("color: #6e7681; font-size: 13px; padding: 0 2px;")
            self._nb_row.addWidget(sep)
            self._crumb_btns.append(sep)

            is_current = (i == len(self._drill_pages) - 1)
            btn = QPushButton(title)
            btn.setFixedHeight(22)
            btn.setStyleSheet(_crumb_cur_style if is_current else _crumb_btn_style)
            if not is_current:
                depth = i + 1
                btn.clicked.connect(lambda checked=False, d=depth: self._pop_to_drill_depth(d))
            else:
                btn.setEnabled(False)
            self._nb_row.addWidget(btn)
            self._crumb_btns.append(btn)

        # Восстанавливаем stretch
        self._nb_row.addStretch()

    # ---------- открытие файлов из графа ----------

    def _on_file_open_requested(self, path: str):
        """Маршрутизирует открытие файла по расширению."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".script":
            self._open_nodes_for_path(path)
        elif ext == ".postscript":
            self._open_postscript_rules(path)
        else:
            self._open_file_in_tabs(path)

    def _on_drilldown_requested(self, rel_path: str, tag: str):
        """Обрабатывает сигнал open_file_requested от NodeGraphEditor."""
        # Сначала нужно разрешить относительный путь — ищем от текущего drill-уровня
        resolved = self._resolve_drill_path(rel_path)
        if not resolved or not os.path.isfile(resolved):
            # Формируем список кандидатов для удобной ошибки
            QMessageBox.warning(self, "Файл не найден", f"Файл не найден: {rel_path}")
            return
        ext = os.path.splitext(resolved)[1].lower()
        if ext in (".script", ".postscript"):
            self._open_nodes_for_path(resolved)
        else:
            self._push_text_view(resolved, tag)

    def _resolve_drill_path(self, rel_path: str) -> str | None:
        """Разрешает путь относительно текущего drill-уровня или prompts_root."""
        if os.path.isabs(rel_path) and os.path.exists(rel_path):
            return rel_path
        # Пытаемся разрешить от base_dir текущего верхнего drill-уровня
        if self._drill_pages:
            _, _, top_path = self._drill_pages[-1]
            if top_path:
                base = os.path.dirname(top_path)
                candidate_base = base
                for _ in range(5):
                    p = os.path.normpath(os.path.join(candidate_base, rel_path))
                    if os.path.exists(p):
                        return p
                    parent = os.path.dirname(candidate_base)
                    if parent == candidate_base:
                        break
                    candidate_base = parent
        # Фоллбек: от prompts_root
        if self.prompts_root:
            p = os.path.normpath(os.path.join(self.prompts_root, rel_path))
            if os.path.exists(p):
                return p
        return None

    def _push_text_view(self, path: str, tag: str = ""):
        """Проваливается в текстовый файл как drill-down страница."""
        title = os.path.basename(path)
        if tag:
            title += f" #{tag}"
        view = FileTextView(path, tag, parent=None)
        self._push_drill_view(view, title, file_path=path)

    def _open_file_in_tabs(self, path: str):
        """Открывает файл в TabManager и переключается на вкладки."""
        if path and os.path.isfile(path):
            self.tabs.open_file(path)
            self._show_editor()
            self._show_tabs_view()

    def _open_nodes_for_path(self, path: str):
        """Проваливается в NodeGraphEditor для .script файла (встроенный drill-down)."""
        if not path or not os.path.isfile(path):
            return
        try:
            from ui.node_graph.editor_widget import NodeGraphEditor

            # Если уже открыт этот файл в стеке — просто переключиться на него
            for idx, (widget, _title, fpath) in enumerate(self._drill_pages):
                if fpath == path:
                    self._pop_to_drill_depth(idx + 1)
                    return

            base_dir = os.path.dirname(path)
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                text = ""

            editor = NodeGraphEditor(
                base_dir=base_dir, prompts_root=self.prompts_root,
                file_path=path, parent=None
            )
            editor.load_text(text)

            # Автосохранение при изменении
            def _on_text_updated(new_text: str):
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new_text)
                    # Синхронизировать с TabManager если файл там открыт
                    for i in range(self.tabs.count()):
                        w = self.tabs.widget(i)
                        if hasattr(w, "get_tab_file_path") and w.get_tab_file_path() == path:
                            w.setPlainText(new_text)
                            break
                except Exception as e:
                    editor_logger.error(f"Ошибка автосохранения {path}: {e}")

            editor.text_updated.connect(_on_text_updated)
            editor.open_file_requested.connect(self._on_drilldown_requested)

            title = os.path.basename(path)
            self._push_drill_view(editor, title, file_path=path)

        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Нодовый редактор", f"Ошибка запуска:\n{e}\n{traceback.format_exc()}")

    def _open_postscript_rules(self, path: str):
        """Открывает .postscript в визуальном Rule Builder."""
        if not path or not os.path.isfile(path):
            return
        try:
            from widgets.post_dsl_rule_list import PostScriptRuleList
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
            dlg = QDialog(self)
            dlg.setWindowTitle(f"PostScript: {os.path.basename(path)}")
            dlg.resize(700, 600)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(0, 0, 0, 4)
            rule_list = PostScriptRuleList(dlg)
            rule_list.load_file(path)
            lay.addWidget(rule_list, 1)
            btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
            btns.accepted.connect(lambda: (rule_list.save(), dlg.accept()))
            btns.rejected.connect(dlg.reject)
            lay.addWidget(btns)
            dlg.exec()
        except Exception as e:
            editor_logger.error(f"PostScript Rule Builder error: {e}", exc_info=True)
            # Фолбэк: открываем как текст
            if os.path.isfile(path):
                self.tabs.open_file(path)
                self._show_editor()
                self._show_tabs_view()

    def _on_file_saved(self, path: str):
        """Обновляем панель шаблона при сохранении main_template.txt."""
        if os.path.basename(path) == "main_template.txt":
            self.tmpl_dock.refresh()

    # ---------------------- vars panel -------------------------
    def _sync_vars_panel(self):
        from utils.config_utils import read_config_json, get_bounds_defaults, compute_defaults_for_char
        if self.selected_char:
            # Передаём bounds для слайдеров (attitude 0-100, boredom 0-100, stress 0-100)
            raw_bounds = get_bounds_defaults()
            bounds: dict = {}
            for k in raw_bounds:
                if k.endswith("_min"):
                    varname = k[:-4]
                    bounds[varname] = (raw_bounds[k], raw_bounds.get(f"{varname}_max", 100.0))
            self.vars_dock.set_bounds(bounds)

            key = self._vars_key()
            saved = self.settings.value(key, "")
            if saved:
                self.vars_dock.load_vars_text(saved)
            else:
                cfg = read_config_json(self.prompts_root, self.selected_char)
                if cfg:
                    self.vars_dock.load_vars_text(self._dict2txt(cfg))
                else:
                    base = compute_defaults_for_char(self._char_part())
                    for k2, v in get_bounds_defaults().items():
                        base.setdefault(k2, v)
                    self.vars_dock.load_vars_text(self._dict2txt(base))
            self._baseline_cfg_dict = read_config_json(self.prompts_root, self.selected_char)
        else:
            self.vars_dock.clear_vars()
            self._baseline_cfg_dict = None
        self._update_save_button_state()

    def _open_node_editor(self):
        current_editor = self.tabs.currentWidget()
        if not current_editor or not hasattr(current_editor, "get_tab_file_path"):
            QMessageBox.information(self, "Нодовый редактор", "Нет активного редактора.")
            return

        file_path = current_editor.get_tab_file_path()
        if not file_path or not file_path.lower().endswith(".script"):
            QMessageBox.warning(self, "Нодовый редактор", "Откройте .script файл для визуального редактора.")
            return

        initial_text = current_editor.toPlainText() if hasattr(current_editor, "toPlainText") else ""

        def apply_back(new_text: str):
            if hasattr(current_editor, "setPlainText"):
                current_editor.setPlainText(new_text)

        try:
            from ui.node_graph_window import NodeGraphWindow
            # держим ссылку, чтобы окно не ушло в GC
            if not hasattr(self, "_node_windows"):
                self._node_windows = []
            win = NodeGraphWindow(initial_text, file_path=file_path, prompts_root=self.prompts_root, apply_callback=apply_back, parent=self)
            self._node_windows.append(win)
            win.show()
        except Exception as e:
            QMessageBox.critical(self, "Нодовый редактор", f"Ошибка запуска: {e}")

    def _reset_vars(self):
        self._apply_config_or_defaults_to_editor()

    def _apply_config_or_defaults_to_editor(self):
        from utils.config_utils import read_config_json, get_bounds_defaults, compute_defaults_for_char
        if self.selected_char:
            cfg = read_config_json(self.prompts_root, self.selected_char)
            if cfg:
                txt = self._dict2txt(cfg)
                self._baseline_cfg_dict = cfg
            else:
                base = compute_defaults_for_char(self._char_part())
                for k, v in get_bounds_defaults().items():
                    base.setdefault(k, v)
                txt = self._dict2txt(base)
                self._baseline_cfg_dict = None
            self.vars_dock.load_vars_text(txt)
            self.settings.setValue(self._vars_key(), txt)
            self.vars_dock.setWindowTitle(f"Параметры DSL — {self._set_display_name()}")
        else:
            self.vars_dock.clear_vars()
            self.vars_dock.setWindowTitle("Параметры DSL")
            self._baseline_cfg_dict = None
        self._update_save_button_state()

    def _save_config_json_for_current_vars(self):
        from utils.config_utils import compute_defaults_for_char, get_bounds_defaults, write_config_json, get_config_path
        if not self.selected_char:
            QMessageBox.information(self, "config.json", "Персонаж не выбран.")
            return
        if not self.prompts_root:
            QMessageBox.warning(self, "config.json", "Корневая папка Prompts не установлена.")
            return
        cfg_path = get_config_path(self.prompts_root, self.selected_char)
        current_vars = self._parse_vars()
        final_cfg = compute_defaults_for_char(self.selected_char)
        final_cfg.update(current_vars)
        for k, v in get_bounds_defaults().items():
            final_cfg.setdefault(k, v)
        if os.path.exists(cfg_path):
            r = QMessageBox.question(
                self, "Перезаписать config.json?",
                f"Файл уже существует:\n{cfg_path}\n\nПерезаписать его текущими значениями из панели?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if r != QMessageBox.Yes:
                return
        try:
            write_config_json(self.prompts_root, self.selected_char, final_cfg)
            QMessageBox.information(self, "config.json", f"Сохранено:\n{cfg_path}")
            txt = self._dict2txt(final_cfg)
            self.vars_dock.load_vars_text(txt)
            self.settings.setValue(self._vars_key(), txt)
            self._baseline_cfg_dict = final_cfg
            self._update_save_button_state()
        except Exception as e:
            QMessageBox.critical(self, "config.json", f"Ошибка сохранения:\n{e}")

    def _on_vars_text_changed(self):
        self._update_save_button_state()

    def _update_save_button_state(self):
        from utils.config_utils import get_config_path, read_config_json, are_configs_equal
        have_char = bool(self.selected_char)
        if not have_char:
            self.vars_dock.update_save_button_text(False)
            self.vars_dock.set_save_enabled(False)
            return
        cfg_path = get_config_path(self.prompts_root, self.selected_char)
        exists = os.path.exists(cfg_path)
        self.vars_dock.update_save_button_text(exists)
        if not exists:
            self.vars_dock.set_save_enabled(True)
            return
        baseline = self._baseline_cfg_dict if self._baseline_cfg_dict is not None else read_config_json(self.prompts_root, self.selected_char) or {}
        current = self._parse_vars()
        self.vars_dock.set_save_enabled(not are_configs_equal(current, baseline))

    def _check_syntax(self):
        from syntax.syntax_checker import PostScriptSyntaxChecker  # Импортируем здесь, чтобы избежать циклических зависимостей

        current_editor = self.tabs.currentWidget()
        if not current_editor:
            QMessageBox.information(self, "Проверка синтаксиса", "Нет открытых файлов для проверки.")
            return

        file_path = current_editor.get_tab_file_path()
        if not file_path:
            QMessageBox.information(self, "Проверка синтаксиса", "Файл не сохранен. Сохраните файл перед проверкой синтаксиса.")
            return

        file_content = current_editor.toPlainText()
        checker = PostScriptSyntaxChecker()
        errors: list = []
        
        if file_path.lower().endswith(".postscript"):
            errors = checker.check_postscript_syntax(file_content, file_path)
        elif file_path.lower().endswith(".script"):
            errors = checker.check_dsl_syntax(file_content, file_path)
        else:
            QMessageBox.warning(self, "Проверка синтаксиса", "Неподдерживаемое расширение файла для проверки синтаксиса. Поддерживаются .postscript и .script.")
            return

        if errors:
            error_messages = "\n".join([str(e) for e in errors])
            dlg = DslResultDialog(
                "Ошибки синтаксиса",
                content_blocks=[error_messages],
                system_infos=[],
                vars_before={},
                vars_after={},
                parent=self
            )
            dlg.show()
            editor_logger.warning(f"Синтаксические ошибки в {file_path}:\n{error_messages}")
        else:
            QMessageBox.information(self, "Проверка синтаксиса", f"Синтаксис файла '{os.path.basename(file_path)}' в порядке. Ошибок не найдено.")
            editor_logger.info(f"Синтаксис файла '{file_path}' в порядке.")

    def _run_dsl(self):
        if not DSL_ENGINE_AVAILABLE:
            QMessageBox.warning(self, "DSL", "DSL-движок недоступен.")
            return
        if not self.selected_char:
            QMessageBox.warning(self, "DSL", "Персонаж не выбран.")
            return
        if not self.prompts_root:
            editor_logger.error("Prompts root directory is not set. Cannot run DSL.")
            QMessageBox.warning(self, "DSL Ошибка", "Корневая папка Prompts не установлена.")
            return

        vars_dict = self._parse_vars()
        display_name = self._set_display_name()
        char = CharacterClass(self.selected_char, display_name, self.prompts_root, vars_dict)
        try:
            # Если нужны инсерты — добавьте tags. Иначе None.
            tags = None
            # Получаем: блоки, системные сообщения, снимки переменных до/после
            blocks, sys_infos, vars_before, vars_after = char.run_dsl(tags)

            dlg = DslResultDialog(
                f"DSL: {display_name}",
                content_blocks=blocks,
                system_infos=sys_infos,
                vars_before=vars_before,
                vars_after=vars_after,
                parent=self
            )
            dlg.show()
        except Exception as e:
            QMessageBox.critical(self, "DSL-ошибка", str(e))
            editor_logger.error(f"Error running DSL for {self.selected_char}: {e}", exc_info=True)

    def _parse_vars(self) -> dict:
        out = {}
        for line in self.vars_dock.editor().toPlainText().splitlines():
            if "=" not in line: continue
            k, v = map(str.strip, line.split("=", 1))
            if v.lower() in ("true", "false"): v = v.lower() == "true"
            else:
                try: v = int(v)
                except: 
                    try: v = float(v)
                    except: v = v.strip("'\"")
            out[k] = v
        return out

    def _update_run_dsl_state(self):
        have_char = bool(self.prompts_root and self.selected_char)
        enabled   = DSL_ENGINE_AVAILABLE and have_char
        self.run_act.setEnabled(enabled)

        if have_char:
            self.run_act.setText(f'Скомпоновать промпт для "{self._set_display_name()}"')
        else:
            self.run_act.setText('Скомпоновать промпт')

        self._update_postdsl_action_state()

    def _update_postdsl_action_state(self):
        """Активируем «Тестировать PostDSL…» только если открыт .postscript файл."""
        if not hasattr(self, "_test_postdsl_act"):
            return
        ed = self.tabs.currentWidget()
        if ed and hasattr(ed, "get_tab_file_path"):
            path = ed.get_tab_file_path() or ""
            self._test_postdsl_act.setEnabled(path.lower().endswith(".postscript"))
        else:
            self._test_postdsl_act.setEnabled(False)

    # ------------------------ helpers -------------------------
    def _change_prompts_dir(self):
        if self.tabs.count() and not self._ask_close_all_tabs(): return
        
        # Запрашиваем новую директорию
        new_prompts_path = select_prompts_directory_dialog(self, self.settings, PROMPTS_DIR_NAME, "Выберите папку Prompts")
        
        if new_prompts_path:
            self.prompts_root = new_prompts_path

            if hasattr(self.tree, 'update_prompts_root'):
                self.tree.update_prompts_root(new_prompts_path)
            else:
                self.tree.model().setRootPath(new_prompts_path)
                self.tree.setRootIndex(self.tree.model().index(new_prompts_path))
                editor_logger.warning("FileTreePanel.update_prompts_root() не найден, используется старый метод обновления.")

            # Обновляем стартовый экран с новой папкой
            self.char_selector.reload(new_prompts_path)
            self._show_selector()
            self._on_char_selected("") 


    def _ask_close_all_tabs(self):
        return QMessageBox.question(self, "Закрыть вкладки", "Закрыть все открытые вкладки?",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes

    # --------------------- title & status ---------------------
    def _update_title(self):
        base = f"Редактор Промптов — {SETTINGS_APP_NAME}"
        ed   = self.tabs.currentWidget()
        
        current_char_id = None
        if hasattr(ed, "get_tab_file_path") and ed:
            path = ed.get_tab_file_path() or "Новый файл"
            star = "*" if ed.document().isModified() else ""
            self.setWindowTitle(f"{os.path.basename(path)}{star} — {base}")
            self.path_lbl.setText(path)

            # Попытка определить персонажа и набор из пути файла
            if self.prompts_root and path != "Новый файл":
                try:
                    root = Path(self.prompts_root)
                    parts = Path(path).relative_to(root).parts
                    if parts:
                        char_part = parts[0]
                        if len(parts) >= 2 and not parts[1].startswith("_"):
                            candidate = root / char_part / parts[1]
                            if candidate.is_dir():
                                current_char_id = f"{char_part}/{parts[1]}"
                            else:
                                current_char_id = char_part
                        else:
                            current_char_id = char_part
                except ValueError:
                    editor_logger.debug(f"Не удалось определить персонажа из пути файла (вне prompts_root): {path}")
                except IndexError:
                    editor_logger.debug(f"Путь к файлу слишком короткий для определения персонажа: {path}")
        else:
            self.setWindowTitle(base); self.path_lbl.setText("Нет открытых файлов")

        # Обновляем выбранного персонажа и UI, если он изменился
        if current_char_id != self.selected_char:
            self._on_char_selected(current_char_id or "")

    # ---------------- settings / loggers ----------------------
    def closeEvent(self, ev):
        self._save_settings(); super().closeEvent(ev)

    def _save_settings(self):
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("splitter",    self.splitter.saveState())
        
        current_editor = self.tabs.currentWidget()
        if current_editor and hasattr(current_editor, 'get_tab_file_path'):
            last_file_path = current_editor.get_tab_file_path()
            if last_file_path:
                self.settings.setValue("lastOpenedFile", last_file_path)
        else:
            self.settings.remove("lastOpenedFile") # Очищаем, если нет открытых файлов

        if self.selected_char:
            self.settings.setValue(
                self._vars_key(),
                self.vars_dock.editor().toPlainText()
            )
        if self.prompts_root:
            self.settings.setValue("lastPromptsDir", self.prompts_root)

    def _load_settings(self):
        if (st := self.settings.value("windowState")): self.restoreState(st)
        if (sp := self.settings.value("splitter")):    self.splitter.restoreState(sp)
        if (last := self.settings.value("lastPromptsDir")) and os.path.isdir(last):
            self.prompts_root = last
            self.tree.setRootIndex(self.tree.model().setRootPath(last))

    def _test_postdsl(self):
        """Открывает диалог тестирования PostDSL для текущего .postscript файла."""
        ed = self.tabs.currentWidget()
        if not ed or not hasattr(ed, "get_tab_file_path"):
            return
        path = ed.get_tab_file_path() or ""
        if not path.lower().endswith(".postscript"):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "PostDSL", "Откройте .postscript файл для тестирования.")
            return

        script_text = ed.toPlainText() if hasattr(ed, "toPlainText") else ""
        variables = self._parse_vars()

        if not hasattr(self, "_postdsl_dialogs"):
            self._postdsl_dialogs = []
        dlg = PostDslTestDialog(script_text, variables, parent=self)
        self._postdsl_dialogs.append(dlg)
        dlg.finished.connect(lambda: self._postdsl_dialogs.remove(dlg) if dlg in self._postdsl_dialogs else None)
        dlg.show()

    def _setup_loggers(self):
        h = self.log_dock.get_handler()

        # 1) Локальный редакторский логгер
        add_editor_log_handler(h)

        # 2) DSL-логгеры
        for l in (get_dsl_execution_logger(), get_dsl_script_logger()):
            if l and all(existing is not h for existing in l.handlers):
                l.addHandler(h)
