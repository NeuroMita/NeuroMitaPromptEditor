// File: frontend\src\pages\EditorPage.js
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
} from '../services/api';
import '../styles/EditorPage.css';


function EditorPage() {
    const { promptsRoot, selectedCharacterId, setSelectedCharacterId, isLoading: appContextLoading, error: appContextError } = useAppContext();

    const [openFiles, setOpenFiles] = useState([]);
    const [activeFilePath, setActiveFilePath] = useState(null);
    const [fileTreeKey, setFileTreeKey] = useState(Date.now());

    const [dslVariables, setDslVariables] = useState({});
    const [dslResult, setDslResult] = useState({ show: false, title: '', content: '' });

    const [logs, setLogs] = useState([]);

    const [isPageLoading, setIsPageLoading] = useState(false);
    const [pageError, setPageError] = useState(null);

    // State for mobile panel visibility: 'explorer', 'editor', 'variables', 'logs'
    const [activeMobilePanel, setActiveMobilePanel] = useState('editor');

    const handleMobilePanelToggle = (panel) => {
        setActiveMobilePanel(panel);
    };

    const handleOpenFile = useCallback(async (fileNode) => {
        if (fileNode.is_dir) {
            return;
        }

        const existingFile = openFiles.find(f => f.path === fileNode.path);
        if (existingFile) {
            setActiveFilePath(fileNode.path);
            if (window.innerWidth <= 768) setActiveMobilePanel('editor'); // Switch to editor on mobile after file select
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
                    originalContent: fileData.content,
                    isModified: false
                }
            ]);
            setActiveFilePath(fileData.path);
            if (window.innerWidth <= 768) setActiveMobilePanel('editor'); // Switch to editor on mobile after file open
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
                return false;
            }
        }

        setOpenFiles(prevFiles => prevFiles.filter(file => file.path !== filePathToClose));

        if (activeFilePath === filePathToClose) {
            const newOpenFiles = openFiles.filter(file => file.path !== filePathToClose);
            setActiveFilePath(newOpenFiles.length > 0 ? newOpenFiles[newOpenFiles.length - 1].path : null);
        }
        return true;
    }, [activeFilePath, openFiles]);

    const refreshFileTree = useCallback(() => {
        setFileTreeKey(Date.now());
    }, []);

    const handleFileRenamedInTree = useCallback((oldPath, newPath, newName) => {
        refreshFileTree();
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
        if (openFiles.some(f => f.path === deletedPath)) {
            handleCloseTab(deletedPath, true);
        }
    }, [openFiles, handleCloseTab, refreshFileTree]);


    const handleRunDsl = useCallback(async () => {
        if (!selectedCharacterId) {
            alert("Please select a character first.");
            return;
        }
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
        setLogs([]);
        try {
            const tags = { SYS_INFO: "Generated from Web Editor." };
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


    const handleClearLogs = useCallback(() => {
        setLogs([]);
    }, []);

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


    if (appContextLoading) return <div className="loading-text">Loading application configuration...</div>;
    if (appContextError) return <div className="error-text">Error loading application: {appContextError}<br/>Prompts Root: {promptsRoot}</div>;

    const activeFileObject = openFiles.find(f => f.path === activeFilePath);
    const canSaveCurrent = activeFileObject && activeFileObject.isModified;
    const canSaveAll = openFiles.some(f => f.isModified);

    return (
        <div className="editorPage">
            <header className="header">
                <h1 className="headerTitle">Prompt Editor (Web)</h1>
                <div className="headerActions">
                    {isPageLoading && <span className="pageStatus loading">Loading...</span>}
                    {pageError && <span className="pageStatus error">Error: {pageError}</span>}
                    <button
                        onClick={() => handleSaveFile(activeFilePath)}
                        disabled={!canSaveCurrent || isPageLoading}
                        title="Save current file (Ctrl+S)"
                    >
                        Save
                    </button>
                    <button
                        onClick={handleSaveAllFiles}
                        disabled={!canSaveAll || isPageLoading}
                        title="Save all modified files (Ctrl+Alt+S)"
                    >
                        Save All
                    </button>
                    <button
                        onClick={handleRunDsl}
                        disabled={!selectedCharacterId || isPageLoading}
                    >
                        Generate for {selectedCharacterId || "..."}
                    </button>
                </div>
            </header>

            <div className="mobileToggleBar">
                <button
                    onClick={() => handleMobilePanelToggle('explorer')}
                    className={activeMobilePanel === 'explorer' ? 'active' : ''}
                >
                    Explorer
                </button>
                <button
                    onClick={() => handleMobilePanelToggle('editor')}
                    className={activeMobilePanel === 'editor' ? 'active' : ''}
                >
                    Editor
                </button>
                <button
                    onClick={() => handleMobilePanelToggle('variables')}
                    className={activeMobilePanel === 'variables' ? 'active' : ''}
                >
                    Variables
                </button>
                <button
                    onClick={() => handleMobilePanelToggle('logs')}
                    className={activeMobilePanel === 'logs' ? 'active' : ''}
                >
                    Logs
                </button>
            </div>

            <div className="mainContent">
                <div className={`leftPanelContainer ${activeMobilePanel !== 'explorer' ? 'mobileHidden' : 'mobileVisible'}`}>
                    <FileTreePanel
                        key={fileTreeKey}
                        onFileSelect={handleOpenFile}
                        onCharacterSelect={setSelectedCharacterId}
                        promptsRoot={promptsRoot}
                        onFileRenamed={handleFileRenamedInTree}
                        onFileDeleted={handleFileDeletedInTree}
                        onFileCreated={refreshFileTree}
                        onError={setPageError}
                    />
                </div>
                <div className={`centerPanelContainer ${activeMobilePanel !== 'editor' ? 'mobileHidden' : 'mobileVisible'}`}>
                    <TabManager
                        openFiles={openFiles}
                        activeFilePath={activeFilePath}
                        setActiveFilePath={setActiveFilePath}
                        onFileContentChange={handleFileContentChange}
                        onCloseTab={handleCloseTab}
                        onSaveTab={handleSaveFile}
                    />
                </div>
                <div className={`rightPanelContainer ${activeMobilePanel !== 'variables' ? 'mobileHidden' : 'mobileVisible'}`}>
                    <DslVariablesPanel
                        characterId={selectedCharacterId}
                        onVariablesChange={setDslVariables}
                    />
                </div>
            </div>

            <div className={`bottomPanelContainer ${activeMobilePanel !== 'logs' ? 'mobileHidden' : 'mobileVisible'}`}>
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