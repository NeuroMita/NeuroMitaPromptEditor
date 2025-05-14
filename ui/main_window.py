import os, logging
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QLabel, QMessageBox
)
from PySide6.QtCore import Qt, QSettings

# ---------- локальные блоки ----------
from .tree_panel          import FileTreePanel
from .tab_manager         import TabManager
from .dsl_variables_dock  import DslVariablesDock
from app.widgets.log_panel import LogPanel

# ---------- утилиты / константы -------
from app.config import PROMPTS_DIR_NAME, SETTINGS_ORG_NAME, SETTINGS_APP_NAME
from app.utils.path_helpers import find_or_ask_prompts_root, select_prompts_directory_dialog
from app.utils.logger       import add_editor_log_handler, get_dsl_execution_logger, editor_logger, get_dsl_script_logger
from app.dsl_manager        import DSL_ENGINE_AVAILABLE, CharacterClass
from app.widgets.dsl_result_dialog import DslResultDialog

# ---------- модели персонажей ----------
from app.models.character import Character
from app.models.characters import (
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
                import app.config as cfg_mod
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

        self._setup_loggers()
        self._update_title() # Обновит заголовок, если символ выбран (маловероятно на этом этапе)

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

        # connections
        self.tree.file_open_requested.connect(self.tabs.open_file)
        self.tree.character_selected.connect(self._on_char_selected)
        self.tabs.modified_set_changed.connect(lambda: self.tree.viewport().update())
        self.vars_dock.reset_requested.connect(self._reset_vars)

        # toolbar
        tb = self.addToolBar("DSL")
        self.run_act = tb.addAction("Скомпоновать промпт", self._run_dsl)
        self._update_run_dsl_state()

        title = "Параметры DSL" + (f" — {self.selected_char}" if self.selected_char else "")
        self.vars_dock.setWindowTitle(title)

        self._build_menu()

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
        ed = self.vars_dock.editor(); ed.blockSignals(True)
        if self.selected_char:
            key = f"{self.selected_char.lower()}_vars"
            saved = self.settings.value(key, "")
            ed.setPlainText(saved or self._dict2txt(self._defaults_for(self.selected_char)))
        else:
            ed.clear()
        ed.blockSignals(False)

    def _reset_vars(self):
        ed = self.vars_dock.editor()
        if self.selected_char:
            txt = self._dict2txt(self._defaults_for(self.selected_char))
            ed.setPlainText(txt)
            self.settings.setValue(f"{self.selected_char.lower()}_vars", txt)
            self.vars_dock.setWindowTitle(f"Параметры DSL — {self.selected_char}")   # ← новая строка
        else:
            ed.clear()
            self.vars_dock.setWindowTitle("Параметры DSL")

    def _run_dsl(self):
        if not DSL_ENGINE_AVAILABLE:
            QMessageBox.warning(self, "DSL", "DSL-движок недоступен.")
            return
        if not self.selected_char:
            QMessageBox.warning(self, "DSL", "Персонаж не выбран.")
            return
        if not self.prompts_root: # <<< НОВАЯ ПРОВЕРКА
            editor_logger.error("Prompts root directory is not set. Cannot run DSL.")
            QMessageBox.warning(self, "DSL Ошибка", "Корневая папка Prompts не установлена.")
            return

        vars_dict = self._parse_vars()
        # <<< ИЗМЕНЕНО: передаем self.prompts_root в конструктор CharacterClass
        char = CharacterClass(self.selected_char, self.selected_char, self.prompts_root, vars_dict)
        try:
            sys_info_fake = ["[SYS_INFO]: Пример Системного Сообщения.", "[SYS_INFO]_2 Пример второго системного сообщения."]
            tags = {"SYS_INFO": sys_info_fake}
            prompt = char.get_full_prompt(tags)
            DslResultDialog(f"DSL: {self.selected_char}", prompt, self).show()
        except Exception as e:
            QMessageBox.critical(self, "DSL-ошибка", str(e))
            editor_logger.error(f"Error running DSL for {self.selected_char}: {e}", exc_info=True) # Добавим логирование

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
        if hasattr(ed, "get_tab_file_path") and ed:
            path = ed.get_tab_file_path() or "Новый файл"
            star = "*" if ed.document().isModified() else ""
            self.setWindowTitle(f"{os.path.basename(path)}{star} — {base}")
            self.path_lbl.setText(path)
        else:
            self.setWindowTitle(base); self.path_lbl.setText("Нет открытых файлов")

    # ---------------- settings / loggers ----------------------
    def closeEvent(self, ev):
        self._save_settings(); super().closeEvent(ev)

    def _save_settings(self):
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("splitter",    self.splitter.saveState())
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
        add_editor_log_handler(h)
        for l in (get_dsl_execution_logger(), get_dsl_script_logger()):
            if l: l.addHandler(h)