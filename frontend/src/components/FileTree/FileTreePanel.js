// frontend/src/components/FileTree/FileTreePanel.js
import React, { useState, useEffect, useCallback } from 'react';
import {
    getFileTree,
    deleteItem as apiDeleteItem,
    renameItem as apiRenameItem,
    createFileOrFolder as apiCreateItem
} from '../../services/api';
// Removed useAppContext here, selectedCharacterId is now passed as onCharacterSelect prop

const treeItemStyle = (isCharDir) => ({
    padding: '4px 8px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    fontSize: '0.9em',
    fontWeight: isCharDir ? 'bold' : 'normal',
    borderBottom: '1px solid #f0f0f0', // Subtle separator
});

const treeItemHoverStyle = {
    backgroundColor: '#e9f5ff', // Light blue hover
};

const fileTreeContainerStyle = {
    padding: '10px',
    flex: 1, // Allow it to take available space in its parent
    overflowY: 'auto', // Scroll if content overflows
};

const inputStyle = {
    marginLeft: '5px',
    padding: '2px',
    fontSize: '0.9em',
    border: '1px solid #ccc',
    borderRadius: '3px',
};

const buttonSmallStyle = {
    marginLeft: 'auto',
    fontSize: '0.8em',
    padding: '2px 5px',
    border: '1px solid #ccc',
    borderRadius: '3px',
    cursor: 'pointer',
    background: '#f0f0f0'
};


function FileTreePanel({
    onFileSelect,
    onCharacterSelect,
    promptsRoot, // Use this to display relative paths correctly if needed
    onFileRenamed,
    onFileDeleted,
    onFileCreated,
    onError // Callback to report errors to EditorPage
}) {
    const [treeData, setTreeData] = useState([]);
    const [currentRelativePath, setCurrentRelativePath] = useState('.');
    const [loading, setLoading] = useState(false);
    const [renamingItemPath, setRenamingItemPath] = useState(null);
    const [newItemName, setNewItemName] = useState('');
    const [creatingInPath, setCreatingInPath] = useState(null); // { path: string, type: 'file' | 'folder' }

    const fetchTree = useCallback(async (relativePath) => {
        setLoading(true);
        onError(null); // Clear previous errors
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
        fetchTree('.'); // Load root initially
    }, [fetchTree]); // fetchTree is stable due to useCallback

    const handleItemClick = (item) => {
        if (item.is_dir) {
            if (item.is_character_dir && onCharacterSelect) {
                onCharacterSelect(item.name);
            } else if (currentRelativePath === '.' && !item.is_character_dir && onCharacterSelect) {
                // If at root and click a non-char dir, clear selected character
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
        const parentIsCharDir = parts.length === 1 && onCharacterSelect; // Navigating up from a character dir
        parts.pop();
        const parentPath = parts.join('/') || '.';
        fetchTree(parentPath);
        if (parentIsCharDir || parentPath === '.') { // If went up to root or from char dir
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
                if (onFileDeleted) onFileDeleted(itemPath); // Notify EditorPage
                else fetchTree(currentRelativePath); // Fallback refresh
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
            else fetchTree(currentRelativePath); // Fallback refresh
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
        setNewItemName(''); // Clear for new item name
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
            if (onFileCreated) onFileCreated(); // Notify EditorPage to refresh
            else fetchTree(currentRelativePath); // Fallback refresh
        } catch (err) {
            onError(`Failed to create ${creatingInPath.type}: ${err.message}`);
        } finally {
            setCreatingInPath(null);
            setNewItemName('');
            setLoading(false);
        }
    };


    if (loading && treeData.length === 0) return <p style={{padding: '10px'}}>Loading tree...</p>;
    // Error is handled by EditorPage now via onError prop

    return (
        <div style={fileTreeContainerStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', paddingBottom: '10px', borderBottom: '1px solid #eee' }}>
                <h4 style={{ margin: 0, fontSize: '1em' }}>Explorer</h4>
                <div>
                    <button onClick={() => handleCreateStart('file')} title="New File" style={{marginRight: '5px', ...buttonSmallStyle, padding: '3px 6px'}}>📄+</button>
                    <button onClick={() => handleCreateStart('folder')} title="New Folder" style={{...buttonSmallStyle, padding: '3px 6px'}}>📁+</button>
                </div>
            </div>

            {creatingInPath && (
                <div style={{ marginBottom: '10px', padding: '5px', border: '1px dashed #ccc' }}>
                    Creating {creatingInPath.type} in '{creatingInPath.path}'
                    <input
                        type="text"
                        value={newItemName}
                        onChange={(e) => setNewItemName(e.target.value)}
                        placeholder={`${creatingInPath.type} name`}
                        onKeyDown={(e) => e.key === 'Enter' && handleCreateConfirm(e)}
                        autoFocus
                        style={inputStyle}
                    />
                    <button onClick={handleCreateConfirm} style={{...buttonSmallStyle, marginLeft: '5px'}}>Create</button>
                    <button onClick={() => setCreatingInPath(null)} style={{...buttonSmallStyle, marginLeft: '5px'}}>Cancel</button>
                </div>
            )}

            {currentRelativePath !== '.' && (
                <div
                    onClick={handleGoUp}
                    style={{ ...treeItemStyle(false), color: '#007bff', cursor: 'pointer' }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = treeItemHoverStyle.backgroundColor}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                    ⬅️ .. (Up)
                </div>
            )}
            <ul style={{ listStyle: 'none', paddingLeft: 0, margin: 0 }}>
                {treeData.map(item => (
                    <li
                        key={item.path}
                        onClick={() => renamingItemPath !== item.path && handleItemClick(item)}
                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = treeItemHoverStyle.backgroundColor}
                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                        style={treeItemStyle(item.is_character_dir)}
                        title={item.path}
                    >
                        {renamingItemPath === item.path ? (
                            <>
                                {item.is_dir ? '📁' : '📄'}
                                <input
                                    type="text"
                                    value={newItemName}
                                    onChange={(e) => setNewItemName(e.target.value)}
                                    onClick={(e) => e.stopPropagation()}
                                    onKeyDown={(e) => e.key === 'Enter' && handleRenameConfirm(e)}
                                    onBlur={() => { /* Consider auto-confirm or cancel on blur */ }}
                                    autoFocus
                                    style={inputStyle}
                                />
                                <button onClick={handleRenameConfirm} style={{...buttonSmallStyle, marginLeft: '5px'}}>Save</button>
                                <button onClick={(e) => {e.stopPropagation(); setRenamingItemPath(null);}} style={{...buttonSmallStyle, marginLeft: '5px'}}>Cancel</button>
                            </>
                        ) : (
                            <>
                                {item.is_dir ? '📁' : '📄'} {item.name}
                                <div style={{ marginLeft: 'auto', display: 'flex', gap: '5px' }}>
                                     <button onClick={(e) => handleRenameStart(e, item.path, item.name)} title="Rename" style={buttonSmallStyle}>✏️</button>
                                     <button onClick={(e) => handleDelete(e, item.path, item.name)} title="Delete" style={buttonSmallStyle}>🗑️</button>
                                </div>
                            </>
                        )}
                    </li>
                ))}
            </ul>
            {treeData.length === 0 && !loading && currentRelativePath === '.' && <p style={{fontSize: '0.9em', color: '#777', textAlign: 'center', marginTop: '20px'}}>Prompts directory is empty or not found.</p>}
            {treeData.length === 0 && !loading && currentRelativePath !== '.' && <p style={{fontSize: '0.9em', color: '#777', textAlign: 'center', marginTop: '20px'}}>This folder is empty.</p>}
        </div>
    );
}
export default FileTreePanel;