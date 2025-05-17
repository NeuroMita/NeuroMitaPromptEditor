import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useAppContext } from '../contexts/AppContext';
import { useSwipeable } from 'react-swipeable';

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

const MOBILE_PANELS = ['explorer', 'editor', 'variables', 'logs'];
const MIN_LOG_PANEL_HEIGHT = 60;
const DEFAULT_LOG_PANEL_HEIGHT = 200;

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
    const [activeMobilePanelIndex, setActiveMobilePanelIndex] = useState(1);
    const activeMobilePanel = useMemo(() => MOBILE_PANELS[activeMobilePanelIndex], [activeMobilePanelIndex]);
    const [isMobileView, setIsMobileView] = useState(window.innerWidth <= 768);
    const [logPanelHeight, setLogPanelHeight] = useState(DEFAULT_LOG_PANEL_HEIGHT);
    const [isResizingLogPanel, setIsResizingLogPanel] = useState(false);
    const initialMouseYRef = useRef(0);
    const initialLogHeightRef = useRef(0);
    const editorPageRef = useRef(null);
    const headerRef = useRef(null);
    const [lineWrapping, setLineWrapping] = useState(false); // По умолчанию перенос строк выключен

    useEffect(() => {
        const handleResize = () => setIsMobileView(window.innerWidth <= 768);
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    const handleMobilePanelChange = useCallback((index) => {
        setActiveMobilePanelIndex(index);
    }, []);

    const swipeHandlers = useSwipeable({
        onSwipedLeft: () => {
            if (isMobileView) setActiveMobilePanelIndex(prev => Math.min(prev + 1, MOBILE_PANELS.length - 1));
        },
        onSwipedRight: () => {
            if (isMobileView) setActiveMobilePanelIndex(prev => Math.max(prev - 1, 0));
        },
        preventScrollOnSwipe: true,
        trackMouse: false
    });

    const handleOpenFile = useCallback(async (fileNode) => {
        if (fileNode.is_dir) return;
        const existingFile = openFiles.find(f => f.path === fileNode.path);
        if (existingFile) {
            setActiveFilePath(fileNode.path);
            if (isMobileView) setActiveMobilePanelIndex(MOBILE_PANELS.indexOf('editor'));
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
            if (isMobileView) setActiveMobilePanelIndex(MOBILE_PANELS.indexOf('editor'));
        } catch (err) {
            setPageError(`Failed to open ${fileNode.name}: ${err.message}`);
            alert(`Failed to open ${fileNode.name}: ${err.message}`);
        } finally {
            setIsPageLoading(false);
        }
    }, [openFiles, isMobileView]);

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
        } catch (err) {
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

    if (appContextLoading) return <div className="loading-text">Loading application configuration...</div>;
    if (appContextError) return <div className="error-text">Error loading application: {appContextError}<br/>Prompts Root: {promptsRoot}</div>;

    const activeFileObject = openFiles.find(f => f.path === activeFilePath);
    const canSaveCurrent = activeFileObject && activeFileObject.isModified;
    const canSaveAll = openFiles.some(f => f.isModified);

    const renderDesktopLayout = () => (
        <div className="desktopContentWrapper">
            <div className="mainContent">
                <div className="leftPanelContainer">
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
                <div className="centerPanelContainer">
                    <TabManager
                        openFiles={openFiles}
                        activeFilePath={activeFilePath}
                        setActiveFilePath={setActiveFilePath}
                        onFileContentChange={handleFileContentChange}
                        onCloseTab={handleCloseTab}
                        onSaveTab={handleSaveFile}
                        lineWrapping={lineWrapping}
                    />
                </div>
                <div className="rightPanelContainer">
                    <DslVariablesPanel
                        characterId={selectedCharacterId}
                        onVariablesChange={setDslVariables}
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

    const renderMobileLayout = () => (
        <>
            <div {...swipeHandlers} className="swipeViewContainer">
                {MOBILE_PANELS.map((panelId, index) => (
                    <div
                        key={panelId}
                        className="swipePage"
                        style={{ transform: `translateX(${(index - activeMobilePanelIndex) * 100}%)` }}
                    >
                        {panelId === 'explorer' && (
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
                        )}
                        {panelId === 'editor' && (
                            <TabManager
                                openFiles={openFiles}
                                activeFilePath={activeFilePath}
                                setActiveFilePath={setActiveFilePath}
                                onFileContentChange={handleFileContentChange}
                                onCloseTab={handleCloseTab}
                                onSaveTab={handleSaveFile}
                                lineWrapping={lineWrapping}
                            />
                        )}
                        {panelId === 'variables' && (
                            <DslVariablesPanel
                                characterId={selectedCharacterId}
                                onVariablesChange={setDslVariables}
                            />
                        )}
                        {panelId === 'logs' && (
                            <LogPanel logs={logs} onClearLogs={handleClearLogs} />
                        )}
                    </div>
                ))}
            </div>
            <div className="mobileToggleBar">
                {MOBILE_PANELS.map((panel, index) => (
                    <button
                        key={panel}
                        onClick={() => handleMobilePanelChange(index)}
                        className={activeMobilePanelIndex === index ? 'active' : ''}
                        aria-label={`Switch to ${panel} view`}
                    >
                        {panel.charAt(0).toUpperCase() + panel.slice(1)}
                    </button>
                ))}
            </div>
        </>
    );

    return (
        <div className="editorPage" ref={editorPageRef}>
            <header className="header" ref={headerRef}>
                <h1 className="headerTitle">Prompt Editor</h1>
                <div className="headerActions">
                    {isPageLoading && <span className="pageStatus loading">Loading...</span>}
                    {pageError && <span className="pageStatus error">Error: {pageError}</span>}
                     <label htmlFor="lineWrappingCheckbox" style={{ display: 'flex', alignItems: 'center', marginRight: '10px', cursor: 'pointer', color: 'var(--text-color-normal, #D4D4D4)' }}>
                        <input
                            type="checkbox"
                            id="lineWrappingCheckbox"
                            checked={lineWrapping}
                            onChange={(e) => setLineWrapping(e.target.checked)}
                            style={{ marginRight: '5px', cursor: 'pointer' }}
                        />
                        Wrap Lines
                    </label>
                    <button onClick={() => handleSaveFile(activeFilePath)} disabled={!canSaveCurrent || isPageLoading} title="Save current file (Ctrl+S)">
                        {isMobileView ? "💾" : "Save"}
                    </button>
                    <button onClick={handleSaveAllFiles} disabled={!canSaveAll || isPageLoading} title="Save all modified files (Ctrl+Alt+S)">
                        {isMobileView ? "💾∀" : "Save All"}
                    </button>
                    <button onClick={handleRunDsl} disabled={!selectedCharacterId || isPageLoading}>
                        {isMobileView 
                            ? (selectedCharacterId ? `▶ ${selectedCharacterId.length > 10 ? selectedCharacterId.slice(0, 10) + '…' : selectedCharacterId}` : "▶ Gen") 
                            : (selectedCharacterId ? `Generate for ${selectedCharacterId}` : "Generate...")}
                    </button>
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