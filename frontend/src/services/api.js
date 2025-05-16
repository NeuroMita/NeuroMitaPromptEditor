// File: frontend\src\services\api.js
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

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
        if (response.status === 204) {
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('Fetch API error:', error);
        throw error;
    }
}

export const getPromptsRoot = () => fetchApi('/settings/prompts-root');

export const getFileTree = (relativePath = '.') => fetchApi(`/files/tree?path=${encodeURIComponent(relativePath)}`);
export const getFileContent = (filePath) => fetchApi(`/files/content?file_path=${encodeURIComponent(filePath)}`);
export const saveFileContent = (filePath, content) => fetchApi(`/files/content?file_path=${encodeURIComponent(filePath)}`, {
    method: 'POST',
    body: JSON.stringify({ content }),
});
export const createFileOrFolder = (parentDirPath, name, type) => fetchApi(`/files/create?parent_dir_path=${encodeURIComponent(parentDirPath)}`, {
    method: 'POST',
    body: JSON.stringify({ name, type }),
});
export const renameItem = (itemPath, newName) => fetchApi(`/files/rename?item_path=${encodeURIComponent(itemPath)}`, {
    method: 'PUT',
    body: JSON.stringify({ new_name: newName }),
});
export const deleteItem = (itemPath) => fetchApi(`/files/delete?item_path=${encodeURIComponent(itemPath)}`, {
    method: 'DELETE',
});


export const getCharacterDefaultVariables = (charId) => fetchApi(`/characters/${charId}/default-variables`);
export const generatePrompt = (charId, initialVariables, tags) => fetchApi(`/characters/${charId}/generate-prompt`, {
    method: 'POST',
    body: JSON.stringify({ initial_variables: initialVariables, tags }),
});