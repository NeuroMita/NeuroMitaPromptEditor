// frontend/src/components/Editor/TabManager.js
import React from 'react';
import EditorArea from './EditorArea';
// Removed: import { saveFileContent, getFileContent } from '../../services/api';

const tabManagerStyle = {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    backgroundColor: '#f0f0f0',
};

const tabBarStyle = {
    display: 'flex',
    borderBottom: '1px solid #ccc',
    padding: '5px 5px 0 5px',
    flexShrink: 0,
    overflowX: 'auto',
    backgroundColor: '#e9ecef', // Match EditorPage center panel
};

const tabStyle = (isActive, isModified) => ({
    padding: '8px 12px',
    marginRight: '2px',
    border: '1px solid #ccc',
    borderBottom: isActive ? '1px solid #fff' : '1px solid #ccc',
    backgroundColor: isActive ? '#fff' : '#e0e0e0',
    cursor: 'pointer',
    borderTopLeftRadius: '4px',
    borderTopRightRadius: '4px',
    position: 'relative',
    bottom: isActive ? '-1px' : '0',
    display: 'flex',
    alignItems: 'center',
    fontSize: '0.9em',
    fontStyle: isModified && isActive ? 'italic' : 'normal', // Italic for modified active tab
    color: isModified ? '#0056b3' : '#333', // Different color for modified
});

const tabContentStyle = {
    flex: 1,
    padding: '0',
    backgroundColor: '#fff',
    overflow: 'hidden',
};

const closeButtonStyle = {
    marginLeft: '8px',
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    padding: '0 4px',
    fontSize: '14px',
    lineHeight: '1',
    color: '#555',
    fontWeight: 'bold',
};

function TabManager({
    openFiles,
    activeFilePath,
    setActiveFilePath,
    onFileContentChange,
    onCloseTab, // From EditorPage
    onSaveTab   // From EditorPage
}) {

    const handleTabClick = (filePath) => {
        setActiveFilePath(filePath);
    };

    const handleInternalCloseTab = (e, filePathToClose) => {
        e.stopPropagation();
        if (onCloseTab) {
            onCloseTab(filePathToClose); // Let EditorPage handle the logic
        }
    };

    const handleEditorContentChange = (newContent) => {
        if (activeFilePath && onFileContentChange) {
            onFileContentChange(activeFilePath, newContent);
        }
    };

    const activeFile = openFiles.find(file => file.path === activeFilePath);

    return (
        <div style={tabManagerStyle}>
            <div style={tabBarStyle}>
                {openFiles.map(file => (
                    <div
                        key={file.path}
                        style={tabStyle(file.path === activeFilePath, file.isModified)}
                        onClick={() => handleTabClick(file.path)}
                        onDoubleClick={() => onSaveTab && onSaveTab(file.path)} // Save on double click
                        title={`${file.path}${file.isModified ? ' (modified)' : ''}\nDouble-click to save.`}
                    >
                        {file.name}{file.isModified ? '*' : ''}
                        <button
                            style={closeButtonStyle}
                            onClick={(e) => handleInternalCloseTab(e, file.path)}
                            aria-label={`Close ${file.name}`}
                            title="Close tab"
                        >
                            ×
                        </button>
                    </div>
                ))}
                {openFiles.length === 0 && <div style={{padding: '8px', fontSize: '0.9em', color: '#777'}}>No files open.</div>}
            </div>
            <div style={tabContentStyle}>
                {activeFile ? (
                    <EditorArea
                        key={activeFile.path}
                        filePath={activeFile.path}
                        initialContent={activeFile.content}
                        onContentChange={handleEditorContentChange}
                        // onSave is not directly passed; EditorPage handles save via Ctrl+S or buttons
                    />
                ) : (
                    <div style={{ padding: '20px', textAlign: 'center', color: '#777', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.1em' }}>
                        Select a file from the explorer to begin editing.
                    </div>
                )}
            </div>
        </div>
    );
}

export default TabManager;