// File: frontend\src\components\Editor\EditorArea.js
import React, {
    useState,
    useEffect,
    useMemo,
    useRef,
    useLayoutEffect,
    useCallback,
} from 'react';
import { generateHighlightedTokens } from '../../syntax/highlighter';
import '../../syntax/syntaxHighlighter.css';
import '../../styles/EditorArea.css';

const TAB_CHAR = '\t';
const TAB_SPACES = 4;
const COMMENT_PREFIX = '// ';
const COMMENT_PREFIX_NO_SPACE = '//';

function EditorArea({ filePath, initialContent, onContentChange }) {
    const [currentContent, setCurrentContent] = useState(initialContent || '');
    const textareaRef = useRef(null);
    const highlightOverlayRef = useRef(null);

    // refs для отложенного восстановления позиции курсора и скролла
    const pendingSelectionRef = useRef(null);
    const pendingScrollRef = useRef(null);

    useEffect(() => {
        setCurrentContent(initialContent || '');
        if (textareaRef.current) textareaRef.current.scrollTop = 0;
        if (highlightOverlayRef.current) highlightOverlayRef.current.scrollTop = 0;
    }, [initialContent, filePath]);

    useLayoutEffect(() => {
        const ta = textareaRef.current;
        const overlay = highlightOverlayRef.current;

        /* 1. Курсор / выделение */
        if (pendingSelectionRef.current && ta) {
            const { start, end } = pendingSelectionRef.current;
            ta.setSelectionRange(start, end);
            pendingSelectionRef.current = null;
        }

        /* 2. Скролл — отложенно, чтобы перебить автоскролл браузера */
        if (pendingScrollRef.current && ta) {
            const { top, left } = pendingScrollRef.current;
            requestAnimationFrame(() => {
                // Иногда к этому моменту компонент уже размонтирован – убеждаемся, что ref ещё валиден
                if (!textareaRef.current) return;
                textareaRef.current.scrollTop = top;
                textareaRef.current.scrollLeft = left;
                if (overlay) {
                    overlay.scrollTop = top;
                    overlay.scrollLeft = left;
                }
                pendingScrollRef.current = null;
            });
        }
    }, [currentContent]);

    const isTxtFile = useMemo(
        () => (filePath ? filePath.toLowerCase().endsWith('.txt') : false),
        [filePath]
    );

    const highlightedLines = useMemo(() => {
        return generateHighlightedTokens(currentContent, isTxtFile);
    }, [currentContent, isTxtFile]);

    /* ───────────────────────── helpers ───────────────────────── */
    const saveScrollPosition = () => {
        const ta = textareaRef.current;
        if (ta) {
            pendingScrollRef.current = {
                top: ta.scrollTop,
                left: ta.scrollLeft,
            };
        }
    };

    const updateContentAndSelection = useCallback(
        (newContent, newSelStart, newSelEnd) => {
            saveScrollPosition();
            setCurrentContent(newContent);
            if (onContentChange) onContentChange(newContent);
            pendingSelectionRef.current = { start: newSelStart, end: newSelEnd };
        },
        [onContentChange]
    );

    const getLineStart = (text, index) => {
        const nl = text.lastIndexOf('\n', index - 1);
        return nl === -1 ? 0 : nl + 1;
    };

    const getLineEnd = (text, index) => {
        const nl = text.indexOf('\n', index);
        return nl === -1 ? text.length : nl;
    };

    /* ─────────────────── indent / unindent ─────────────────── */
    const indentSelection = () => {
        const ta = textareaRef.current;
        const { selectionStart, selectionEnd } = ta;
        const selStartLineStart = getLineStart(currentContent, selectionStart);
        let selEndAdj = selectionEnd;
        if (selEndAdj > selectionStart && currentContent[selEndAdj - 1] === '\n')
            selEndAdj -= 1;
        const selEndLineEnd = getLineEnd(currentContent, selEndAdj);

        const block = currentContent.slice(selStartLineStart, selEndLineEnd);
        const lines = block.split('\n').map((l) => TAB_CHAR + l);
        const newBlock = lines.join('\n');

        const diff = newBlock.length - block.length;
        const newContent =
            currentContent.slice(0, selStartLineStart) +
            newBlock +
            currentContent.slice(selEndLineEnd);

        updateContentAndSelection(
            newContent,
            selectionStart + TAB_CHAR.length,
            selectionEnd + diff
        );
    };

    const unindentSelection = () => {
        const ta = textareaRef.current;
        const { selectionStart, selectionEnd } = ta;
        const selStartLineStart = getLineStart(currentContent, selectionStart);
        let selEndAdj = selectionEnd;
        if (selEndAdj > selectionStart && currentContent[selEndAdj - 1] === '\n')
            selEndAdj -= 1;
        const selEndLineEnd = getLineEnd(currentContent, selEndAdj);

        const block = currentContent.slice(selStartLineStart, selEndLineEnd);
        let removedFirst = 0;
        let removedTotal = 0;

        const lines = block.split('\n').map((line, idx) => {
            if (line.startsWith(TAB_CHAR)) {
                if (idx === 0) removedFirst = 1;
                removedTotal += 1;
                return line.slice(1);
            }
            let rmSpaces = 0;
            for (let i = 0; i < Math.min(TAB_SPACES, line.length); i++) {
                if (line[i] === ' ') rmSpaces += 1;
                else break;
            }
            if (idx === 0) removedFirst = rmSpaces;
            removedTotal += rmSpaces;
            return line.slice(rmSpaces);
        });

        const newBlock = lines.join('\n');
        const newContent =
            currentContent.slice(0, selStartLineStart) +
            newBlock +
            currentContent.slice(selEndLineEnd);

        updateContentAndSelection(
            newContent,
            Math.max(selectionStart - removedFirst, selStartLineStart),
            selectionEnd - removedTotal
        );
    };

    /* ───────────────────── commenting ───────────────────── */
    const toggleCommentSelection = () => {
        const ta = textareaRef.current;
        let { selectionStart, selectionEnd } = ta;
        const hasSel = selectionStart !== selectionEnd;

        let startLineStart = getLineStart(currentContent, selectionStart);
        let endPos = selectionEnd;
        if (endPos > selectionStart && currentContent[endPos - 1] === '\n')
            endPos -= 1;
        let endLineEnd = getLineEnd(currentContent, endPos);

        if (!hasSel) {
            startLineStart = getLineStart(currentContent, selectionStart);
            endLineEnd = getLineEnd(currentContent, selectionStart);
        }

        const block = currentContent.slice(startLineStart, endLineEnd);
        const lines = block.split('\n');

        const uncomment = lines[0]
            .trimStart()
            .startsWith(COMMENT_PREFIX_NO_SPACE);

        let diffFirst = 0;
        let diffTotal = 0;

        const processedLines = lines.map((line, idx) => {
            const trimmed = line.trimStart();
            const leadingWs = line.slice(0, line.length - trimmed.length);

            if (uncomment) {
                if (trimmed.startsWith(COMMENT_PREFIX)) {
                    if (idx === 0) diffFirst = -COMMENT_PREFIX.length;
                    diffTotal -= COMMENT_PREFIX.length;
                    return leadingWs + trimmed.slice(COMMENT_PREFIX.length);
                } else if (trimmed.startsWith(COMMENT_PREFIX_NO_SPACE)) {
                    if (idx === 0) diffFirst = -COMMENT_PREFIX_NO_SPACE.length;
                    diffTotal -= COMMENT_PREFIX_NO_SPACE.length;
                    return leadingWs + trimmed.slice(COMMENT_PREFIX_NO_SPACE.length);
                }
                return line;
            } else {
                const prefix = COMMENT_PREFIX_NO_SPACE + (trimmed ? ' ' : '');
                if (idx === 0) diffFirst = prefix.length;
                diffTotal += prefix.length;
                return leadingWs + prefix + trimmed;
            }
        });

        const newBlock = processedLines.join('\n');
        const newContent =
            currentContent.slice(0, startLineStart) +
            newBlock +
            currentContent.slice(endLineEnd);

        updateContentAndSelection(
            newContent,
            selectionStart + diffFirst,
            selectionEnd + diffTotal
        );
    };

    /* ────────────────── auto-indent after Enter ────────────────── */
    const applyAutoIndentAfterEnter = () => {
        const ta = textareaRef.current;
        const { selectionStart, selectionEnd } = ta;
        if (selectionStart !== selectionEnd) return;

        const prevLineStart = getLineStart(currentContent, selectionStart);
        const prevLine = currentContent.slice(prevLineStart, selectionStart);

        let leadingWs = '';
        for (const ch of prevLine) {
            if (ch === ' ' || ch === '\t') leadingWs += ch;
            else break;
        }

        const stripped = prevLine.trimEnd().toUpperCase();
        const needExtra = stripped.endsWith('THEN') || stripped === 'ELSE';
        const extra = needExtra ? TAB_CHAR : '';

        const insertStr = '\n' + leadingWs + extra;
        const newContent =
            currentContent.slice(0, selectionStart) +
            insertStr +
            currentContent.slice(selectionEnd);
        const newPos = selectionStart + insertStr.length;

        updateContentAndSelection(newContent, newPos, newPos);
    };

    /* ───────────────────── key handling ───────────────────── */
    const handleKeyDown = (event) => {
        const { key, ctrlKey, metaKey, shiftKey } = event;
        const ctrlOrCmd = ctrlKey || metaKey;

        // Ctrl+S / Cmd+S — даём глобальной обработке на верхнем уровне страницы
        if (ctrlOrCmd && key.toLowerCase() === 's') {
            event.preventDefault();
            return;
        }

        if (ctrlOrCmd && key === '/') {
            event.preventDefault();
            toggleCommentSelection();
            return;
        }

        if (key === 'Tab' && ctrlOrCmd) {
            event.preventDefault();
            if (
                textareaRef.current.selectionStart !==
                textareaRef.current.selectionEnd
            ) {
                indentSelection();
            } else {
                const { selectionStart, selectionEnd } = textareaRef.current;
                const newContent =
                    currentContent.slice(0, selectionStart) +
                    TAB_CHAR +
                    currentContent.slice(selectionEnd);
                const newPos = selectionStart + 1;
                updateContentAndSelection(newContent, newPos, newPos);
            }
            return;
        }

        if (key === 'Tab' && shiftKey && ctrlOrCmd) {
            event.preventDefault();
            if (
                textareaRef.current.selectionStart !==
                textareaRef.current.selectionEnd
            ) {
                unindentSelection();
            }
            return;
        }

        if (key === 'Tab' && !ctrlOrCmd) {
            if (
                textareaRef.current.selectionStart !==
                textareaRef.current.selectionEnd
            ) {
                event.preventDefault();
                if (shiftKey) unindentSelection();
                else indentSelection();
            }
            return;
        }

        if (key === 'Enter') {
            event.preventDefault();
            applyAutoIndentAfterEnter();
            return;
        }
    };

    /* ─────────────────── onChange / onScroll ─────────────────── */
    const handleChange = (event) => {
        saveScrollPosition();
        const newContent = event.target.value;
        setCurrentContent(newContent);
        if (onContentChange) onContentChange(newContent);
    };

    const handleScroll = (event) => {
        if (highlightOverlayRef.current) {
            highlightOverlayRef.current.scrollTop = event.target.scrollTop;
            highlightOverlayRef.current.scrollLeft = event.target.scrollLeft;
        }
    };

    /* ───────────────────── visual styles ───────────────────── */
    const sharedEditorStyles = {
        margin: 0,
        padding: '15px',
        fontFamily:
            "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace",
        fontSize: '14px',
        lineHeight: '1.6',
        tabSize: 4,
        WebkitTabSize: 4,
        MozTabSize: 4,
        OTabSize: 4,
        whiteSpace: 'pre',
        overflow: 'auto',
        boxSizing: 'border-box',
    };

    /* ─────────────────────── render ─────────────────────── */
    return (
        <div className="editorContainer">
            <textarea
                ref={textareaRef}
                className="editorTextarea actualEditorInput"
                value={currentContent}
                onChange={handleChange}
                onScroll={handleScroll}
                onKeyDown={handleKeyDown}
                spellCheck="false"
                aria-label={`Editing ${filePath || 'new file'}`}
                style={{
                    ...sharedEditorStyles,
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    zIndex: 1,
                    color: 'transparent',
                    caretColor: 'var(--text-primary)',
                    backgroundColor: 'transparent',
                    resize: 'none',
                    border: 'none',
                    outline: 'none',
                }}
            />
            <pre
                ref={highlightOverlayRef}
                className="editorTextareaHighlightOverlay"
                aria-hidden="true"
                style={{
                    ...sharedEditorStyles,
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    zIndex: 0,
                    pointerEvents: 'none',
                    backgroundColor: 'var(--bg-editor)',
                    color: 'var(--sh-default)',
                }}
            >
                <code>
                    {highlightedLines.map((lineTokens, lineIndex) => (
                        <React.Fragment key={lineIndex}>
                            {lineTokens.map((token, tokenIndex) => (
                                <span key={tokenIndex} className={token.className}>
                                    {token.text}
                                </span>
                            ))}
                            {lineIndex < highlightedLines.length - 1 ? '\n' : ''}
                        </React.Fragment>
                    ))}
                    {currentContent.length === 0 && '\n'}
                </code>
            </pre>
        </div>
    );
}

export default EditorArea;