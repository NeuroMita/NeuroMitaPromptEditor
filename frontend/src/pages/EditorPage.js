// File: frontend\src\pages\EditorPage.js
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useAppContext } from '../contexts/AppContext';
import { useNavigate } from 'react-router-dom';

import FileTreePanel from '../components/FileTree/FileTreePanel';
import TabManager from '../components/Editor/TabManager';
import DslVariablesPanel from '../components/Panels/DslVariablesPanel';
import LogPanel from '../components/Panels/LogPanel';
import DslResultModal from '../components/Panels/DslResultModal';

import {
    generatePrompt,
    getFileContent,
    saveFileContent as apiSaveFile,
    downloadUserPrompts as apiDownloadUserPrompts,
    uploadUserPromptsZip as apiUploadUserPromptsZip,
} from '../services/api';
import '../styles/EditorPage.css';

const MIN_LOG_PANEL_HEIGHT = 60;
const DEFAULT_LOG_PANEL_HEIGHT = 200;

const MOBILE_TABS = [
    { id: 'editor', label: 'Editor', icon: '📝' },
    { id: 'variables', label: 'Variables', icon: '⚙️' },
    { id: 'logs', label: 'Logs', icon: '📜' },
    { id: 'actions', label: 'Actions', icon: '🔧' }
];


function EditorPage() {
    const { 
        userPromptsInfo,
        selectedCharacterId, 
        setSelectedCharacterId, 
        isLoading: appContextLoading, 
        authError: appContextError,
        logout,
        currentUser
    } = useAppContext();
    const navigate = useNavigate();

    const [openFiles, setOpenFiles] = useState([]);
    const [activeFilePath, setActiveFilePath] = useState(null);
    const [fileTreeKey, setFileTreeKey] = useState(Date.now());
    const [dslVariables, setDslVariables] = useState({});
    const [dslResult, setDslResult] = useState({ show: false, title: '', content: '' });
    const [logs, setLogs] = useState([]);
    const [isPageLoading, setIsPageLoading] = useState(false);
    const [pageError, setPageError] = useState(null);
    
    const [isMobileView, setIsMobileView] = useState(window.innerWidth <= 768);
    const [isMobileExplorerOpen, setIsMobileExplorerOpen] = useState(false);
    const [activeMobileTab, setActiveMobileTab] = useState(MOBILE_TABS[0].id);

    const [logPanelHeight, setLogPanelHeight] = useState(DEFAULT_LOG_PANEL_HEIGHT);
    const [isResizingLogPanel, setIsResizingLogPanel] = useState(false);
    const initialMouseYRef = useRef(0);
    const initialLogHeightRef = useRef(0);
    const editorPageRef = useRef(null);
    const headerRef = useRef(null);
    const [lineWrapping, setLineWrapping] = useState(false);
    const zipUploadInputRef = useRef(null);

    useEffect(() => {
        const handleResize = () => {
            const mobile = window.innerWidth <= 768;
            setIsMobileView(mobile);
            if (!mobile && isMobileExplorerOpen) {
                setIsMobileExplorerOpen(false); // Close explorer if resizing to desktop
            }
        };
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, [isMobileExplorerOpen]);

    const toggleMobileExplorer = useCallback(() => {
        setIsMobileExplorerOpen(prev => !prev);
    }, []);
    
    const handleMobileFileSelect = useCallback(async (fileNode) => {
        await handleOpenFile(fileNode); // Use the existing open logic
        if (fileNode && !fileNode.is_dir) {
             setIsMobileExplorerOpen(false); // Close explorer after selection
             setActiveMobileTab('editor'); // Switch to editor tab
        } else if (fileNode && fileNode.is_dir) {
            // If it's a directory, explorer stays open to show new content
        } else {
            setIsMobileExplorerOpen(false);
        }
    }, []);


    const handleOpenFile = useCallback(async (fileNode) => {
        if (fileNode.is_dir) return;
        const existingFile = openFiles.find(f => f.path === fileNode.path);
        if (existingFile) {
            setActiveFilePath(fileNode.path);
             // No automatic tab switch here, let user control mobile tabs separately
            return;
        }
        setIsPageLoading(true);
        setPageError(null);
        try {
            const fileData = await getFileContent(fileNode.path);
            setOpenFiles(prevFiles => [
                ...prevFiles,
                { path: fileData.path, name: fileNode.name, content: fileData.content, originalContent: fileData.content, isModified: false }
            ]);
            setActiveFilePath(fileData.path);
        } catch (err) {
            setPageError(`Failed to open ${fileNode.name}: ${err.message}`);
            alert(`Failed to open ${fileNode.name}: ${err.message}`);
        } finally {
            setIsPageLoading(false);
        }
    }, [openFiles]);
    
    const handleOpenPathByString = useCallback(async (filePathToOpen) => {
        // This function is primarily for desktop Ctrl+Click.
        // On mobile, direct interaction with FileTreePanel is preferred.
        // It might be possible to find the file by iterating through the tree if loaded,
        // or by calling an API to get minimal file info, then opening.
        // For now, focusing on the main request, this remains as is.
        console.log(`Attempting to open by string: ${filePathToOpen}`);
        try {
            // Simple approach: assume it's a full path and try to open
            // This needs a "file node" like structure. We only have path string.
            // This is a placeholder for a more robust implementation if needed on mobile.
            // For now, rely on EditorArea's `!isMobileView` check for Ctrl+Click.
            // A more robust way would be to search or fetch file details.
            const dummyFileNode = { path: filePathToOpen, name: filePathToOpen.split(/[/\\]+/).pop(), is_dir: false };
            await handleOpenFile(dummyFileNode);
            if (isMobileView) {
                setActiveMobileTab('editor');
            }
        } catch (err) {
            setPageError(`Failed to open linked file ${filePathToOpen}: ${err.message}`);
        }
    }, [handleOpenFile, isMobileView]);


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
        if (!fileToSave || !fileToSave.isModified) return;
        setIsPageLoading(true);
        setPageError(null);
        try {
            await apiSaveFile(fileToSave.path, fileToSave.content);
            setOpenFiles(prevFiles =>
                prevFiles.map(f =>
                    f.path === fileToSave.path ? { ...f, isModified: false, originalContent: f.content } : f
                )
            );
        } catch (err) {
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
                    if (!window.confirm("Some files could not be saved. Continue generating prompt anyway?")) return;
                }
            } else {
                 if (!window.confirm("Generate prompt with unsaved changes? This might lead to unexpected results.")) return;
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
            if (isMobileView) setActiveMobileTab('logs'); // Switch to logs tab on mobile after generation
        } catch (err) {
            setPageError(`Error generating prompt: ${err.message}`);
            alert(`Error generating prompt: ${err.message}`);
            setLogs(prev => [...prev, { level: "ERROR", message: `API Error: ${err.message}`, name: "API_CLIENT" }]);
        } finally {
            setIsPageLoading(false);
        }
    }, [selectedCharacterId, dslVariables, openFiles, handleSaveAllFiles, isMobileView]);

    const handleClearLogs = useCallback(() => {
        setLogs([]);
    }, []);

    useEffect(() => {
        const handleKeyDown = (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === 's') {
                event.preventDefault();
                if (activeFilePath) handleSaveFile(activeFilePath);
            }
            if ((event.ctrlKey || event.metaKey) && event.altKey && event.key === 's') {
                event.preventDefault();
                handleSaveAllFiles();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [activeFilePath, handleSaveFile, handleSaveAllFiles]);

    const handleLogPanelResizeStart = useCallback((e) => {
        e.preventDefault();
        setIsResizingLogPanel(true);
        initialMouseYRef.current = e.clientY;
        initialLogHeightRef.current = logPanelHeight;
        document.body.style.cursor = 'ns-resize';
        document.body.style.userSelect = 'none';
    }, [logPanelHeight]);

    useEffect(() => {
        const handleMouseMove = (e) => {
            if (!isResizingLogPanel) return;
            const deltaY = e.clientY - initialMouseYRef.current;
            let newHeight = initialLogHeightRef.current - deltaY;
            const maxLogPanelHeight = editorPageRef.current 
                ? editorPageRef.current.offsetHeight - (headerRef.current?.offsetHeight || 60) - 150
                : window.innerHeight * 0.7;
            newHeight = Math.max(MIN_LOG_PANEL_HEIGHT, newHeight);
            newHeight = Math.min(newHeight, maxLogPanelHeight);
            setLogPanelHeight(newHeight);
        };
        const handleMouseUp = () => {
            setIsResizingLogPanel(false);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };
        if (isResizingLogPanel) {
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
            return () => {
                document.removeEventListener('mousemove', handleMouseMove);
                document.removeEventListener('mouseup', handleMouseUp);
            };
        }
    }, [isResizingLogPanel]);

    const handleLogoutClick = () => {
        logout();
        navigate('/login', { replace: true });
    };

    const handleDownloadPrompts = async () => {
        setIsPageLoading(true);
        setPageError(null);
        try {
            const { isEmpty, filename, blob } = await apiDownloadUserPrompts();
            if (isEmpty) {
                alert("Your prompts directory is empty. Nothing to download.");
            } else if (blob && filename) {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
            } else {
                throw new Error("Download failed: No blob or filename received from server.");
            }
        } catch (err) {
            setPageError(`Download failed: ${err.message}`);
            alert(`Download failed: ${err.message}`);
        } finally {
            setIsPageLoading(false);
        }
    };

    const handleZipFileSelected = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        setIsPageLoading(true);
        setPageError(null);
        try {
            if (!file.name.toLowerCase().endsWith('.zip')) {
                throw new Error("Invalid file type. Please select a .zip file.");
            }
            const result = await apiUploadUserPromptsZip(file);
            alert(result.message || "ZIP file imported successfully!");
            refreshFileTree();
            if (isMobileView && isMobileExplorerOpen) { // If explorer is open on mobile, refresh its content
                 // FileTreePanel uses key to refresh, this should be enough
            }
        } catch (err) {
            setPageError(`Import failed: ${err.message}`);
            alert(`Import failed: ${err.message}`);
        } finally {
            setIsPageLoading(false);
            if (zipUploadInputRef.current) {
                zipUploadInputRef.current.value = '';
            }
        }
    };


    if (appContextLoading) return <div className="loading-text">Loading user session...</div>;
    if (appContextError) return <div className="error-text">Session Error: {appContextError}<br/>Please try logging in again.</div>;
    if (!userPromptsInfo) return <div className="loading-text">Initializing user workspace...</div>;

    const activeFileObject = openFiles.find(f => f.path === activeFilePath);
    const canSaveCurrent = activeFileObject && activeFileObject.isModified;
    const canSaveAll = openFiles.some(f => f.isModified);

    const getDisplayCharName = (charPath) => {
        if (!charPath) return null;
        const parts = charPath.replace(/\\/g, '/').split('/');
        return parts[parts.length - 1];
    };
    const displayCharName = getDisplayCharName(selectedCharacterId);

    const renderDesktopLayout = () => (
        <div className="desktopContentWrapper">
            <div className="mainContent">
                <div className="leftPanelContainer">
                    <FileTreePanel
                        key={fileTreeKey}
                        onFileSelect={handleOpenFile}
                        onCharacterSelect={setSelectedCharacterId}
                        onFileRenamed={handleFileRenamedInTree}
                        onFileDeleted={handleFileDeletedInTree}
                        onFileCreated={refreshFileTree}
                        onError={setPageError}
                    />
                </div>
                <div className="centerPanelContainer">
                    <TabManager
                        openFiles={openFiles}
                        activeFilePath={activeFilePath}
                        setActiveFilePath={setActiveFilePath}
                        onFileContentChange={handleFileContentChange}
                        onCloseTab={handleCloseTab}
                        onSaveTab={handleSaveFile}
                        lineWrapping={lineWrapping}
                        isMobileView={false} // Explicitly false for desktop
                        onOpenPathByString={handleOpenPathByString}
                    />
                </div>
                <div className="rightPanelContainer">
                    <DslVariablesPanel
                        characterId={selectedCharacterId}
                        onVariablesChange={setDslVariables}
                        isMobileView={false}
                    />
                </div>
            </div>
            <div 
                className="logPanelResizeHandle" 
                onMouseDown={handleLogPanelResizeStart}
                title="Drag to resize log panel"
            />
            <div className="bottomPanelContainer" style={{ height: `${logPanelHeight}px` }}>
                <LogPanel logs={logs} onClearLogs={handleClearLogs} />
            </div>
        </div>
    );

    const renderMobileActionsPanel = () => (
        <div className="mobileActionsPanel">
            <h3>Actions</h3>
            <div className="mobileActionsGrid">
                <button onClick={handleSaveAllFiles} disabled={!canSaveAll || isPageLoading} className="mobileActionButton">
                    Save All
                </button>
                 <label htmlFor="lineWrappingCheckboxMobile" className="mobileActionButton checkboxLabel">
                    <input
                        type="checkbox"
                        id="lineWrappingCheckboxMobile"
                        checked={lineWrapping}
                        onChange={(e) => setLineWrapping(e.target.checked)}
                    />
                    Wrap Lines
                </label>
                <button onClick={handleDownloadPrompts} disabled={isPageLoading} className="mobileActionButton">
                    Download ZIP
                </button>
                <button onClick={() => zipUploadInputRef.current?.click()} disabled={isPageLoading} className="mobileActionButton">
                    Import ZIP
                </button>
                <button onClick={handleLogoutClick} disabled={isPageLoading} className="mobileActionButton">
                    Logout
                </button>
            </div>
             {isPageLoading && <span className="pageStatus loading">Loading...</span>}
             {pageError && <span className="pageStatus error small-error">Error: {pageError}</span>}
        </div>
    );


    const renderMobileLayout = () => (
        <>
            {isMobileExplorerOpen && (
                <>
                    <div className="mobileExplorerOverlay" onClick={toggleMobileExplorer}></div>
                    <div className={`mobileExplorerPanel ${isMobileExplorerOpen ? 'open' : ''}`}>
                        <FileTreePanel
                            key={`mobile-${fileTreeKey}`}
                            onFileSelect={handleMobileFileSelect}
                            onCharacterSelect={(charId) => {
                                setSelectedCharacterId(charId);
                                // Optionally close explorer or switch tab if needed
                            }}
                            onFileRenamed={handleFileRenamedInTree}
                            onFileDeleted={handleFileDeletedInTree}
                            onFileCreated={refreshFileTree}
                            onError={setPageError}
                        />
                    </div>
                </>
            )}
            <div className="mobileMainContentArea">
                {activeMobileTab === 'editor' && (
                    <TabManager
                        openFiles={openFiles}
                        activeFilePath={activeFilePath}
                        setActiveFilePath={setActiveFilePath}
                        onFileContentChange={handleFileContentChange}
                        onCloseTab={handleCloseTab}
                        onSaveTab={handleSaveFile}
                        lineWrapping={lineWrapping}
                        isMobileView={true}
                        onOpenPathByString={handleOpenPathByString}
                    />
                )}
                {activeMobileTab === 'variables' && (
                    <DslVariablesPanel
                        characterId={selectedCharacterId}
                        onVariablesChange={setDslVariables}
                        isMobileView={true}
                    />
                )}
                {activeMobileTab === 'logs' && (
                    <LogPanel logs={logs} onClearLogs={handleClearLogs} />
                )}
                {activeMobileTab === 'actions' && renderMobileActionsPanel()}
            </div>
            <div className="mobileBottomNavBar">
                {MOBILE_TABS.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveMobileTab(tab.id)}
                        className={activeMobileTab === tab.id ? 'active' : ''}
                        aria-label={tab.label}
                        title={tab.label}
                    >
                        <span className="mobileNavIcon">{tab.icon}</span>
                        <span className="mobileNavLabel">{tab.label}</span>
                    </button>
                ))}
            </div>
        </>
    );

    return (
        <div className={`editorPage ${isMobileView ? 'mobile-view' : ''}`} ref={editorPageRef}>
            <header className="header" ref={headerRef}>
                <div className="header-left">
                    {isMobileView && (
                        <button onClick={toggleMobileExplorer} className="headerButton hamburgerButton" aria-label="Toggle Explorer">
                            ☰
                        </button>
                    )}
                    <h1 className="headerTitle">Prompt Editor</h1>
                    {!isMobileView && currentUser && <span className="currentUserDisplay">User: {currentUser.username}</span>}
                </div>
                <div className="headerActions">
                    {isPageLoading && !isMobileView && <span className="pageStatus loading">Loading...</span>}
                    {pageError && !isMobileView && <span className="pageStatus error">Error: {pageError}</span>}
                    
                    {!isMobileView && (
                         <label htmlFor="lineWrappingCheckboxDesktop" className="headerCheckboxLabel">
                            <input
                                type="checkbox"
                                id="lineWrappingCheckboxDesktop"
                                checked={lineWrapping}
                                onChange={(e) => setLineWrapping(e.target.checked)}
                            />
                            Wrap Lines
                        </label>
                    )}

                    <button className="headerButton" onClick={() => handleSaveFile(activeFilePath)} disabled={!canSaveCurrent || isPageLoading} title="Save current file (Ctrl+S)">
                        Save
                    </button>
                    {!isMobileView && (
                        <button className="headerButton" onClick={handleSaveAllFiles} disabled={!canSaveAll || isPageLoading} title="Save all modified files (Ctrl+Alt+S)">
                            Save All
                        </button>
                    )}
                    <button className="headerButton" onClick={handleRunDsl} disabled={!selectedCharacterId || isPageLoading} title={displayCharName ? `Generate for ${displayCharName}` : "Generate..."}>
                        {displayCharName ? `Generate ${isMobileView && displayCharName.length > 6 ? displayCharName.slice(0,5) + '…' : displayCharName}` : "Generate"}
                    </button>
                    
                    {!isMobileView && (
                        <>
                            <button className="headerButton" onClick={handleDownloadPrompts} disabled={isPageLoading} title="Download all your prompts as ZIP">
                                Download ZIP
                            </button>
                            <input 
                                type="file" 
                                accept=".zip" 
                                ref={zipUploadInputRef} 
                                onChange={handleZipFileSelected} 
                                style={{ display: 'none' }} 
                                aria-hidden="true"
                            />
                            <button 
                                className="headerButton"
                                onClick={() => zipUploadInputRef.current?.click()} 
                                disabled={isPageLoading} 
                                title="Import prompts from a ZIP file"
                            >
                                Import ZIP
                            </button>
                            <button className="headerButton" onClick={handleLogoutClick} disabled={isPageLoading} title="Logout">
                                Logout
                            </button>
                        </>
                    )}
                     {isMobileView && currentUser && <span className="currentUserDisplayMobile">User: {currentUser.username}</span>}
                </div>
            </header>
            
            {isMobileView ? renderMobileLayout() : renderDesktopLayout()}
            
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