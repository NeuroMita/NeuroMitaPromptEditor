import React, { useState, useEffect, useCallback } from 'react';
import { useAppContext } from '../contexts/AppContext';

import FileTreePanel from '../components/FileTree/FileTreePanel';
import TabManager from '../components/Editor/TabManager';
import DslVariablesPanel from '../components/Panels/DslVariablesPanel';
import LogPanel from '../components/Panels/LogPanel';
import DslResultModal from '../components/Panels/DslResultModal';

import {
    generatePrompt,
    getFileContent,
    saveFileContent as apiSaveFile,
    // createItem, renameItem, deleteItem are handled in FileTreePanel for now
} from '../services/api';

// Basic styling for layout (you'll want to use CSS for this properly)
const editorPageStyle = {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif", // A more standard font
};

const headerStyle = {
    padding: '10px 15px',
    borderBottom: '1px solid #ccc',
    backgroundColor: '#f8f9fa',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0,
};

const headerTitleStyle = {
    margin: 0,
    fontSize: '1.2em',
};

const headerActionsStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '10px', // Space between buttons
};

const mainContentStyle = {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
};

const leftPanelStyle = {
    width: '280px',
    minWidth: '200px', // Prevent excessive shrinking
    borderRight: '1px solid #ccc',
    overflowY: 'auto',
    backgroundColor: '#fff', // Lighter background for file tree
    // padding: '10px', // FileTreePanel will handle its own padding
    display: 'flex',
    flexDirection: 'column',
};

const centerPanelStyle = {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    backgroundColor: '#e9ecef', // Slightly different background for tab area
};

const rightPanelStyle = {
    width: '320px',
    minWidth: '250px',
    borderLeft: '1px solid #ccc',
    overflowY: 'auto',
    backgroundColor: '#fff',
    // padding: '10px', // DslVariablesPanel will handle its own padding
    display: 'flex',
    flexDirection: 'column',
};

const bottomPanelStyle = {
    height: '250px',
    minHeight: '150px', // Prevent excessive shrinking
    borderTop: '1px solid #ccc',
    overflowY: 'auto',
    backgroundColor: '#fff',
    // padding: '10px', // LogPanel will handle its own padding
    display: 'flex',
    flexDirection: 'column',
};

const buttonStyle = {
    padding: '8px 12px',
    border: '1px solid #007bff',
    backgroundColor: '#007bff',
    color: 'white',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '0.9em',
};

const buttonDisabledStyle = {
    ...buttonStyle,
    backgroundColor: '#6c757d',
    borderColor: '#6c757d',
    cursor: 'not-allowed',
};


function EditorPage() {
    const { promptsRoot, selectedCharacterId, setSelectedCharacterId, isLoading: appContextLoading, error: appContextError } = useAppContext();

    // File and Tab State
    const [openFiles, setOpenFiles] = useState([]); // { path: string, content: string, name: string, isModified: bool, originalContent: string }
    const [activeFilePath, setActiveFilePath] = useState(null);
    const [fileTreeKey, setFileTreeKey] = useState(Date.now()); // To force re-render/re-fetch of FileTree

    // DSL State
    const [dslVariables, setDslVariables] = useState({});
    const [dslResult, setDslResult] = useState({ show: false, title: '', content: '' });

    // Log State
    const [logs, setLogs] = useState([]);

    // Loading/Error State for page-specific actions
    const [isPageLoading, setIsPageLoading] = useState(false);
    const [pageError, setPageError] = useState(null);


    // --- File Operations ---
    const handleOpenFile = useCallback(async (fileNode) => { // fileNode: { name, path, is_dir }
        if (fileNode.is_dir) {
            // Navigation within FileTreePanel is handled by its own state now
            return;
        }

        const existingFile = openFiles.find(f => f.path === fileNode.path);
        if (existingFile) {
            setActiveFilePath(fileNode.path);
            return;
        }

        setIsPageLoading(true);
        setPageError(null);
        try {
            const fileData = await getFileContent(fileNode.path);
            setOpenFiles(prevFiles => [
                ...prevFiles,
                {
                    path: fileData.path,
                    name: fileNode.name,
                    content: fileData.content,
                    originalContent: fileData.content, // Store original for isModified check
                    isModified: false
                }
            ]);
            setActiveFilePath(fileData.path);
        } catch (err) {
            console.error("Error opening file:", err);
            setPageError(`Failed to open ${fileNode.name}: ${err.message}`);
            alert(`Failed to open ${fileNode.name}: ${err.message}`);
        } finally {
            setIsPageLoading(false);
        }
    }, [openFiles]);

    const handleFileContentChange = useCallback((filePath, newContent) => {
        setOpenFiles(prevFiles =>
            prevFiles.map(f =>
                f.path === filePath ? { ...f, content: newContent, isModified: newContent !== f.originalContent } : f
            )
        );
    }, []);

    const handleSaveFile = useCallback(async (filePathToSave) => {
        const path = filePathToSave || activeFilePath;
        if (!path) return;

        const fileToSave = openFiles.find(f => f.path === path);
        if (!fileToSave || !fileToSave.isModified) {
            if (fileToSave && !fileToSave.isModified) console.log(`${fileToSave.name} has no changes to save.`);
            return;
        }

        setIsPageLoading(true);
        setPageError(null);
        try {
            await apiSaveFile(fileToSave.path, fileToSave.content);
            setOpenFiles(prevFiles =>
                prevFiles.map(f =>
                    f.path === fileToSave.path ? { ...f, isModified: false, originalContent: f.content } : f
                )
            );
            // No alert needed for single save, visual indication (asterisk removal) is enough
            console.log(`${fileToSave.name} saved successfully.`);
        } catch (err) {
            console.error("Error saving file:", err);
            setPageError(`Failed to save ${fileToSave.name}: ${err.message}`);
            alert(`Failed to save ${fileToSave.name}: ${err.message}`);
        } finally {
            setIsPageLoading(false);
        }
    }, [activeFilePath, openFiles]);

    const handleSaveAllFiles = useCallback(async () => {
        const modifiedFiles = openFiles.filter(f => f.isModified);
        if (modifiedFiles.length === 0) {
            alert("No files have unsaved changes.");
            return;
        }

        setIsPageLoading(true);
        setPageError(null);
        let allSaved = true;
        try {
            for (const fileToSave of modifiedFiles) {
                await apiSaveFile(fileToSave.path, fileToSave.content);
                // Update state individually to reflect changes immediately if one fails
                setOpenFiles(prevFiles =>
                    prevFiles.map(f =>
                        f.path === fileToSave.path ? { ...f, isModified: false, originalContent: f.content } : f
                    )
                );
            }
            alert("All modified files saved successfully!");
        } catch (err) {
            console.error("Error saving all files:", err);
            setPageError(`Failed to save some files: ${err.message}. Check console for details.`);
            alert(`Failed to save some files: ${err.message}. Check console for details.`);
            allSaved = false;
        } finally {
            setIsPageLoading(false);
        }
        return allSaved;
    }, [openFiles]);

    const handleCloseTab = useCallback((filePathToClose, forceClose = false) => {
        const fileToClose = openFiles.find(f => f.path === filePathToClose);

        if (fileToClose && fileToClose.isModified && !forceClose) {
            if (!window.confirm(`File ${fileToClose.name} has unsaved changes. Close anyway?`)) {
                return false; // Indicate closure was cancelled
            }
        }

        setOpenFiles(prevFiles => prevFiles.filter(file => file.path !== filePathToClose));

        if (activeFilePath === filePathToClose) {
            const newOpenFiles = openFiles.filter(file => file.path !== filePathToClose); // Re-filter to get the correct list
            setActiveFilePath(newOpenFiles.length > 0 ? newOpenFiles[newOpenFiles.length - 1].path : null); // Activate last opened or null
        }
        return true; // Indicate successful closure
    }, [activeFilePath, openFiles]);

    // --- File Tree Callbacks ---
    const refreshFileTree = useCallback(() => {
        setFileTreeKey(Date.now()); // Changing the key forces FileTreePanel to re-mount or re-fetch
    }, []);

    const handleFileRenamedInTree = useCallback((oldPath, newPath, newName) => {
        refreshFileTree();
        // Update open files if the renamed file was open
        setOpenFiles(prevOpenFiles => {
            return prevOpenFiles.map(file => {
                if (file.path === oldPath) {
                    return { ...file, path: newPath, name: newName };
                }
                return file;
            });
        });
        if (activeFilePath === oldPath) {
            setActiveFilePath(newPath);
        }
    }, [activeFilePath, refreshFileTree]);

    const handleFileDeletedInTree = useCallback((deletedPath) => {
        refreshFileTree();
        // Close tab if the deleted file was open
        if (openFiles.some(f => f.path === deletedPath)) {
            handleCloseTab(deletedPath, true); // Force close without prompt
        }
    }, [openFiles, handleCloseTab, refreshFileTree]);


    // --- DSL Operations ---
    const handleRunDsl = useCallback(async () => {
        if (!selectedCharacterId) {
            alert("Please select a character first.");
            return;
        }
        // Check for unsaved changes and prompt to save
        const modifiedFile = openFiles.find(f => f.isModified);
        if (modifiedFile) {
            if (window.confirm("You have unsaved changes. Save them before generating the prompt?")) {
                const saved = await handleSaveAllFiles();
                if (!saved) {
                    if (!window.confirm("Some files could not be saved. Continue generating prompt anyway?")) {
                        return;
                    }
                }
            } else {
                 if (!window.confirm("Generate prompt with unsaved changes? This might lead to unexpected results.")) {
                    return;
                 }
            }
        }


        setIsPageLoading(true);
        setPageError(null);
        setLogs([]); // Clear previous logs
        try {
            const tags = { SYS_INFO: "Generated from Web Editor." }; // Example
            const result = await generatePrompt(selectedCharacterId, dslVariables, tags);
            setDslResult({ show: true, title: `DSL Result: ${selectedCharacterId}`, content: result.generated_prompt });
            setLogs(result.logs || []);
        } catch (err) {
            console.error("Error generating prompt:", err);
            setPageError(`Error generating prompt: ${err.message}`);
            alert(`Error generating prompt: ${err.message}`);
            setLogs(prev => [...prev, { level: "ERROR", message: `API Error: ${err.message}`, name: "API_CLIENT" }]);
        } finally {
            setIsPageLoading(false);
        }
    }, [selectedCharacterId, dslVariables, openFiles, handleSaveAllFiles]);


    // --- Log Operations ---
    const handleClearLogs = useCallback(() => {
        setLogs([]);
    }, []);

    // --- Effects ---
    // Save on Ctrl+S / Cmd+S
    useEffect(() => {
        const handleKeyDown = (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === 's') {
                event.preventDefault();
                if (activeFilePath) {
                    handleSaveFile(activeFilePath);
                }
            }
            if ((event.ctrlKey || event.metaKey) && event.altKey && event.key === 's') {
                event.preventDefault();
                handleSaveAllFiles();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, [activeFilePath, handleSaveFile, handleSaveAllFiles]);


    if (appContextLoading) return <div style={{padding: '20px'}}>Loading application configuration...</div>;
    if (appContextError) return <div style={{ color: 'red', padding: '20px' }}>Error loading application: {appContextError}<br/>Prompts Root: {promptsRoot}</div>;

    const activeFileObject = openFiles.find(f => f.path === activeFilePath);
    const canSaveCurrent = activeFileObject && activeFileObject.isModified;
    const canSaveAll = openFiles.some(f => f.isModified);

    return (
        <div style={editorPageStyle}>
            <header style={headerStyle}>
                <h1 style={headerTitleStyle}>Prompt Editor (Web)</h1>
                <div style={headerActionsStyle}>
                    {isPageLoading && <span style={{marginRight: '10px'}}>Loading...</span>}
                    {pageError && <span style={{color: 'red', marginRight: '10px', fontSize: '0.9em'}}>Error: {pageError}</span>}
                    <button
                        onClick={() => handleSaveFile(activeFilePath)}
                        disabled={!canSaveCurrent || isPageLoading}
                        style={!canSaveCurrent || isPageLoading ? buttonDisabledStyle : buttonStyle}
                        title="Save current file (Ctrl+S)"
                    >
                        Save
                    </button>
                    <button
                        onClick={handleSaveAllFiles}
                        disabled={!canSaveAll || isPageLoading}
                        style={!canSaveAll || isPageLoading ? buttonDisabledStyle : buttonStyle}
                        title="Save all modified files (Ctrl+Alt+S)"
                    >
                        Save All
                    </button>
                    <button
                        onClick={handleRunDsl}
                        disabled={!selectedCharacterId || isPageLoading}
                        style={!selectedCharacterId || isPageLoading ? buttonDisabledStyle : buttonStyle}
                    >
                        Generate for {selectedCharacterId || "..."}
                    </button>
                </div>
            </header>

            <div style={mainContentStyle}>
                <div style={leftPanelStyle}>
                    <FileTreePanel
                        key={fileTreeKey} // Force re-render on key change
                        onFileSelect={handleOpenFile}
                        onCharacterSelect={setSelectedCharacterId} // Pass this down from AppContext or manage here
                        promptsRoot={promptsRoot} // Pass the actual root
                        onFileRenamed={handleFileRenamedInTree}
                        onFileDeleted={handleFileDeletedInTree}
                        onFileCreated={refreshFileTree} // Simple refresh for now
                        onError={setPageError} // Allow FileTree to report errors
                    />
                </div>
                <div style={centerPanelStyle}>
                    <TabManager
                        openFiles={openFiles}
                        // setOpenFiles={setOpenFiles} // EditorPage manages this now
                        activeFilePath={activeFilePath}
                        setActiveFilePath={setActiveFilePath}
                        onFileContentChange={handleFileContentChange}
                        onCloseTab={handleCloseTab} // Pass the new close handler
                        onSaveTab={handleSaveFile} // Allow tab to request save
                    />
                </div>
                <div style={rightPanelStyle}>
                    <DslVariablesPanel
                        characterId={selectedCharacterId}
                        onVariablesChange={setDslVariables}
                    />
                </div>
            </div>

            <div style={bottomPanelStyle}>
                <LogPanel logs={logs} onClearLogs={handleClearLogs} />
            </div>

            {dslResult.show && (
                <DslResultModal
                    title={dslResult.title}
                    content={dslResult.content}
                    onClose={() => setDslResult({ ...dslResult, show: false })}
                />
            )}
        </div>
    );
}

export default EditorPage;