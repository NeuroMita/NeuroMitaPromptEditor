// File: frontend\src\components\FileTree\FileTreePanel.js
import React, { useState, useEffect, useCallback } from 'react';
import {
    getFileTree,
    deleteItem as apiDeleteItem,
    renameItem as apiRenameItem,
    createFileOrFolder as apiCreateItem
} from '../../services/api';
import {
    Folder as FolderIcon,
    File as FileIcon,
    Settings as ScriptIcon, // Using Settings icon for .script files
    Edit2 as EditIcon,
    Trash2 as TrashIcon,
    ChevronLeft as ChevronLeftIcon,
    FilePlus as FilePlusIcon,
    FolderPlus as FolderPlusIcon
} from 'react-feather'; 
import '../../styles/FileTreePanel.css';


function FileTreePanel({
    onFileSelect,
    onCharacterSelect,
    onFileRenamed,
    onFileDeleted,
    onFileCreated,
    onError
}) {
    const [treeData, setTreeData] = useState([]);
    const [currentRelativePath, setCurrentRelativePath] = useState('.');
    const [loading, setLoading] = useState(false);
    const [renamingItemPath, setRenamingItemPath] = useState(null);
    const [newItemName, setNewItemName] = useState('');
    const [creatingInPath, setCreatingInPath] = useState(null);

    const fetchTree = useCallback(async (relativePath) => {
        setLoading(true);
        onError(null);
        try {
            const data = await getFileTree(relativePath); 
            setTreeData(data);
            setCurrentRelativePath(relativePath);
        } catch (err) {
            console.error("FileTreePanel fetchTree error:", err);
            onError(err.message || "Failed to load file tree.");
            setTreeData([]);
        } finally {
            setLoading(false);
        }
    }, [onError]);

    useEffect(() => {
        fetchTree('.'); 
    }, [fetchTree]);

    const handleItemClick = (item) => {
        if (item.is_dir) {
            if (item.is_character_dir && onCharacterSelect) {
                onCharacterSelect(item.path); 
            } else if (onCharacterSelect) {
                onCharacterSelect(null);
            }
            fetchTree(item.path); 
        } else { 
            onFileSelect(item);
        }
    };

    const handleGoUp = () => {
        if (currentRelativePath === '.' || currentRelativePath === '') return;
        const parts = currentRelativePath.split(/[/\\]+/);
        parts.pop();
        const parentPath = parts.join('/') || '.';
        fetchTree(parentPath);
        
        if (onCharacterSelect) {
            onCharacterSelect(null);
        }
    };

    const handleDelete = async (e, itemPath, itemName) => {
        e.stopPropagation();
        if (window.confirm(`Are you sure you want to delete '${itemName}'?`)) {
            setLoading(true);
            onError(null);
            try {
                await apiDeleteItem(itemPath); 
                if (onFileDeleted) onFileDeleted(itemPath);
                else fetchTree(currentRelativePath); 
            } catch (err) {
                onError(`Failed to delete ${itemName}: ${err.message}`);
            } finally {
                setLoading(false);
            }
        }
    };

    const handleRenameStart = (e, itemPath, currentName) => {
        e.stopPropagation();
        setRenamingItemPath(itemPath);
        setNewItemName(currentName);
    };

    const handleRenameConfirm = async (e) => {
        e.stopPropagation();
        if (!renamingItemPath || !newItemName.trim()) {
            setRenamingItemPath(null);
            return;
        }
        setLoading(true);
        onError(null);
        try {
            const result = await apiRenameItem(renamingItemPath, newItemName.trim()); 
            if (onFileRenamed) onFileRenamed(renamingItemPath, result.new_path, newItemName.trim());
            else fetchTree(currentRelativePath); 
        } catch (err) {
            onError(`Failed to rename: ${err.message}`);
        } finally {
            setRenamingItemPath(null);
            setNewItemName('');
            setLoading(false);
        }
    };

    const handleCreateStart = (type) => {
        setCreatingInPath({ path: currentRelativePath, type }); 
        setNewItemName('');
    };

    const handleCreateConfirm = async (e) => {
        e.stopPropagation();
        if (!creatingInPath || !newItemName.trim()) {
            setCreatingInPath(null);
            return;
        }
        setLoading(true);
        onError(null);
        try {
            await apiCreateItem(creatingInPath.path, newItemName.trim(), creatingInPath.type); 
            if (onFileCreated) onFileCreated(); 
            else fetchTree(currentRelativePath); 
        } catch (err) {
            onError(`Failed to create ${creatingInPath.type}: ${err.message}`);
        } finally {
            setCreatingInPath(null);
            setNewItemName('');
            setLoading(false);
        }
    };


    if (loading && treeData.length === 0) return <p className="fileTreeMessage loading-text">Loading tree...</p>;

    const getItemIcon = (item) => {
        if (item.is_dir) {
            return <FolderIcon size={16} className="fileTreeItemTypeIcon" />;
        }
        if (item.name && item.name.toLowerCase().endsWith('.script')) {
            return <ScriptIcon size={16} className="fileTreeItemTypeIcon scriptFileIcon" />;
        }
        return <FileIcon size={16} className="fileTreeItemTypeIcon" />;
    };

    return (
        <div className="fileTreeContainer">
            <div className="fileTreeHeader">
                <h4>Explorer</h4>
                <div className="fileTreeHeaderActions">
                    <button onClick={() => handleCreateStart('file')} title="New File" aria-label="New File">
                        <FilePlusIcon size={18} />
                    </button>
                    <button onClick={() => handleCreateStart('folder')} title="New Folder" aria-label="New Folder">
                        <FolderPlusIcon size={18} />
                    </button>
                </div>
            </div>

            {creatingInPath && (
                <div className="fileTreeFormContainer">
                    Creating {creatingInPath.type} in '{creatingInPath.path}'
                    <input
                        type="text"
                        value={newItemName}
                        onChange={(e) => setNewItemName(e.target.value)}
                        placeholder={`${creatingInPath.type} name`}
                        onKeyDown={(e) => e.key === 'Enter' && handleCreateConfirm(e)}
                        autoFocus
                        className="fileTreeInput"
                    />
                    <div className="fileTreeFormActions">
                        <button onClick={handleCreateConfirm}>Create</button>
                        <button onClick={() => setCreatingInPath(null)}>Cancel</button>
                    </div>
                </div>
            )}

            {currentRelativePath !== '.' && (
                <div
                    onClick={handleGoUp}
                    className="fileTreeItem upLink"
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleGoUp()}
                >
                    <ChevronLeftIcon size={16} className="fileTreeItemTypeIcon" /> .. (Up)
                </div>
            )}
            <ul className="fileTreeList">
                {treeData.map(item => (
                    <li
                        key={item.path} 
                        onClick={() => renamingItemPath !== item.path && handleItemClick(item)}
                        className={`fileTreeItem ${item.is_character_dir ? 'characterDir' : ''} ${!item.is_dir && item.name && item.name.toLowerCase().endsWith('.script') ? 'scriptFile' : ''}`}
                        title={item.path}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && renamingItemPath !== item.path && handleItemClick(item)}
                    >
                        {renamingItemPath === item.path ? (
                            <>
                                {getItemIcon(item)}
                                <input
                                    type="text"
                                    value={newItemName}
                                    onChange={(e) => setNewItemName(e.target.value)}
                                    onClick={(e) => e.stopPropagation()}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') handleRenameConfirm(e);
                                        if (e.key === 'Escape') {e.stopPropagation(); setRenamingItemPath(null);}
                                    }}
                                    onBlur={() => { /* Consider auto-cancel or auto-save on blur if needed */ }}
                                    autoFocus
                                    className="fileTreeInput"
                                />
                                <div className="fileTreeFormActions">
                                    <button onClick={handleRenameConfirm}>Save</button>
                                    <button onClick={(e) => {e.stopPropagation(); setRenamingItemPath(null);}}>Cancel</button>
                                </div>
                            </>
                        ) : (
                            <>
                                {getItemIcon(item)}
                                <span className="fileTreeItemName">{item.name}</span>
                                <div className="fileTreeItemActions">
                                     <button onClick={(e) => handleRenameStart(e, item.path, item.name)} title="Rename" aria-label="Rename">
                                        <EditIcon size={14} />
                                     </button>
                                     <button onClick={(e) => handleDelete(e, item.path, item.name)} title="Delete" aria-label="Delete">
                                        <TrashIcon size={14} />
                                     </button>
                                </div>
                            </>
                        )}
                    </li>
                ))}
            </ul>
            {treeData.length === 0 && !loading && currentRelativePath === '.' && <p className="fileTreeMessage">Your prompts directory is empty. Click buttons above to create items.</p>}
            {treeData.length === 0 && !loading && currentRelativePath !== '.' && <p className="fileTreeMessage">This folder is empty.</p>}
        </div>
    );
}
export default FileTreePanel;