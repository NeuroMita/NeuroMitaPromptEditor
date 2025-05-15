// frontend/src/components/Editor/EditorArea.js
import React, { useState, useEffect } from 'react';

const editorAreaStyle = {
    width: '100%',
    height: 'calc(100% - 40px)', // Adjust if you have a save button or other controls within
    boxSizing: 'border-box',
    border: 'none',
    padding: '10px',
    fontFamily: 'monospace',
    fontSize: '14px',
    lineHeight: '1.5',
    backgroundColor: '#282c34', // Dark background similar to original
    color: '#abb2bf',       // Light text color
    resize: 'none',
};

const editorContainerStyle = {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
};

function EditorArea({ filePath, initialContent, onContentChange, onSave }) {
    const [content, setContent] = useState(initialContent || '');

    useEffect(() => {
        setContent(initialContent || '');
    }, [initialContent, filePath]); // Reset content when file path or initial content changes

    const handleChange = (event) => {
        const newContent = event.target.value;
        setContent(newContent);
        if (onContentChange) {
            onContentChange(newContent);
        }
    };

    return (
        <div style={editorContainerStyle}>
            <textarea
                style={editorAreaStyle}
                value={content}
                onChange={handleChange}
                spellCheck="false"
                aria-label={`Editing ${filePath || 'new file'}`}
            />
            {/* 
            // Optional: Add a save button per editor instance if desired
            // Usually, save is handled globally or per tab
            {onSave && (
                <button onClick={() => onSave(filePath, content)} style={{marginTop: '5px'}}>
                    Save this file
                </button>
            )}
            */}
        </div>
    );
}

export default EditorArea;