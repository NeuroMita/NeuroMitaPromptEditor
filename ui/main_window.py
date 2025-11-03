import os, logging
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QLabel, QMessageBox
)
from PySide6.QtCore import Qt, QSettings, QItemSelectionModel

# ---------- локальные блоки ----------
from ui.tree_panel          import FileTreePanel
from ui.tab_manager         import TabManager
from ui.dsl_variables_dock  import DslVariablesDock
from widgets.log_panel import LogPanel

# ---------- утилиты / константы -------
from config import PROMPTS_DIR_NAME, SETTINGS_ORG_NAME, SETTINGS_APP_NAME
from utils.path_helpers import find_or_ask_prompts_root, select_prompts_directory_dialog
from utils.logger       import add_editor_log_handler, get_dsl_execution_logger, editor_logger, get_dsl_script_logger
from dsl_manager        import DSL_ENGINE_AVAILABLE, CharacterClass
from widgets.dsl_result_dialog import DslResultDialog

# ---------- модели персонажей ----------
from models.character import Character
from models.characters import (
    CrazyMita, KindMita, ShortHairMita,
    CappyMita, MilaMita, CreepyMita, SleepyMita
)

_log = logging.getLogger(__name__)

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

    def _defaults_for(self, char_id: str | None) -> dict:
        if not char_id:
            return Character.BASE_DEFAULTS.copy()
        for cls in _LEGACY_CLASSES:
            if cls.__name__.lower().startswith(char_id.lower()):
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

        # Загружаем и открываем последний открытый файл
        last_opened_file = self.settings.value("lastOpenedFile")
        if last_opened_file and os.path.isfile(last_opened_file):
            self.tabs.open_file(last_opened_file)
            editor_logger.info(f"Открыт последний файл: {last_opened_file}")
            
            # Программно выбираем файл в дереве, чтобы обновить selected_char и UI
            file_index = self.tree._model.index(last_opened_file)
            if file_index.isValid():
                self.tree.selectionModel().setCurrentIndex(file_index, QItemSelectionModel.ClearAndSelect)
                editor_logger.info(f"Выбран файл в дереве: {last_opened_file}")
            else:
                editor_logger.warning(f"Не удалось найти индекс файла в дереве: {last_opened_file}")
                self._on_char_selected("") # Сбросить выбор персонажа, если файл не найден в дереве

            self._update_title() # Вызываем _update_title после открытия файла и выбора в дереве
        else:
            if last_opened_file:
                editor_logger.warning(f"Сохраненный путь к последнему файлу '{last_opened_file}' недействителен.")
            else:
                editor_logger.info("Путь к последнему открытому файлу не найден в настройках.")
            self._update_title() # Вызываем _update_title, чтобы установить заголовок "Нет открытых файлов" и сбросить персонажа

        if not self.prompts_root:
            QMessageBox.warning(self, "Prompts", "Корневая папка Prompts не выбрана. Функциональность будет ограничена.")
        if not DSL_ENGINE_AVAILABLE:
            QMessageBox.warning(self, "DSL", "DSL-движок недоступен. Функциональность будет ограничена.")

    def _load_window_layout_settings(self): # Новый метод
        if (st := self.settings.value("windowState")): self.restoreState(st)
        if (sp := self.settings.value("splitter")):    self.splitter.restoreState(sp)

    # --------------------- UI construction ----------------------
    def _build_ui(self):
        spl = QSplitter(Qt.Horizontal, self); self.splitter = spl; self.setCentralWidget(spl)

        self.tree = FileTreePanel(self.prompts_root, lambda: self.tabs.modified_paths(), self)
        spl.addWidget(self.tree)

        self.tabs = TabManager(lambda: self.prompts_root, self)
        spl.addWidget(self.tabs); spl.setStretchFactor(1, 1)

        self.vars_dock = DslVariablesDock(self); self.addDockWidget(Qt.RightDockWidgetArea, self.vars_dock)
        self.log_dock  = LogPanel(parent=self); self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)

        sb = QStatusBar(); self.setStatusBar(sb)
        self.path_lbl = QLabel("Нет открытых файлов"); sb.addPermanentWidget(self.path_lbl)

        self.tree.file_open_requested.connect(self.tabs.open_file)
        self.tree.character_selected.connect(self._on_char_selected)
        self.tabs.modified_set_changed.connect(lambda: self.tree.viewport().update())
        self.tabs.currentChanged.connect(self._update_title)
        self.vars_dock.reset_requested.connect(self._reset_vars)
        self.vars_dock.set_on_save_clicked(self._save_config_json_for_current_vars)
        self.vars_dock.editor().textChanged.connect(self._on_vars_text_changed)

        tb = self.addToolBar("DSL")
        self.run_act = tb.addAction("Скомпоновать промпт", self._run_dsl)
        self._update_run_dsl_state()

        title = "Параметры DSL" + (f" — {self.selected_char}" if self.selected_char else "")
        self.vars_dock.setWindowTitle(title)

        self._build_menu()
        self._setup_loggers()

        self._baseline_cfg_dict = None
        self._update_save_button_state()


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

        # -------- Вид --------
        vm = mb.addMenu("&Вид")

        vars_toggle = self.vars_dock.toggleViewAction()
        vars_toggle.setText("Панель переменных DSL")
        vm.addAction(vars_toggle)

        log_toggle = self.log_dock.toggleViewAction()
        log_toggle.setText("Панель логов")
        vm.addAction(log_toggle)

    # --------------------- tree -> персонаж ---------------------
    def _on_char_selected(self, char_id: str):
        self.selected_char = char_id or None
        self._sync_vars_panel()
        self._update_run_dsl_state()

        title = "Параметры DSL" + (f" — {self.selected_char}" if self.selected_char else "")
        self.vars_dock.setWindowTitle(title)

    # ---------------------- vars panel -------------------------
    def _sync_vars_panel(self):
        from utils.config_utils import read_config_json, get_bounds_defaults, compute_defaults_for_char
        ed = self.vars_dock.editor(); ed.blockSignals(True)
        if self.selected_char:
            key = f"{self.selected_char.lower()}_vars"
            saved = self.settings.value(key, "")
            if saved:
                ed.setPlainText(saved)
            else:
                cfg = read_config_json(self.prompts_root, self.selected_char)
                if cfg:
                    ed.setPlainText(self._dict2txt(cfg))
                else:
                    base = compute_defaults_for_char(self.selected_char)
                    for k, v in get_bounds_defaults().items():
                        base.setdefault(k, v)
                    ed.setPlainText(self._dict2txt(base))
            self._baseline_cfg_dict = read_config_json(self.prompts_root, self.selected_char)
        else:
            ed.clear()
            self._baseline_cfg_dict = None
        ed.blockSignals(False)
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
        ed = self.vars_dock.editor()
        if self.selected_char:
            cfg = read_config_json(self.prompts_root, self.selected_char)
            if cfg:
                txt = self._dict2txt(cfg)
                self._baseline_cfg_dict = cfg
            else:
                base = compute_defaults_for_char(self.selected_char)
                for k, v in get_bounds_defaults().items():
                    base.setdefault(k, v)
                txt = self._dict2txt(base)
                self._baseline_cfg_dict = None
            ed.setPlainText(txt)
            self.settings.setValue(f"{self.selected_char.lower()}_vars", txt)
            self.vars_dock.setWindowTitle(f"Параметры DSL — {self.selected_char}")
        else:
            ed.clear()
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
            self.vars_dock.editor().setPlainText(txt)
            self.settings.setValue(f"{self.selected_char.lower()}_vars", txt)
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
        from syntax.syntax_checker import PostScriptSyntaxChecker, SyntaxError  # Импортируем здесь, чтобы избежать циклических зависимостей

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
        errors: List[SyntaxError] = []
        
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
        char = CharacterClass(self.selected_char, self.selected_char, self.prompts_root, vars_dict)
        try:
            # Если нужны инсерты — добавьте tags. Иначе None.
            tags = None
            # Получаем: блоки, системные сообщения, снимки переменных до/после
            blocks, sys_infos, vars_before, vars_after = char.run_dsl(tags)

            dlg = DslResultDialog(
                f"DSL: {self.selected_char}",
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
            self.run_act.setText(f'Скомпоновать промпт для “{self.selected_char}”')
        else:
            self.run_act.setText("Скомпоновать промпт")

    # ------------------------ helpers -------------------------
    def _change_prompts_dir(self):
        if self.tabs.count() and not self._ask_close_all_tabs(): return
        
        # Запрашиваем новую директорию
        new_prompts_path = select_prompts_directory_dialog(self, self.settings, PROMPTS_DIR_NAME, "Выберите папку Prompts")
        
        if new_prompts_path:
            self.prompts_root = new_prompts_path #
            
            if hasattr(self.tree, 'update_prompts_root'):
                self.tree.update_prompts_root(new_prompts_path)
            else:
                self.tree.model().setRootPath(new_prompts_path)
                self.tree.setRootIndex(self.tree.model().index(new_prompts_path))
                editor_logger.warning("FileTreePanel.update_prompts_root() не найден, используется старый метод обновления.")

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

            # Попытка определить персонажа из пути файла
            if self.prompts_root and path != "Новый файл":
                try:
                    relative_path = Path(path).relative_to(self.prompts_root)
                    # Предполагаем, что имя персонажа - это первая папка после prompts_root
                    current_char_id = str(relative_path.parts[0])
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
                f"{self.selected_char.lower()}_vars",
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

    def _setup_loggers(self):
        h = self.log_dock.get_handler()

        # 1) Локальный редакторский логгер
        from utils.logger import add_editor_log_handler, get_dsl_execution_logger, get_dsl_script_logger
        add_editor_log_handler(h)

        # 2) DSL-логгеры
        for l in (get_dsl_execution_logger(), get_dsl_script_logger()):
            if l and all(existing is not h for existing in l.handlers):
                l.addHandler(h)
