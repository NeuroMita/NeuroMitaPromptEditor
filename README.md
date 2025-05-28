# Конструктор промптов (DSL)

Доки сгенерены, так что если что-то непонятно — пишите

---

## 1. Зачем это всё

* **Идея:** писать текст кусочками («кирпичиками»), а конструктор склеит
  их в одну строку.
* **Что умеет:**
  1. Подставлять файлы через простые скобки `[<…>]`.
  2. Запускать скрипты и менять текст в зависимости от переменных.
  3. Вставлять заранее подготовленную информацию — `{{SysInfo}}`
     и другие вставки.

---

## 2. Какие бывают файлы

| Расширение | Для чего нужен                                          |
|------------|---------------------------------------------------------|
| `*.txt`    | Обычный текст. Может включать другие файлы и секции.    |
| `*.script` | Скрипт. Запускается, возвращает строку (командой `RETURN`). |
| `*.postscript` | Правила постобработки вывода LLM. |

---

## 3. Как собирается финальный текст

1. Стартовый файл — **`main_template.txt`** персонажа.  
2. В нём встречаются плейсхолдеры `[<…>]`.  
3. Если путь указывает на `.txt`, файл вставляется «как есть».  
4. Если путь указывает на `.script`, скрипт выполняется;
   его строка-результат подставляется.  
5. Затем меняются все вставки `{{…}}` на свои значения.  
6. Готовый текст отправляется в LLM.

---

## 4. Плейсхолдеры `[< … >]`

```text
[<Main/common.txt>]            # вставит текст
[<Scripts/build_mood.script>]  # выполнит скрипт и подставит строку
```

Путь пишется:

* относительно текущего файла `./…`
* на уровень выше `../…`
* из общих папок `_CommonPrompts/`, `_CommonScripts/`.

---

## 5. Вставки `{{ … }}`

```text
{{SysInfo}}
{{PlayerName}}
```

Значение задаётся в Python:

```python
interp.set_insert("PlayerName", "Алиса")
```

---

## 6. Секции в `.txt`

```text
[#Greeting]
Привет, путник!
[/Greeting]

[#Farewell]
До встречи.
[/Farewell]
```

* Взять конкретную секцию:  
  ```js
  RETURN LOAD Greeting FROM "Main/phrases.txt"
  ```
* Взять весь файл (маркеры секций будут убраны):  
  ```js
  RETURN LOAD "Main/phrases.txt"
  ```

---

## 7. Скрипты (`*.script`)

### 7.1 Полный список команд

---

## 8. Postscript-ы (`*.postscript`)

Postscript-файлы используются для постобработки текста, полученного от LLM, перед его использованием. Они позволяют изменять текст, извлекать информацию и обновлять переменные на основе определенных правил.

### 8.1 Структура Postscript-файла

Postscript-файл состоит из одного или нескольких блоков `RULE` и опционального блока `DEBUG_DISPLAY`.

#### 8.1.1 Блок `RULE`

Каждый `RULE` определяет набор условий (`MATCH`) и действий (`ACTIONS`), которые выполняются, если условие совпадает.

```
RULE <ИмяПравила>
    MATCH [REGEX "<регулярное_выражение>" CAPTURE (<переменные_захвата>)]
          [TEXT "<текст_для_совпадения>"]
    ACTIONS
        [SET <переменная> = <значение>]
        [SET LOCAL <переменная> = <значение>] // Локальная переменная, доступная только в текущем правиле
        [LOG "<сообщение>"]
        [REMOVE_MATCH] // Удаляет совпавший текст из ответа LLM
        [REPLACE_MATCH WITH "<новый_текст>"] // Заменяет совпавший текст на новый
    END_ACTIONS
END_RULE
```

*   **`MATCH REGEX`**: Сопоставляет текст с регулярным выражением. Захваченные группы могут быть присвоены переменным с помощью `CAPTURE`.
*   **`MATCH TEXT`**: Сопоставляет точный текст.
*   **`ACTIONS`**: Блок, содержащий действия, которые будут выполнены при совпадении.
    *   **`SET <переменная> = <значение>`**: Присваивает значение переменной. Переменные могут быть числовыми, строковыми или булевыми.
    *   **`SET LOCAL <переменная> = <значение>`**: Присваивает значение локальной переменной, которая видна только внутри текущего правила.
    *   **`LOG "<сообщение>"`**: Выводит сообщение в лог (полезно для отладки).
    *   **`REMOVE_MATCH`**: Удаляет часть текста, которая совпала с `MATCH`.
    *   **`REPLACE_MATCH WITH "<новый_текст>"`**: Заменяет часть текста, которая совпала с `MATCH`, на указанный новый текст.

#### 8.1.2 Блок `DEBUG_DISPLAY`

Этот блок позволяет указать, какие переменные должны отображаться в пользовательском интерфейсе для отладки и мониторинга.

```
DEBUG_DISPLAY
    <Метка1>: <переменная1>
    "<Метка с пробелами>": <переменная2>
END_DEBUG_DISPLAY
```

*   **`<Метка>`**: Текст, который будет отображаться в UI. Может быть строкой в кавычках для меток с пробелами.
*   **`<переменная>`**: Имя переменной, значение которой будет отображаться.

### 8.2 Примеры Postscript-правил

**Пример 1: Обработка тега `<love>`**

Это правило ищет тег `<love>` с числовым значением, обновляет переменную `Love` и удаляет тег из ответа.

```
// Rule to handle a custom <love> tag
RULE LoveTagHandler
    MATCH REGEX "<love>([+-]?\d*\.?\d+)</love>" CAPTURE (love_value_str)
    ACTIONS
        SET LOCAL love_value = float(love_value_str)
        SET Love = Love + int(love_value)
        LOG "Character love updated by " + str(love_value) + ". New love: " + str(Love)
        REMOVE_MATCH // This will remove "<love>X</love>" from the response
    END_ACTIONS
END_RULE
```

**Пример 2: Установка булевой переменной по тегу**

Это правило устанавливает булеву переменную `secretExposed` в `True` при обнаружении тега `<secret_revealed>` и удаляет его.

```
// Rule for a boolean <secret_revealed> tag
RULE SecretExposedByTag
    MATCH TEXT "<secret_revealed>" // Simple text match
    ACTIONS
        SET secretExposed = True
        LOG "secretExposed set to True by <secret_revealed> tag."
        REMOVE_MATCH
    END_ACTIONS
END_RULE
```

**Пример 3: Замена текста**

Это правило заменяет фразу "Hello." на "Greetings and salutations!".

```
// Rule to modify response text without changing variables
RULE PoliteGreeting
    MATCH TEXT "Hello."
    ACTIONS
        REPLACE_MATCH WITH "Greetings and salutations!" // Replaces "Hello."
        LOG "Replaced 'Hello.' with a more formal greeting."
    END_ACTIONS
END_RULE
```

**Пример 4: Извлечение нескольких параметров**

Это правило извлекает имя действия и два параметра из XML-подобного тега.

```
// Rule to extract multiple parameters
RULE ActionParams
    MATCH REGEX "<action name=\"(\w+)\" value1=\"(\d+)\" value2=\"(true|false)\"/>" CAPTURE (action_name, val1_str, val2_str)
    ACTIONS
        SET current_action = action_name
        SET action_param1 = int(val1_str)
        SET action_param2 = (val2_str == "true")
        LOG "Parsed action: " + current_action + " with params " + str(action_param1) + ", " + str(action_param2)
        REMOVE_MATCH
    END_ACTIONS
END_RULE
```

---

## 9. Мини-проект (структура)

| Команда                    | Назначение                               |
|----------------------------|------------------------------------------|
| `SET var = expr`           | Записать значение.                      |
| `LOG expr`                 | Вывести в лог (для отладки).            |
| `IF / ELSEIF / ELSE / ENDIF` | Условные блоки.                       |
| `RETURN …`                 | Завершить скрипт и вернуть строку.      |

### 7.2 Что может стоять после `RETURN`

| Запись                               | Что вернётся (пример)                                       |
|--------------------------------------|-------------------------------------------------------------|
| `RETURN "Просто строка"`             | `Просто строка`                                             |
| `RETURN LOAD "Main/core.txt"`        | содержимое `core.txt`                                       |
| `RETURN LOAD Greeting FROM "Main/phrases.txt"` | `Привет, путник!` (содержимое секции `Greeting`) |
| `RETURN LOAD A FROM "a.txt" + LOAD B FROM "b.txt"` | склейка: содержимое секции `A` + содержимое секции `B` |

### 7.3 Мини-пример скрипта

```js
// разный текст в зависимости от настроения
IF mood > 70 THEN
    RETURN "Настроение отличное!"
ELSE
    RETURN "Настроение так себе…"
ENDIF
```

---

## 8. Мини-проект (структура)

```
Prompts/
└── Hero/
    ├── main_template.txt
    ├── Main/
    │   └── hero_core.txt
    └── Scripts/
        └── build_mood.script
```

### main_template.txt

```text
[<Main/hero_core.txt>]

Current mood:
[<Scripts/build_mood.script>]

{{SysInfo}}
```

### build_mood.script

```js
IF bravery > 50 THEN
    RETURN "Fearless"
ELSE
    RETURN "Cautious"
ENDIF
```

**Результат** (если bravery = 80):

```
(содержимое hero_core.txt)

Current mood:
Fearless

<текст вместо {{SysInfo}}>
```

## 9. Кастомные переменные

Начиная с версии v1 можно создать скрипт инициализации кастомных переменных.

Пример:
```js
// Scripts/init.script
LOG "Initialization of variables"

IF my_custom_variable == None THEN // При первом старте будет иметь значение None
	LOG "my_custom_variable is null: " + my_custom_variable
	SET my_custom_variable = "123" // заменяем на новое значение
	LOG "now it is: " + my_custom_variable // теперь переменная my_custom_variable = "123"
ELSE // При втором запуске/запросе переменная уже не будет пустой:
	LOG "my_custom_variable is not null" + my_custom_variable // Вывод: "123"
ENDIF
```

и подключить его в main_template.txt:
```
[<Scripts/init.script>]
```

---

## 10. Советы
1. `LOG` поможет понять, почему скрипт выбрал ту или иную ветку.  
2. Держите логику в `.script`, тексты — в `.txt`.  
3. Общие материалы кладите в `_CommonPrompts` / `_CommonScripts`.
