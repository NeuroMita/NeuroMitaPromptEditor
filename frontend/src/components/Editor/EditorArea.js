// File: frontend\src\components\Editor\EditorArea.js
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { generateHighlightedTokens } from '../../syntax/highlighter';
import '../../syntax/syntaxHighlighter.css';
import '../../styles/EditorArea.css';

function EditorArea({ filePath, initialContent, onContentChange }) {
    const [currentContent, setCurrentContent] = useState(initialContent || '');
    const textareaRef = useRef(null);
    const highlightOverlayRef = useRef(null);

    // Update internal state if initialContent or filePath changes (e.g., switching tabs)
    useEffect(() => {
        setCurrentContent(initialContent || '');
        // Reset scroll positions when content/file changes
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
            onContentChange(newContent); // Propagate change to parent (TabManager)
        }
    };

    const handleScroll = (event) => {
        // Sync scroll position from textarea to overlay
        if (highlightOverlayRef.current) {
            highlightOverlayRef.current.scrollTop = event.target.scrollTop;
            highlightOverlayRef.current.scrollLeft = event.target.scrollLeft;
        }
    };

    // Ensure consistent font, padding, etc. between textarea and overlay
    // These styles are crucial for alignment.
    const sharedEditorStyles = {
        margin: 0,
        padding: '15px', // Must match editorTextarea padding in EditorArea.css
        fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace",
        fontSize: '14px', // Must match editorTextarea font-size
        lineHeight: '1.6', // Must match editorTextarea line-height
        tabSize: 4,
        WebkitTabSize: 4,
        MozTabSize: 4,
        OTabSize: 4,
        whiteSpace: 'pre',
        overflow: 'auto', // Important for the overlay's pre/code
        boxSizing: 'border-box',
    };

    const handleLinkClick = (linkData) => {
        if (linkData) {
            alert(`Link clicked: ${linkData}. Navigation not implemented in this example.`);
            // Potentially call a prop to handle opening the link
        }
    };


    return (
        <div className="editorContainer"> {/* This container is already flex: 1, display: flex etc. */}
            <textarea
                ref={textareaRef}
                className="editorTextarea actualEditorInput" // Added new class for specific styling
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
                    zIndex: 1, // Textarea is "behind" for typing
                    color: 'transparent', // Make actual text invisible
                    // caretColor: '#abb2bf', // Or your desired caret color for dark theme
                    caretColor: 'white', // Make caret visible against dark background
                    backgroundColor: 'transparent', // Ensure it doesn't hide the overlay below
                    resize: 'none',
                    border: 'none',
                    outline: 'none',
                }}
            />
            <pre
                ref={highlightOverlayRef}
                className="editorTextareaHighlightOverlay" // New class for specific styling
                aria-hidden="true" // Hide from screen readers as it's decorative
                style={{
                    ...sharedEditorStyles,
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    zIndex: 0, // Overlay is "behind" the transparent textarea input layer
                    pointerEvents: 'none', // Allows clicks to pass through to textarea if needed, but links won't work
                                          // If links need to be clickable, zIndex of textarea should be 0, overlay 1, and pointerEvents on overlay 'auto'
                    backgroundColor: '#282c34', // Actual background color from EditorArea.css for editorTextarea
                    color: '#abb2bf',       // Default text color from EditorArea.css for editorTextarea
                }}
            >
                <code>
                    {highlightedLines.map((lineTokens, lineIndex) => (
                        <React.Fragment key={lineIndex}>
                            {lineTokens.map((token, tokenIndex) => (
                                <span
                                    key={tokenIndex}
                                    className={token.className}
                                    // onClick handling for links needs careful z-index and pointerEvents management
                                    // If overlay is on top with pointerEvents: 'auto', this would work:
                                    // onClick={token.isLink ? () => handleLinkClick(token.linkData) : undefined}
                                    // style={token.isLink ? { pointerEvents: 'auto', cursor: 'pointer'} : {}}
                                >
                                    {token.text}
                                </span>
                            ))}
                            {/* Add newline character for rendering, except for the last line */}
                            {lineIndex < highlightedLines.length - 1 ? '\n' : ''}
                        </React.Fragment>
                    ))}
                    {/* If content is empty, ensure overlay doesn't collapse and matches textarea height for one line */}
                    {currentContent.length === 0 && '\n'}
                </code>
            </pre>
        </div>
    );
}

export default EditorArea;