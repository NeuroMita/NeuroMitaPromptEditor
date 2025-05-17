import { Tag, tags as t } from '@lezer/highlight';
import { HighlightStyle, syntaxHighlighting, LanguageSupport } from '@codemirror/language';
import { EditorView } from '@codemirror/view';
import { StreamLanguage } from '@codemirror/language';
import { currentTheme } from '../syntax/syntaxStyles';

// Ключи этого объекта будут использоваться как имена токенов
export const dslTagNames = {
  placeholderLink: "placeholderLink",
  specialTag: "specialTag",
  loadCommand: "loadCommand",
  sectionMarker: "sectionMarker",
  insert: "insert",
  tripleQuoteString: "tripleQuoteString",
  dslKeyword: "dslKeyword",
  defaultText: "defaultText",
  // Стандартные теги, если мы хотим их переопределить или использовать как уникальные имена
  lineComment: "lineComment",
  string: "string",
  number: "number",
};

// Создаем объекты Tag, используя стандартные теги Lezer как основу, где это возможно
export const dslTags = {
  [dslTagNames.placeholderLink]: Tag.define(t.link),
  [dslTagNames.specialTag]: Tag.define(t.tagName),
  [dslTagNames.loadCommand]: Tag.define(t.strong), // Был t.strong, соответствует LoadCommand стилю
  [dslTagNames.sectionMarker]: Tag.define(t.heading),
  [dslTagNames.insert]: Tag.define(t.atom),
  [dslTagNames.tripleQuoteString]: Tag.define(t.string), // Был t.string, соответствует TripleQuoteString стилю
  [dslTagNames.dslKeyword]: Tag.define(t.keyword), // Был t.keyword, соответствует Keyword стилю
  [dslTagNames.defaultText]: Tag.define(),
  // Стандартные теги, которые мы будем использовать напрямую
  [dslTagNames.lineComment]: t.lineComment,
  [dslTagNames.string]: t.string,
  [dslTagNames.number]: t.number,
};


const darkThemeColors = {
  background: "var(--cm-background, #282c34)",
  foreground: "var(--cm-foreground, #ABB2BF)",
  caret: "var(--cm-caret, #D4D4D4)",
  selection: "var(--cm-selection, #3E4451)",
  lineHighlight: "var(--cm-line-highlight, rgba(100,100,100,0.1))",
  gutterBackground: "var(--cm-gutter-background, #282c34)",
  gutterForeground: "var(--cm-gutter-foreground, #606060)",
  gutterBorder: "var(--cm-gutter-border, #3b4048)",
};

const dslHighlightStyleObject = HighlightStyle.define([
  {
    tag: dslTags[dslTagNames.dslKeyword],
    color: currentTheme.Keyword.color,
    fontWeight: currentTheme.Keyword.fontWeight,
    class: currentTheme.Keyword.className
  },
  {
    tag: dslTags[dslTagNames.loadCommand],
    color: currentTheme.LoadCommand.color,
    fontWeight: currentTheme.LoadCommand.fontWeight,
    class: currentTheme.LoadCommand.className
  },
  {
    tag: dslTags[dslTagNames.placeholderLink],
    color: currentTheme.PlaceholderLink.color,
    textDecoration: currentTheme.PlaceholderLink.textDecoration,
    cursor: "pointer",
    class: currentTheme.PlaceholderLink.className
  },
  {
    tag: dslTags[dslTagNames.lineComment], // Используем наш dslTag для lineComment
    color: currentTheme.Comment.color,
    fontStyle: currentTheme.Comment.fontStyle,
    class: currentTheme.Comment.className
  },
  {
    tag: dslTags[dslTagNames.string], // Используем наш dslTag для string
    color: currentTheme.String.color,
    class: currentTheme.String.className
  },
  {
    tag: dslTags[dslTagNames.tripleQuoteString],
    color: currentTheme.TripleQuoteString.color,
    class: currentTheme.TripleQuoteString.className
  },
  {
    tag: dslTags[dslTagNames.number], // Используем наш dslTag для number
    color: currentTheme.Number.color,
    class: currentTheme.Number.className
  },
  {
    tag: dslTags[dslTagNames.specialTag],
    color: currentTheme.SpecialTag.color,
    class: currentTheme.SpecialTag.className
  },
  {
    tag: dslTags[dslTagNames.sectionMarker],
    color: currentTheme.SectionMarker.color,
    fontWeight: currentTheme.SectionMarker.fontWeight,
    class: currentTheme.SectionMarker.className
  },
  {
    tag: dslTags[dslTagNames.insert],
    color: currentTheme.Insert.color,
    fontWeight: currentTheme.Insert.fontWeight,
    class: currentTheme.Insert.className
  },
  {
    tag: t.keyword, // Общий t.keyword, если вдруг где-то используется напрямую
    color: currentTheme.Keyword.color,
    fontWeight: currentTheme.Keyword.fontWeight,
    class: currentTheme.Keyword.className
  },
  {
    tag: [t.name, t.variableName, t.propertyName, t.className, t.labelName, t.operator, t.punctuation, t.meta, t.character, t.self],
    color: currentTheme.Default.color,
    class: currentTheme.Default.className
  },
  {
    tag: dslTags[dslTagNames.defaultText],
    color: currentTheme.Default.color,
    class: currentTheme.Default.className
  },
]);

export const dslSyntaxHighlighting = syntaxHighlighting(dslHighlightStyleObject);

const TRIPLE_QUOTE_MARKER = '"""';
const DSL_KEYWORDS_PATTERN_STR = "\\b(IF|THEN|ELSEIF|ELSE|ENDIF|SET|RETURN|LOG|AND|OR|TRUE|FALSE|NONE)\\b";
const TXT_SPECIFIC_COMMANDS_PATTERN_STR = "\\b(LOAD)\\b";

const getDslRules = (isTxtFile) => {
  const rules = [
    { id: "lineComment", regex: /\/\/[^\n]*/, tokenName: dslTagNames.lineComment },
    { id: "string", regex: /(".*?"|'.*?')/, tokenName: dslTagNames.string },
  ];

  if (isTxtFile) {
    rules.push({ id: "txtLoad", regex: new RegExp(TXT_SPECIFIC_COMMANDS_PATTERN_STR, 'i'), tokenName: dslTagNames.loadCommand });
  } else {
    rules.push({ id: "loadCommand", regex: /\bLOAD\s+[A-Z0-9_]+\s+FROM\s+['"][^'"]+['"]/i, tokenName: dslTagNames.loadCommand });
    rules.push({ id: "dslKeyword", regex: new RegExp(DSL_KEYWORDS_PATTERN_STR, 'i'), tokenName: dslTagNames.dslKeyword });
  }

  rules.push(
    { id: "sectionMarker", regex: /\[(?:#|\/)\s*[A-Z0-9_]+\s*]/i, tokenName: dslTagNames.sectionMarker },
    { id: "insert", regex: /\{\{[A-Z0-9_]+\}\}/i, tokenName: dslTagNames.insert },
    { id: "specialTag", regex: /<[/!]?[a-zA-Z_][^>]*>/, tokenName: dslTagNames.specialTag },
    { id: "placeholderLink", regex: /(\[<)([^\]>]+?\.(?:script|txt))(>\])/, tokenName: dslTagNames.placeholderLink },
    { id: "number", regex: /\b\d+(\.\d+)?\b/, tokenName: dslTagNames.number }
  );
  return rules;
};


const createDslStreamLanguage = (isTxtFile) => {
  const currentRules = getDslRules(isTxtFile);

  // tokenTable теперь сопоставляет уникальные строковые имена (из dslTagNames) с объектами Tag (из dslTags)
  const tokenTable = {};
  for (const nameKey in dslTagNames) {
      const tokenNameString = dslTagNames[nameKey]; // "dslKeyword", "string", etc.
      tokenTable[tokenNameString] = dslTags[tokenNameString]; // dslTags["dslKeyword"] (объект Tag)
  }
  // Убедимся, что все теги, используемые в dslHighlightStyleObject, есть в tokenTable
  // и что getDslRules возвращает правильные tokenName.

  console.log("Initializing StreamLanguage. isTxtFile:", isTxtFile);
  console.log("Current rules:", currentRules.map(r => ({id: r.id, regex: r.regex.source, tokenName: r.tokenName})));
  console.log("Token table:", tokenTable);


  return StreamLanguage.define({
    startState: function() {
      return { inTripleQuote: false };
    },
    token: function(stream, state) {
      if (state.inTripleQuote) {
        // ... (логика тройных кавычек остается прежней)
        let closed = false;
        let escaped = false;
        while (!stream.eol()) {
          const char = stream.next();
          if (!escaped && char === TRIPLE_QUOTE_MARKER[0]) {
            if (stream.match(TRIPLE_QUOTE_MARKER.substring(1))) {
              closed = true;
              state.inTripleQuote = false;
              break;
            }
          }
          escaped = !escaped && char === '\\';
        }
        return dslTagNames.tripleQuoteString; // Возвращаем строковое имя
      }

      if (stream.match(TRIPLE_QUOTE_MARKER)) {
        state.inTripleQuote = true;
        return dslTagNames.tripleQuoteString; // Возвращаем строковое имя
      }

      for (const rule of currentRules) {
        if (rule.regex.global) {
            rule.regex.lastIndex = 0;
        }
        if (stream.match(rule.regex)) {
          // Теперь rule.tokenName это строка типа "dslKeyword"
          console.log(`>>> Rule [${rule.id || 'no-id'}] matched text: "${stream.current()}", assigned tokenName: ${rule.tokenName}`);
          return rule.tokenName; // Возвращаем строковое имя
        }
      }

      if (!stream.eol()) {
        stream.next();
      }
      
      return isTxtFile ? dslTagNames.defaultText : null; // Возвращаем строковое имя или null
    },
    languageData: {
      commentTokens: { line: "//" }
    },
    tokenTable // tokenTable теперь правильно сопоставляет "dslKeyword" -> Tag объект
  });
};

export const dslEditorTheme = EditorView.theme({
  "&": {
    color: darkThemeColors.foreground,
    backgroundColor: darkThemeColors.background,
    fontFamily: "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,Courier,monospace",
    fontSize: "14px",
    lineHeight: "1.6",
    height: "100%",
  },
  ".cm-content": {
    caretColor: darkThemeColors.caret,
    fontFamily: "inherit",
    fontSize: "inherit",
    lineHeight: "inherit",
    tabSize: 4,
  },
  "&.cm-editor.cm-focused": {
    outline: "none !important",
  },
  ".cm-cursor, &.cm-focused .cm-cursor": {
     borderLeftColor: darkThemeColors.caret,
  },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": {
    backgroundColor: `${darkThemeColors.selection} !important`,
  },
  ".cm-gutters": {
    backgroundColor: darkThemeColors.gutterBackground,
    color: darkThemeColors.gutterForeground,
    borderRight: `1px solid ${darkThemeColors.gutterBorder}`
  },
  ".cm-lineNumbers .cm-gutterElement": {
    padding: "0 10px",
    minWidth: "30px",
    textAlign: "right",
  },
  ".cm-activeLine": {
    backgroundColor: darkThemeColors.lineHighlight
  },
  ".cm-activeLineGutter": {
    backgroundColor: darkThemeColors.lineHighlight
  }
}, { dark: true });

export function dslSupport(isTxtFile = false) {
  console.log("Creating dslSupport, isTxtFile:", isTxtFile);
  const lang = createDslStreamLanguage(isTxtFile);
  return new LanguageSupport(lang);
}