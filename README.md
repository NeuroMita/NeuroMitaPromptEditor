# Конструктор промптов (DSL) — короткое руководство для промптеров

Конструктор собирает большой финальный промпт из множества файлов
(текста и логики).  Всё выполняется **до** того, как строка уходит в
LLM, поэтому в ответ модели попадает только «чистый» текст.

---

## 1. Основные элементы

| Файл / сущность | Что это | Как выглядит |
|-----------------|---------|--------------|
| **Текстовый шаблон** (`*.txt`) | Обычный текст, может включать другие файлы. | `common.txt`, `player.txt` |
| **Скрипт** (`*.script`) | Небольшой файл с командами, который возвращает строку. | `fsm_handler.script` |
| **Плейсхолдер** | Вставка другого файла (текста или результата скрипта). | `[<Main/common.txt>]` |
| **Вставка** (`insert`) | Метка `{{NAME}}`, заполняется из Python-кода. | `{{SYS_INFO}}` |
| **Секция** | Часть `.txt`, выделенная `[ #TAG ] … [ /TAG ]`. | `[ #GREETING ]` … |

---

## 2. Как всё склеивается

1. Точка входа — `main_template.txt` персонажа.  
2. Конструктор читает его сверху вниз, встречает плейсхолдеры `[<…>]`.  
3. Если путь ведёт на `.txt` — файл вставляется.  
4. Если путь ведёт на `.script` — скрипт исполняется, что он вернёт —
   то и будет подставлено.  
5. После обхода всех файлов метки `{{…}}` меняются на свои значения.  
6. Итоговый текст отправляется в модель.

---

## 3. Плейсхолдеры `[< … >]`

```text
[<Main/common.txt>]            # подставит текст
[<Scripts/get_emotions.script>]# выполнит скрипт и вставит результат
```

*Пути работают как в обычной файловой системе: `./`, `../`,
или из общих папок `_CommonPrompts/`, `_CommonScripts/`.*

---

## 4. Вставки `{{ … }}`

```text
{{SYS_INFO}}
{{PLAYER_NAME}}
```

Заполняются из Python:

```python
interp.set_insert("PLAYER_NAME", "Алиса")
```

`{{SYS_INFO}}` — обязательная системная вставка.

---

## 5. Секции внутри `.txt`

```text
[#GREETING]
Привет, путник!
[/GREETING]
```

Скрипт может вернуть именно эту часть:

```dsl
RETURN LOAD GREETING FROM "Main/phrases.txt"
```

Если нужен весь файл:

```dsl
RETURN LOAD "Main/phrases.txt"   # маркеры секций будут убраны
```

---

## 6. Команды в `.script`

| Команда | Описание | Пример |
|---------|----------|--------|
| `SET var = выражение` | Записывает значение. | `SET mood = "happy"` |
| `LOG выражение` | Пишет в лог. | `LOG "mood=" + mood` |
| `IF / ELSEIF / ELSE / ENDIF` | Условные блоки. | `IF score > 50 THEN … ENDIF` |
| `RETURN …` | Завершает скрипт и отдаёт строку. | `RETURN "Готово!"` |

### 6.1 Что можно положить в `RETURN`

```
RETURN "Просто текст"
RETURN LOAD "Main/core.txt"
RETURN LOAD GREETING FROM "Main/phrases.txt"
RETURN LOAD A FROM "file.txt" + "\n" + LOAD B FROM "file.txt"
```

Последний пример показывает **inline-LOAD** —
загрузка секций прямо внутри выражения.

---

## 7. Как ищутся файлы

1. `_CommonPrompts/`, `_CommonScripts/` — общие ресурсы.  
2. `./` и `../` — вокруг текущего файла.  
3. Всё остальное — внутри папки персонажа.  
Конструктор не даст выйти за пределы папки `Prompts/`.

---

## 8. Живой пример — персонаж CrazyMita

```
Prompts/
└── Crazy/
    ├── main_template.txt
    ├── Main/
    │   ├── common.txt
    │   ├── main.txt
    │   ├── mainCrazy.txt
    │   └── mainPlaying.txt
    ├── Context/
    │   ├── examplesLong.txt
    │   ├── examplesLongCrazy.txt
    │   └── mita_history.txt
    ├── Events/
    │   └── SecretExposed.txt
    ├── Scripts/
    │   ├── personality_selector.script
    │   ├── example_selector.script
    │   ├── get_available_emotions.script
    │   └── … (другие файлы логики)
    └── Structural/
        └── response_structure.txt
```

### 8.1 `main_template.txt`

```text
[<Structural/response_structure.txt>]
[<../Common/Dialogue.txt>]

[<Scripts/get_variable_effects_description.script>]
[<Scripts/initialize_character.script>]
[<Scripts/personality_selector.script>]

[<Main/player.txt>]

[<Scripts/example_selector.script>]
[<Scripts/history_loader.script>]
[<Scripts/event_handler.script>]
[<Scripts/context_info.script>]

[<Main/common.txt>]
[<Scripts/fsm_handler.script>]
```

*Каждая строка включает файл или отдаёт результат скрипта — из
этого «каркаса» собирается финальный промпт.*

### 8.2 Фрагмент `personality_selector.script`

```dsl
LOG "PersonalitySelector: started. attitude=" + attitude

IF (attitude <= 10 OR secretExposed == True) THEN
    SET available_action_level = 2
    RETURN LOAD "Main/mainCrazy.txt"
ENDIF

IF attitude < 50 AND secretExposed == False THEN
    SET available_action_level = 1
    RETURN LOAD "Main/mainPlaying.txt"
ENDIF

RETURN LOAD "Main/main.txt"
```

Скрипт решает, какую версию личности подставить, и просто возвращает
нужный файл через `LOAD`.

---

## 9. Советы

1. **Делите** большой текст на мелкие `.txt`.  
2. **Логи** (`LOG`) помогут понять, почему скрипт выбрал ту или иную ветку.  
3. Длинный текст → `.txt`, проверка условий → `.script`.  
4. Файлы, которые нужны многим персонажам, кладите в `_CommonPrompts` /
   `_CommonScripts`.  
5. Убедитесь, что `{{SYS_INFO}}` встречается хотя бы один раз, если он
   нужен системе.  
6. Проверяйте результат — кнопка «Скомпоновать промпт» в редакторе
   покажет финальный текст, который увидит модель.
