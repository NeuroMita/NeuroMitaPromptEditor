// File: frontend\src\components\Editor\EditorArea.js
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { generateHighlightedTokens } from '../../syntax/highlighter';
import '../../syntax/syntaxHighlighter.css';
import '../../styles/EditorArea.css';

function EditorArea({ filePath, initialContent, onContentChange }) {
    const [currentContent, setCurrentContent] = useState(initialContent || '');
    const textareaRef = useRef(null);
    const highlightOverlayRef = useRef(null);

    useEffect(() => {
        setCurrentContent(initialContent || '');
        if (textareaRef.current) textareaRef.current.scrollTop = 0;
        if (highlightOverlayRef.current) highlightOverlayRef.current.scrollTop = 0;
    }, [initialContent, filePath]);

    const isTxtFile = useMemo(() => filePath ? filePath.toLowerCase().endsWith(".txt") : false, [filePath]);

    const highlightedLines = useMemo(() => {
        return generateHighlightedTokens(currentContent, isTxtFile);
    }, [currentContent, isTxtFile]);

    const handleChange = (event) => {
        const newContent = event.target.value;
        setCurrentContent(newContent);
        if (onContentChange) {
            onContentChange(newContent);
        }
    };

    const handleScroll = (event) => {
        if (highlightOverlayRef.current) {
            highlightOverlayRef.current.scrollTop = event.target.scrollTop;
            highlightOverlayRef.current.scrollLeft = event.target.scrollLeft;
        }
    };

    const sharedEditorStyles = {
        margin: 0,
        padding: '15px',
        fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace",
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

    // const handleLinkClick = (linkData) => {
    //     if (linkData) {
    //         alert(`Link clicked: ${linkData}. Navigation not implemented in this example.`);
    //     }
    // };

    return (
        <div className="editorContainer">
            <textarea
                ref={textareaRef}
                className="editorTextarea actualEditorInput"
                value={currentContent}
                onChange={handleChange}
                onScroll={handleScroll}
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
                    caretColor: 'var(--text-primary)', // Use CSS variable
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
                    backgroundColor: 'var(--bg-editor)', // Use CSS variable
                    color: 'var(--sh-default)', // Use CSS variable
                }}
            >
                <code>
                    {highlightedLines.map((lineTokens, lineIndex) => (
                        <React.Fragment key={lineIndex}>
                            {lineTokens.map((token, tokenIndex) => (
                                <span
                                    key={tokenIndex}
                                    className={token.className}
                                >
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