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
const mobileBottomPaddingCompartment = new Compartment(); 

const MOBILE_BOTTOM_PADDING_VH = '40vh'; 
const MOBILE_PADDING_THRESHOLD_RATIO = 0.6;


function EditorArea({
  filePath,
  initialContent,
  onContentChange,
  lineWrapping,
  onSave,
  isMobileView
}) {
  const editorRef = useRef(null);
  const viewRef   = useRef(null);

  const isTxtFile = useMemo(
    () => (filePath ? filePath.toLowerCase().endsWith('.txt') : false),
    [filePath]
  );

  const indentEnterCommand = useCallback((view) => {
    insertNewlineAndIndent(view);
    const { state } = view;
    const head      = state.selection.main.head;
    const prevLine  = state.doc.lineAt(Math.max(0, head - 1));
    const prevTextU = prevLine.text.trimEnd().toUpperCase();
    const needTab   = !isTxtFile &&
                      (prevTextU.endsWith('THEN') || prevTextU === 'ELSE');
    if (needTab) {
      view.dispatch({
        changes: { from: head, insert: TAB_CHAR },
        selection: EditorSelection.cursor(head + 1),
        userEvent: 'input'
      });
    }
    return true;
  }, [isTxtFile]);

  const onChangeRef = useRef(onContentChange);
  useEffect(() => { onChangeRef.current = onContentChange; }, [onContentChange]);

  const onSaveRef = useRef(onSave);
  useEffect(() => { onSaveRef.current = onSave; }, [onSave]);

  const saveCommand = useCallback(() => {
    onSaveRef.current?.();
    return true;
  }, []);

  // Функция для обновления padding'а
  const updateMobilePadding = useCallback((view) => {
    if (!view) return;

    let needsPadding = false;
    if (isMobileView) {
      const contentHeight = view.contentHeight;
      const editorHeight = view.dom.clientHeight; // или view.scrollDOM.clientHeight
      if (editorHeight > 0 && contentHeight / editorHeight > MOBILE_PADDING_THRESHOLD_RATIO) {
        needsPadding = true;
      }
    }

    const paddingTheme = EditorView.theme({
      '.cm-scroller': {
        paddingBottom: needsPadding ? MOBILE_BOTTOM_PADDING_VH : '0px',
      }
    });

    view.dispatch({
      effects: mobileBottomPaddingCompartment.reconfigure(paddingTheme)
    });
  }, [isMobileView]);


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
        { key: 'Mod-s', run: saveCommand },
        { key: 'Enter', run: indentEnterCommand },
        { key: 'Tab',   run: indentMore,  shift: indentLess },
        { key: 'Mod-/', run: cmToggleComment },
        ...historyKeymap,
        ...completionKeymap,
        ...defaultKeymap,
      ]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged && viewRef.current) {
          onChangeRef.current?.(update.state.doc.toString());
        }
        // Обновляем padding при изменении документа или геометрии редактора
        if (update.docChanged || update.geometryChanged) {
          updateMobilePadding(update.view);
        }
      }),
      EditorView.theme({
        '&': { height: '100%' },
        '.cm-scroller': { overflow: 'auto' },
      }),
      mobileBottomPaddingCompartment.of(EditorView.theme({})), // Инициализация compartment
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
    
    // Первоначальное применение padding'а после монтирования
    updateMobilePadding(view);
    
    view.focus();

    return () => {
      viewRef.current?.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTxtFile, indentEnterCommand, updateMobilePadding]); // Добавили updateMobilePadding

  // Обновление padding'а при изменении isMobileView
  useEffect(() => {
    if (viewRef.current) {
      updateMobilePadding(viewRef.current);
    }
  }, [isMobileView, updateMobilePadding]);

  // Обновление lineWrapping
  useEffect(() => {
    if (viewRef.current) {
      viewRef.current.dispatch({
        effects: lineWrappingCompartment.reconfigure(
          lineWrapping ? EditorView.lineWrapping : []
        )
      });
    }
  }, [lineWrapping]);

  // Обновление initialContent
  useEffect(() => {
    if (viewRef.current &&
        initialContent !== viewRef.current.state.doc.toString()) {
      viewRef.current.dispatch({
        changes: { from: 0,
                   to: viewRef.current.state.doc.length,
                   insert: initialContent || '' },
        selection: EditorSelection.cursor(
          initialContent ? initialContent.length : 0
        ),
      });
    }
  }, [initialContent]);

  return <div ref={editorRef} className="editorAreaCodeMirrorContainer" />;
}

export default EditorArea;