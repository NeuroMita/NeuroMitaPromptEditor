// File: frontend\src\services\api.js
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

const cache = {
    promptsRoot: null, // Stores the promise for promptsRoot
    fileTree: new Map(), // path -> Promise
    fileContent: new Map(), // filePath -> Promise
    charDefaultVariables: new Map(), // charId -> Promise
};

// Helper to get parent path for cache invalidation
function getParentPath(itemPath) {
    if (!itemPath || itemPath === '.') return '.';
    const parts = itemPath.split(/[/\\]+/);
    if (parts.length <= 1 && parts[0] !== '') return '.'; // Item is in root or is root itself
    if (parts.length === 1 && parts[0] === '') return '.'; // Path like "/file" - parent is root
    parts.pop();
    const parent = parts.join('/');
    return parent === '' ? '.' : parent; // Handle cases like "dir/file" -> "dir", "file" -> "."
}


async function fetchApi(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const config = {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    };

    try {
        const response = await fetch(url, config);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            console.error(`API Error (${response.status}): ${errorData.detail || 'Unknown error'} for ${url}`);
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }
        if (response.status === 204) { // No Content
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('Fetch API error:', error);
        throw error;
    }
}

export const getPromptsRoot = () => {
    if (cache.promptsRoot) {
        return cache.promptsRoot;
    }
    const promise = fetchApi('/settings/prompts-root')
        .catch(err => {
            cache.promptsRoot = null; // Clear on error to allow retry
            throw err;
        });
    cache.promptsRoot = promise;
    return promise;
};

export const getFileTree = (relativePath = '.') => {
    const cacheKey = relativePath;
    if (cache.fileTree.has(cacheKey)) {
        return cache.fileTree.get(cacheKey);
    }
    const promise = fetchApi(`/files/tree?path=${encodeURIComponent(relativePath)}`)
        .catch(err => {
            cache.fileTree.delete(cacheKey); // Clear on error
            throw err;
        });
    cache.fileTree.set(cacheKey, promise);
    return promise;
};

export const getFileContent = (filePath) => {
    if (cache.fileContent.has(filePath)) {
        return cache.fileContent.get(filePath);
    }
    const promise = fetchApi(`/files/content?file_path=${encodeURIComponent(filePath)}`)
        .catch(err => {
            cache.fileContent.delete(filePath); // Clear on error
            throw err;
        });
    cache.fileContent.set(filePath, promise);
    return promise;
};

export const saveFileContent = async (filePath, content) => {
    const result = await fetchApi(`/files/content?file_path=${encodeURIComponent(filePath)}`, {
        method: 'POST',
        body: JSON.stringify({ content }),
    });
    // Invalidate cache for this file, so next getFileContent fetches fresh data
    // Or, if API returns the new content, update cache: cache.fileContent.set(filePath, Promise.resolve(newContentData));
    cache.fileContent.delete(filePath);
    return result;
};

export const createFileOrFolder = async (parentDirPath, name, type) => {
    const result = await fetchApi(`/files/create?parent_dir_path=${encodeURIComponent(parentDirPath)}`, {
        method: 'POST',
        body: JSON.stringify({ name, type }),
    });
    // Invalidate parent directory tree cache
    cache.fileTree.delete(parentDirPath);
    return result;
};

export const renameItem = async (itemPath, newName) => {
    const result = await fetchApi(`/files/rename?item_path=${encodeURIComponent(itemPath)}`, {
        method: 'PUT',
        body: JSON.stringify({ new_name: newName }),
    });
    // Invalidate parent directory tree cache
    const parentDir = getParentPath(itemPath);
    cache.fileTree.delete(parentDir);

    // If the renamed item was a directory and its tree was cached, invalidate that too
    // (though it's now under a new name, the old path cache is stale)
    if (cache.fileTree.has(itemPath)) { // Check if itemPath itself was a key (i.e., it was a directory whose tree was fetched)
         cache.fileTree.delete(itemPath);
    }
    // Also invalidate new parent path if the item was moved across directories (not supported by current API structure, but good practice)
    // For current API, new_path is returned, so we could potentially invalidate cache for new_path's parent too.
    // For simplicity, only invalidating old parent. The UI re-fetches tree usually.
    return result;
};

export const deleteItem = async (itemPath) => {
    const result = await fetchApi(`/files/delete?item_path=${encodeURIComponent(itemPath)}`, {
        method: 'DELETE',
    });
    // Invalidate parent directory tree cache
    const parentDir = getParentPath(itemPath);
    cache.fileTree.delete(parentDir);

    // If the deleted item was a directory and its tree was cached, invalidate that too
    if (cache.fileTree.has(itemPath)) {
        cache.fileTree.delete(itemPath);
    }
    return result;
};

export const getCharacterDefaultVariables = (charId) => {
    if (cache.charDefaultVariables.has(charId)) {
        return cache.charDefaultVariables.get(charId);
    }
    const promise = fetchApi(`/characters/${charId}/default-variables`)
        .catch(err => {
            cache.charDefaultVariables.delete(charId); // Clear on error
            throw err;
        });
    cache.charDefaultVariables.set(charId, promise);
    return promise;
};

// This function involves a POST request, which typically isn't cached itself,
// but it doesn't directly invalidate other caches like file content or tree based on its current design.
// If generating a prompt could somehow alter files, then invalidation logic would be needed.
export const generatePrompt = (charId, initialVariables, tags) => fetchApi(`/characters/${charId}/generate-prompt`, {
    method: 'POST',
    body: JSON.stringify({ initial_variables: initialVariables, tags }),
});

// Function to clear specific caches if needed (e.g., for testing or a "force refresh" feature)
export const clearCache = (cacheName) => {
    if (cacheName === 'all') {
        cache.promptsRoot = null;
        cache.fileTree.clear();
        cache.fileContent.clear();
        cache.charDefaultVariables.clear();
        console.log('All API caches cleared.');
    } else if (cacheName === 'promptsRoot') {
        cache.promptsRoot = null;
    } else if (cache.hasOwnProperty(cacheName) && cache[cacheName] instanceof Map) {
        cache[cacheName].clear();
        console.log(`Cache cleared for: ${cacheName}`);
    }
};