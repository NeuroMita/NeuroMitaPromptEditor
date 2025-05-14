# DSL-Конструктор промптов  
легкое руководство для промптеров

> Система собирает **готовый текст** из кусочков-файлов.  
> Всё «волшебство» происходит заранее — в модель уходит чистый итог.

---

## 1. Что есть что

| Объект                     | Файл | Зачем нужен                                  |
|----------------------------|------|----------------------------------------------|
| Текстовый блок             | `.txt`   | Простой текст. Может подтягивать другие файлы. |
| Скрипт                     | `.script`| Принимает решения: «какой блок взять?», «что вернуть?». |
| Плейсхолдер                | —    | `[<path/file.ext>]` — вставить файл или результат скрипта. |
| Вставка (insert)           | —    | `{{NAME}}` — заполняется извне (например, `{{SYS_INFO}}`). |
| Секция в `.txt`            | —    | `[ #TAG ] … [ /TAG ]` — именованный кусок внутри файла. |

---

## 2. Коротко о сборке

```
main_template.txt ──► читает плейсхолдеры
                    ├──► вставляет .txt
                    ├──► запускает .script → RETURN
                    └──► меняет {{INSERTS}}
результат  ──► уходит в LLM
```

---

## 3. Синтаксис вставок

| Хотим …                                  | Пишем                                   |
|------------------------------------------|-----------------------------------------|
| Вставить файл целиком                    | `[<Main/common.txt>]`                   |
| Выполнить скрипт и подставить ответ      | `[<Scripts/build_mood.script>]`         |
| Вставить **секцию** из файла             | `LOAD GREETING FROM "Main/phrases.txt"` |
| Вставить файл внутри выражения           | `SET txt = LOAD FULL FROM "x.txt" + "!"`|
| Вставка-метка                            | `{{SYS_INFO}}`                          |

*Если путь начинается с `./` или `../` — он считается от текущего файла.  
`_CommonPrompts/` и `_CommonScripts/` доступны для общих ресурсов.*

---

## 4. Команды в `.script`

| Команда                                | Что делает                                                                        | Быстрый пример |
|----------------------------------------|-----------------------------------------------------------------------------------|----------------|
| `SET var = выражение`                  | Сохраняет значение.                                                               | `SET mood = "happy"` |
| `LOG выражение`                        | Пишет в лог (для отладки).                                                        | `LOG mood` |
| `IF / ELSEIF / ELSE / ENDIF`           | Условные блоки.                                                                   | `IF score>50 THEN … ENDIF` |
| `RETURN …`                             | Завершает скрипт и отдаёт строку.                                                 | `RETURN "готово"` |
| `LOAD`, `LOAD <TAG> FROM "file"`       | Часть `RETURN` или выражения: берёт файл целиком либо секцию.                     | `RETURN LOAD "Main/a.txt"` |

Выражения поддерживают `+`, арифметику, f-строки, булевы операции
(`AND`, `OR`).

---

## 5. Мини-пример «до / после»

### Скрипт `example_selector.script`

```dsl
LOG "ExampleSelector: start. secretExposed=" + secretExposed

IF secretExposed == TRUE THEN
    RETURN LOAD "Context/examplesLongCrazy.txt"
ELSE
    RETURN LOAD "Context/examplesLong.txt"
ENDIF
```

### В `main_template.txt`

```text
[<Scripts/example_selector.script>]
```

### Что получится

```
(предположим secretExposed == FALSE)

Файл Context/examplesLong.txt будет вставлен целиком,
а маркеры [#…]/[/…] — удалены.
```

---

## 6. Большой практический пример — CrazyMita

```
Prompts/
└── Crazy/
    ├── main_template.txt
    ├── Main/          — основные личности
    ├── Context/       — длинные фразы и история
    ├── Events/        — тексты событий
    ├── Scripts/       — логика выбора и генерации
    └── Structural/    — шаблон ответа и справка
```

**Главный шаблон**

```text
[<Structural/response_structure.txt>]
[<../Common/Dialogue.txt>]

[<Scripts/get_variable_effects_description.script>]
[<Scripts/personality_selector.script>]   # решает, какую «Миту» взять
[<Main/player.txt>]

[<Scripts/example_selector.script>]       # длинные примеры фраз
[<Scripts/history_loader.script>]         # история
[<Scripts/event_handler.script>]          # редкие события
[<Scripts/context_info.script>]           # текущее время и счётчики

[<Main/common.txt>]
[<Scripts/fsm_handler.script>]            # состояние finite-state-machine
```

*Весь «кирпичный» текст лежит в `.txt`, а выбор и условия — в `.script`.
Менять поведение означает поменять лишь скрипты.*

---

## 7. Быстрый тест из Python

```python
char = CrazyMitaCharacter()              # объект вашего персонажа
dsl  = DslInterpreter(char)

dsl.set_insert("SYS_INFO",
               "[SYSTEM]: demo info")    # заполняем вставку

prompt_text = dsl.process_main_template_file("main_template.txt")
print(prompt_text)                       # готовая строка
```

---

## 8. Полезные советы

* **Делите** длинные описания на `.txt`.  
* **Логи** (`LOG ...`) помогают понять, куда пошёл скрипт.  
* Общие материалы кладите в `_CommonPrompts` / `_CommonScripts`.  
* Проверяйте итог с помощью «Скомпоновать промпт» — увидите финальный текст.  
* Держите хотя бы одну метку `{{SYS_INFO}}`, если система планирует её
  заполнять.
