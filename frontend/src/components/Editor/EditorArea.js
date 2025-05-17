import React, { useEffect, useMemo, useRef, useCallback } from 'react';
import { EditorState, Compartment } from '@codemirror/state'; // Импортируем Compartment
import { EditorView, keymap, lineNumbers, highlightActiveLineGutter, highlightSpecialChars, drawSelection, dropCursor, rectangularSelection, crosshairCursor, highlightActiveLine } from '@codemirror/view';
import { history, historyKeymap, indentMore, indentLess, toggleComment as cmToggleComment } from '@codemirror/commands';
import { bracketMatching, indentOnInput } from '@codemirror/language';
import { autocompletion, completionKeymap } from '@codemirror/autocomplete';

import { dslSupport, dslSyntaxHighlighting, dslEditorTheme } from '../../codemirror/dslSyntax';
import '../../styles/EditorArea.css';

const TAB_CHAR = '\t';

// Создаем Compartment для управления переносом строк
const lineWrappingCompartment = new Compartment();

function EditorArea({ filePath, initialContent, onContentChange, lineWrapping }) { // Принимаем новый проп
  const editorRef = useRef(null);
  const viewRef = useRef(null);

  const isTxtFile = useMemo(() => filePath ? filePath.toLowerCase().endsWith('.txt') : false, [filePath]);

  const indentEnterCommand = useCallback((targetView) => {
    // Используем targetView, переданный из keymap
    const { state, dispatch } = targetView;
    const changes = state.changeByRange(range => {
      const { from, to } = range;
      if (from !== to) {
        return { changes: { from, to, insert: "\n" }, range: { anchor: from + 1 } };
      }
      const line = state.doc.lineAt(from);
      const textBeforeCursor = line.text.substring(0, from - line.from);
      let leadingWhitespace = textBeforeCursor.match(/^(\s*)/)?.[1] || "";
      const prevLineTrimmedUpper = textBeforeCursor.trimEnd().toUpperCase();
      let extraIndent = "";
      if (!isTxtFile && (prevLineTrimmedUpper.endsWith("THEN") || prevLineTrimmedUpper === "ELSE")) {
        extraIndent = TAB_CHAR;
      }
      const insert = "\n" + leadingWhitespace + extraIndent;
      return {
        changes: { from, insert },
        range: { anchor: from + insert.length }
      };
    });
    dispatch(state.update(changes, { scrollIntoView: true, userEvent: "input" }));
    return true;
  }, [isTxtFile]);

  // useEffect для создания и уничтожения EditorView
  useEffect(() => {
    if (!editorRef.current) return;

    const extensions = [
      lineNumbers(),
      highlightActiveLineGutter(),
      highlightSpecialChars(),
      history(),
      drawSelection(),
      dropCursor(),
      EditorState.allowMultipleSelections.of(true),
      indentOnInput(),
      bracketMatching(),
      autocompletion(),
      rectangularSelection(),
      crosshairCursor(),
      highlightActiveLine(),
      // EditorView.lineWrapping, // Убрали отсюда, будем управлять через Compartment
      lineWrappingCompartment.of(lineWrapping ? EditorView.lineWrapping : []), // Инициализируем Compartment
      dslSupport(isTxtFile),
      dslSyntaxHighlighting,
      dslEditorTheme,
      keymap.of([
        ...historyKeymap,
        ...completionKeymap,
        { key: "Tab", run: indentMore, shift: indentLess },
        { key: "Mod-/", run: (view) => cmToggleComment(view) }, // Передаем view в cmToggleComment
        { key: "Enter", run: indentEnterCommand }, // indentEnterCommand теперь принимает view
      ]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged && viewRef.current) {
          const newDocString = update.state.doc.toString();
          if (onContentChange) {
             onContentChange(newDocString);
          }
        }
      }),
      EditorView.theme({
        "&": { height: "100%" },
        ".cm-scroller": { overflow: "auto" } // Важно для горизонтальной прокрутки
      })
    ];

    const startState = EditorState.create({
      doc: initialContent || '',
      extensions: extensions,
    });

    if (viewRef.current) {
      viewRef.current.destroy();
    }

    const view = new EditorView({
      state: startState,
      parent: editorRef.current,
    });
    viewRef.current = view;
    view.focus();

    return () => {
      if (viewRef.current) {
        viewRef.current.destroy();
        viewRef.current = null;
      }
    };
  // Зависимости для пересоздания EditorView.
  // lineWrapping не должен вызывать полное пересоздание, им управляет другой useEffect.
  // Но если EditorArea пересоздается по другой причине (например, смена filePath/initialContent),
  // то Compartment должен быть инициализирован с текущим значением lineWrapping.
  }, [initialContent, isTxtFile, indentEnterCommand, onContentChange, lineWrapping]);


  // useEffect для динамического изменения lineWrapping
  useEffect(() => {
    if (viewRef.current) {
      viewRef.current.dispatch({
        effects: lineWrappingCompartment.reconfigure(lineWrapping ? EditorView.lineWrapping : [])
      });
    }
  }, [lineWrapping]); // Этот эффект зависит только от lineWrapping

  // useEffect для обновления контента, если он изменился извне
  useEffect(() => {
    if (viewRef.current && initialContent !== viewRef.current.state.doc.toString()) {
      viewRef.current.dispatch({
        changes: { from: 0, to: viewRef.current.state.doc.length, insert: initialContent || '' },
      });
    }
  }, [initialContent]);


  return <div ref={editorRef} className="editorAreaCodeMirrorContainer" />;
}

export default EditorArea;