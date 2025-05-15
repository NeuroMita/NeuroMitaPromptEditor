// frontend/src/components/Panels/DslVariablesPanel.js
import React, { useState, useEffect, useCallback } from 'react';
import { getCharacterDefaultVariables } from '../../services/api';

const panelStyle = {
    padding: '10px',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
};

const textareaStyle = {
    flex: 1,
    width: '100%',
    boxSizing: 'border-box',
    padding: '8px',
    fontFamily: 'monospace',
    fontSize: '13px',
    border: '1px solid #ccc',
    marginBottom: '10px',
    backgroundColor: '#282c34', // Dark background
    color: '#abb2bf',       // Light text color
};

function parseVariables(text) {
    const variables = {};
    if (!text) return variables;
    text.split('\n').forEach(line => {
        line = line.trim();
        if (line && !line.startsWith('#') && !line.startsWith('//')) { // Ignore comments
            const parts = line.split('=');
            if (parts.length >= 2) {
                const key = parts[0].trim();
                let value = parts.slice(1).join('=').trim();
                // Basic type conversion (more robust parsing might be needed)
                if (value.toLowerCase() === 'true') {
                    value = true;
                } else if (value.toLowerCase() === 'false') {
                    value = false;
                } else if (!isNaN(value) && value.trim() !== '') {
                    value = Number(value);
                } else if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
                    value = value.substring(1, value.length - 1);
                }
                variables[key] = value;
            }
        }
    });
    return variables;
}

function formatVariables(variablesObject) {
    if (!variablesObject || Object.keys(variablesObject).length === 0) return "";
    return Object.entries(variablesObject)
        .map(([key, value]) => `${key}=${value}`)
        .join('\n');
}


function DslVariablesPanel({ characterId, onVariablesChange }) {
    const [text, setText] = useState('');
    const [isLoadingDefaults, setIsLoadingDefaults] = useState(false);

    const fetchAndSetDefaults = useCallback(async (charId) => {
        if (!charId) {
            setText('');
            onVariablesChange({});
            return;
        }
        setIsLoadingDefaults(true);
        try {
            const response = await getCharacterDefaultVariables(charId);
            const formattedVars = formatVariables(response.variables);
            setText(formattedVars);
            onVariablesChange(response.variables);
        } catch (error) {
            console.error(`Failed to fetch default variables for ${charId}:`, error);
            setText(`# Error loading defaults for ${charId}\n`);
            onVariablesChange({});
        } finally {
            setIsLoadingDefaults(false);
        }
    }, [onVariablesChange]);

    useEffect(() => {
        fetchAndSetDefaults(characterId);
    }, [characterId, fetchAndSetDefaults]);

    const handleChange = (event) => {
        const newText = event.target.value;
        setText(newText);
        const parsed = parseVariables(newText);
        onVariablesChange(parsed);
    };

    const handleResetToDefaults = () => {
        if (characterId) {
            fetchAndSetDefaults(characterId);
        } else {
            setText('');
            onVariablesChange({});
        }
    };

    return (
        <div style={panelStyle}>
            <h4>DSL Variables {characterId ? `for ${characterId}` : ''}</h4>
            {isLoadingDefaults && <p>Loading default variables...</p>}
            <textarea
                style={textareaStyle}
                value={text}
                onChange={handleChange}
                placeholder="varName=value
anotherVar=123
isCool=true"
                aria-label="DSL Variables Input"
            />
            <button onClick={handleResetToDefaults} disabled={isLoadingDefaults || !characterId}>
                Reset to Defaults for {characterId || '...'}
            </button>
        </div>
    );
}

export default DslVariablesPanel;