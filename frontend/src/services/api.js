// File: frontend\src\services\api.js
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

const cache = {
    fileTree: new Map(), 
    fileContent: new Map(), 
    charDefaultVariables: new Map(), 
};

const getToken = () => localStorage.getItem('authToken');

// Helper to normalize path separators to forward slashes
function normalizePath(pathStr) {
    if (typeof pathStr === 'string') {
        return pathStr.replace(/\\/g, '/');
    }
    return pathStr;
}

function getParentPath(itemPath) { // Assumes itemPath is already normalized
    if (!itemPath || itemPath === '.') return '.';
    const parts = itemPath.split('/'); // Use forward slash for splitting
    if (parts.length <= 1 && parts[0] !== '') return '.'; 
    if (parts.length === 1 && parts[0] === '') return '.'; 
    parts.pop();
    const parent = parts.join('/');
    return parent === '' ? '.' : parent;
}

async function fetchApi(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const token = getToken();
    
    const headers = { ...options.headers };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = { ...options, headers }; // Create a mutable copy for headers and other options
    // Explicitly add keepalive to the fetch config if options.keepalive is true
    if (options.keepalive === true) {
        config.keepalive = true;
    }


    if (!(options.body instanceof FormData) && options.body && typeof options.body === 'object' && !headers['Content-Type']) {
        config.headers['Content-Type'] = 'application/json';
        config.body = JSON.stringify(config.body); 
    } else if (options.body instanceof FormData) {
        delete config.headers['Content-Type']; 
    }

    try {
        const response = await fetch(url, config);
        if (response.status === 401) {
            console.error(`API Error 401: Unauthorized for ${url}. Token might be invalid or expired.`);
            window.dispatchEvent(new CustomEvent('auth-error-401', { detail: { endpoint } }));
        }
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            console.error(`API Error (${response.status}): ${errorData.detail || 'Unknown error'} for ${url}`);
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }
        if (response.status === 204) { 
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('Fetch API error:', error, 'Endpoint:', endpoint);
        if (error.message.includes("Unexpected token '<'") && error.message.includes("HTML")) {
             throw new Error("API request failed. Server might be down or returned an HTML error page instead of JSON.");
        }
        throw error;
    }
}

// --- Auth Endpoints ---
export const loginUser = async (username, password) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch(`${API_BASE_URL}/auth/token`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData,
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || `Login failed: Status ${response.status}`);
    }
    const data = await response.json();
    return data;
};

export const registerUser = async (username, password, inviteCode) => {
    const payload = {
        username: username,
        password: password,
        invite_code: inviteCode,
    };
    return fetchApi('/auth/register', {
        method: 'POST',
        body: payload,
    });
};


// --- Settings Endpoints ---
export const getUserPromptsInfo = () => {
    return fetchApi('/settings/prompts-root');
};


// --- File Endpoints ---
export const getFileTree = (relativePath = '.') => {
    const normalizedPath = normalizePath(relativePath);
    const cacheKey = normalizedPath;
    if (cache.fileTree.has(cacheKey)) {
        return cache.fileTree.get(cacheKey);
    }
    const promise = fetchApi(`/files/tree?path=${encodeURIComponent(normalizedPath)}`)
        .catch(err => {
            cache.fileTree.delete(cacheKey);
            throw err;
        });
    cache.fileTree.set(cacheKey, promise);
    return promise;
};

export const getFileContent = (filePath) => {
    const normalizedPath = normalizePath(filePath);
    if (cache.fileContent.has(normalizedPath)) {
        return cache.fileContent.get(normalizedPath);
    }
    const promise = fetchApi(`/files/content?file_path=${encodeURIComponent(normalizedPath)}`)
        .catch(err => {
            cache.fileContent.delete(normalizedPath);
            throw err;
        });
    cache.fileContent.set(normalizedPath, promise);
    return promise;
};

export const saveFileContent = async (filePath, content, keepalive = false) => {
    const normalizedPath = normalizePath(filePath);
    
    const fetchOptions = {
        method: 'POST',
        body: { content },
    };
    if (keepalive) {
        fetchOptions.keepalive = true;
    }

    const result = await fetchApi(`/files/content?file_path=${encodeURIComponent(normalizedPath)}`, fetchOptions);
    
    // Invalidate caches. If keepalive is true, this happens optimistically.
    // The request is sent; if it succeeds on the server, the cache invalidation is correct for next load.
    cache.fileContent.delete(normalizedPath); 
    const parentDir = getParentPath(normalizedPath);
    cache.fileTree.delete(parentDir); 
    
    return result; 
};

export const createFileOrFolder = async (parentDirPath, name, type) => {
    const normalizedPath = normalizePath(parentDirPath);
    const result = await fetchApi(`/files/create?parent_dir_path=${encodeURIComponent(normalizedPath)}`, {
        method: 'POST',
        body: { name, type },
    });
    cache.fileTree.delete(normalizedPath);
    return result;
};

export const renameItem = async (itemPath, newName) => {
    const normalizedItemPath = normalizePath(itemPath);
    const result = await fetchApi(`/files/rename?item_path=${encodeURIComponent(normalizedItemPath)}`, {
        method: 'PUT',
        body: { new_name: newName },
    });
    const parentDirOld = getParentPath(normalizedItemPath);
    cache.fileTree.delete(parentDirOld);
    
    if (cache.fileTree.has(normalizedItemPath)) { 
         cache.fileTree.delete(normalizedItemPath);
    }
    const normalizedNewPath = normalizePath(result.new_path);
    const parentDirNew = getParentPath(normalizedNewPath);
    if (parentDirNew !== parentDirOld) {
        cache.fileTree.delete(parentDirNew);
    }
    cache.fileContent.delete(normalizedItemPath); 
    return result;
};

export const deleteItem = async (itemPath) => {
    const normalizedItemPath = normalizePath(itemPath);
    const result = await fetchApi(`/files/delete?item_path=${encodeURIComponent(normalizedItemPath)}`, {
        method: 'DELETE',
    });
    const parentDir = getParentPath(normalizedItemPath);
    cache.fileTree.delete(parentDir);
    if (cache.fileTree.has(normalizedItemPath)) { 
        cache.fileTree.delete(normalizedItemPath);
    }
    cache.fileContent.delete(normalizedItemPath); 
    return result;
};

// --- Character Endpoints ---
export const getCharacterStaticDefaults = (characterName) => {
    const normalizedCharName = normalizePath(characterName).split('/').pop(); 
    
    if (cache.charDefaultVariables.has(normalizedCharName)) {
        return cache.charDefaultVariables.get(normalizedCharName);
    }
    const promise = fetchApi(`/characters/${normalizedCharName}/static-defaults`)
        .catch(err => {
            cache.charDefaultVariables.delete(normalizedCharName);
            throw err;
        });
    cache.charDefaultVariables.set(normalizedCharName, promise);
    return promise;
};

export const generatePrompt = (charId, initialVariables, tags) => {
    const normalizedCharId = normalizePath(charId); 
    return fetchApi(`/characters/${normalizedCharId}/generate-prompt`, {
        method: 'POST',
        body: { initial_variables: initialVariables, tags },
    });
};

// --- User Actions Endpoints (New) ---
export const downloadUserPrompts = async () => {
    const url = `${API_BASE_URL}/user/prompts/download`;
    const token = getToken();
    const headers = {};
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, { headers });

    if (response.status === 204) {
        return { isEmpty: true, filename: null, blob: null };
    }

    if (response.status === 401) {
        window.dispatchEvent(new CustomEvent('auth-error-401', { detail: { endpoint: '/user/prompts/download' } }));
        throw new Error("Unauthorized. Your session may have expired.");
    }

    if (!response.ok) {
        let errorDetail = response.statusText;
        try {
            const errorData = await response.json();
            errorDetail = errorData.detail || errorDetail;
        } catch (e) { /* ignore */ }
        throw new Error(errorDetail || `Download failed: Status ${response.status}`);
    }

    const contentDisposition = response.headers.get('content-disposition');
    let filename = 'user_prompts.zip';
    if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
        if (filenameMatch && filenameMatch[1]) {
            filename = filenameMatch[1];
        }
    }

    const blob = await response.blob();
    return { isEmpty: false, filename, blob };
};

export const uploadUserPromptsZip = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    const result = await fetchApi('/user/prompts/upload-zip', {
        method: 'POST',
        body: formData,
    });
    cache.fileTree.clear(); 
    return result;
};


// --- Cache Management ---
export const clearUserSpecificCaches = () => {
    cache.fileTree.clear();
    cache.fileContent.clear();
    cache.charDefaultVariables.clear();
    console.log('User-specific API caches cleared (fileTree, fileContent, charDefaultVariables).');
};

export const clearAllCaches = () => {
    clearUserSpecificCaches();
    console.log('All API caches cleared.');
};