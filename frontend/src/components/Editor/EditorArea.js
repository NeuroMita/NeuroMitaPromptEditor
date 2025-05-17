import React, { useEffect, useMemo, useRef, useCallback } from 'react';
import { EditorState, Compartment, EditorSelection } from '@codemirror/state';
import {
  EditorView, keymap, lineNumbers, highlightActiveLineGutter,
  highlightSpecialChars, drawSelection, dropCursor,
  rectangularSelection, crosshairCursor, highlightActiveLine
} from '@codemirror/view';
import {
  history, historyKeymap, indentMore, indentLess,
  toggleComment as cmToggleComment,
  defaultKeymap,
  insertNewlineAndIndent
} from '@codemirror/commands';
import { bracketMatching, indentOnInput } from '@codemirror/language';
import { autocompletion, completionKeymap } from '@codemirror/autocomplete';

import { dslSupport, dslSyntaxHighlighting, dslEditorTheme } from '../../codemirror/dslSyntax';
import '../../styles/EditorArea.css';

const TAB_CHAR = '\t';
const lineWrappingCompartment = new Compartment();

function EditorArea({ filePath, initialContent, onContentChange, lineWrapping }) {
  const editorRef = useRef(null);
  const viewRef   = useRef(null);

  const isTxtFile = useMemo(
    () => (filePath ? filePath.toLowerCase().endsWith('.txt') : false),
    [filePath]
  );

  /* ----------------- ENTER с авто-отступом ----------------- */
  const indentEnterCommand = useCallback((view) => {
    /* Шаг 1 — стандартная новая строка + авто-отступ CodeMirror */
    insertNewlineAndIndent(view);

    /* Шаг 2 — возможно добавляем дополнительный таб */
    const { state } = view;
    const { head }  = state.selection.main;
    const prevLine = state.doc.lineAt(Math.max(0, head - 1));

    const prevTextUpper = prevLine.text.trimEnd().toUpperCase();
    const needExtraTab = !isTxtFile &&
                         (prevTextUpper.endsWith('THEN') || prevTextUpper === 'ELSE');

    if (needExtraTab) {
      view.dispatch({
        changes: { from: head, insert: TAB_CHAR },
        selection: EditorSelection.cursor(head + 1),
        userEvent: 'input'
      });
    }
    return true;
  }, [isTxtFile]);
  /* --------------------------------------------------------- */

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
      lineWrappingCompartment.of(lineWrapping ? EditorView.lineWrapping : []),
      dslSupport(isTxtFile),
      dslSyntaxHighlighting,
      dslEditorTheme,
      keymap.of([
        { key: 'Enter', run: indentEnterCommand },    // ← наше переопределение
        { key: 'Tab',   run: indentMore, shift: indentLess },
        { key: 'Mod-/', run: cmToggleComment },
        ...historyKeymap,
        ...completionKeymap,
        ...defaultKeymap,
      ]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged && viewRef.current) {
          onContentChange?.(update.state.doc.toString());
        }
      }),
      EditorView.theme({
        '&': { height: '100%' },
        '.cm-scroller': { overflow: 'auto' },
      })
    ];

    const startState = EditorState.create({
      doc: initialContent || '',
      extensions,
    });

    viewRef.current?.destroy();

    const view = new EditorView({
      state: startState,
      parent: editorRef.current,
    });
    viewRef.current = view;
    view.focus();

    return () => {
      viewRef.current?.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTxtFile, indentEnterCommand, onContentChange, lineWrapping]);

  /* ---- динамическое переключение переноса строк ---- */
  useEffect(() => {
    if (viewRef.current) {
      viewRef.current.dispatch({
        effects: lineWrappingCompartment.reconfigure(
          lineWrapping ? EditorView.lineWrapping : []
        )
      });
    }
  }, [lineWrapping]);

  /* ---- внешнее обновление initialContent ---- */
  useEffect(() => {
    if (viewRef.current && initialContent !== viewRef.current.state.doc.toString()) {
      viewRef.current.dispatch({
        changes: { from: 0, to: viewRef.current.state.doc.length, insert: initialContent || '' },
        selection: EditorSelection.cursor(initialContent ? initialContent.length : 0),
      });
    }
  }, [initialContent]);

  return <div ref={editorRef} className="editorAreaCodeMirrorContainer" />;
}

export default EditorArea;