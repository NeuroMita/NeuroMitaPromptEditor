// File: frontend\src\components\Editor\TabManager.js
import React from 'react';
import EditorArea from './EditorArea';
import '../../styles/TabManager.css';

function TabManager({
    openFiles,
    activeFilePath,
    setActiveFilePath,
    onFileContentChange,
    onCloseTab,
    onSaveTab
}) {

    const handleTabClick = (filePath) => {
        setActiveFilePath(filePath);
    };

    const handleInternalCloseTab = (e, filePathToClose) => {
        e.stopPropagation();
        if (onCloseTab) {
            onCloseTab(filePathToClose);
        }
    };

    const handleEditorContentChange = (newContent) => {
        if (activeFilePath && onFileContentChange) {
            onFileContentChange(activeFilePath, newContent);
        }
    };

    const activeFile = openFiles.find(file => file.path === activeFilePath);

    return (
        <div className="tabManager">
            <div className="tabBar">
                {openFiles.map(file => (
                    <div
                        key={file.path}
                        className={`tab ${file.path === activeFilePath ? 'active' : ''} ${file.isModified ? 'modified' : ''}`}
                        onClick={() => handleTabClick(file.path)}
                        onDoubleClick={() => onSaveTab && onSaveTab(file.path)}
                        title={`${file.path}${file.isModified ? ' (modified)' : ''}\nDouble-click to save.`}
                    >
                        <span className="tabName">{file.name}{file.isModified ? '*' : ''}</span>
                        <button
                            className="tabCloseButton"
                            onClick={(e) => handleInternalCloseTab(e, file.path)}
                            aria-label={`Close ${file.name}`}
                            title="Close tab"
                        >
                            ×
                        </button>
                    </div>
                ))}
                {openFiles.length === 0 && <div className="noFilesOpenMessage" style={{padding: '8px'}}>No files open.</div>}
            </div>
            <div className="tabContent">
                {activeFile ? (
                    <EditorArea
                        key={activeFile.path}
                        filePath={activeFile.path}
                        initialContent={activeFile.content}
                        onContentChange={handleEditorContentChange}
                    />
                ) : (
                    <div className="noFilesOpenMessage">
                        Select a file from the explorer to begin editing.
                    </div>
                )}
            </div>
        </div>
    );
}

export default TabManager;