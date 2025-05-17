// File: frontend\src\components\Panels\DslVariablesPanel.js
import React, { useState, useEffect, useCallback } from 'react';
import { getCharacterStaticDefaults } from '../../services/api';
import '../../styles/DslVariablesPanel.css';

const getDisplayName = (path) => {
    if (!path) return "Character";
    return path.replace(/\\/g, '/').split('/').pop();
};

const variablesToString = (vars) => {
    if (Object.keys(vars).length === 0) return "";
    return Object.entries(vars)
        .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
        .join('\n');
};

const stringToVariables = (str) => {
    const newVars = {};
    str.split('\n').forEach(line => {
        const trimmedLine = line.trim();
        if (!trimmedLine || trimmedLine.startsWith('#') || trimmedLine.startsWith('//')) return;
        
        const parts = trimmedLine.split('=');
        if (parts.length >= 2) {
            const key = parts[0].trim();
            const valueStr = parts.slice(1).join('=').trim();
            try {
                newVars[key] = JSON.parse(valueStr);
            } catch (e) {
                if (valueStr.toLowerCase() === 'true') {
                    newVars[key] = true;
                } else if (valueStr.toLowerCase() === 'false') {
                    newVars[key] = false;
                } else if (!isNaN(valueStr) && valueStr.trim() !== '' && !valueStr.includes('.')) { // Целое число
                    newVars[key] = parseInt(valueStr, 10);
                } else if (!isNaN(valueStr) && valueStr.trim() !== '') { // Дробное число
                    newVars[key] = parseFloat(valueStr);
                } else { // Строка (убираем кавычки, если они есть по краям)
                     if ((valueStr.startsWith('"') && valueStr.endsWith('"')) || (valueStr.startsWith("'") && valueStr.endsWith("'"))) {
                        newVars[key] = valueStr.slice(1, -1);
                    } else {
                        newVars[key] = valueStr;
                    }
                }
            }
        }
    });
    return newVars;
};

function DslVariablesPanel({ characterId, onVariablesChange, isMobileView }) {
    const [textAreaValue, setTextAreaValue] = useState('');
    const [apiDefaultVariables, setApiDefaultVariables] = useState({});
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null); 

    const getLocalStorageKey = useCallback((charId) => {
        if (!charId) return null;
        return `userVars-${charId}`;
    }, []);

    useEffect(() => {
        if (characterId) {
            setIsLoading(true);
            setError(null);
            const characterName = getDisplayName(characterId);

            getCharacterStaticDefaults(characterName)
                .then(data => {
                    const defaultsFromServer = data.variables || {};
                    setApiDefaultVariables(defaultsFromServer);

                    const storageKey = getLocalStorageKey(characterId);
                    let varsToDisplay = { ...defaultsFromServer };

                    if (storageKey) {
                        const storedUserVarsJson = localStorage.getItem(storageKey);
                        if (storedUserVarsJson) {
                            try {
                                const storedUserVars = JSON.parse(storedUserVarsJson);
                                varsToDisplay = { ...defaultsFromServer, ...storedUserVars };
                            } catch (e) {
                                console.error(`Error parsing user vars from localStorage for ${characterId}:`, e);
                            }
                        }
                    }
                    setTextAreaValue(variablesToString(varsToDisplay));
                    onVariablesChange(varsToDisplay); 
                })
                .catch(err => {
                    console.error(`Failed to fetch static default variables for '${characterName}' (from path '${characterId}'):`, err);
                    setError(`Failed to load defaults for ${characterName}: ${err.message}`);
                    setApiDefaultVariables({});
                    setTextAreaValue('');
                    onVariablesChange({});
                })
                .finally(() => {
                    setIsLoading(false);
                });
        } else {
            setApiDefaultVariables({});
            setTextAreaValue('');
            setError(null);
            setIsLoading(false);
            onVariablesChange({});
        }
    }, [characterId, onVariablesChange, getLocalStorageKey]);

    const handleTextAreaChange = (e) => {
        const newText = e.target.value;
        setTextAreaValue(newText);

        const parsedVars = stringToVariables(newText);
        onVariablesChange(parsedVars); 

        const storageKey = getLocalStorageKey(characterId);
        if (storageKey) {
            if (Object.keys(parsedVars).length > 0 || newText.trim() === "") { 
                const varsToStore = {};
                let hasCustomValue = false;
                for (const key in parsedVars) {
                    if (JSON.stringify(parsedVars[key]) !== JSON.stringify(apiDefaultVariables[key])) {
                        varsToStore[key] = parsedVars[key];
                        hasCustomValue = true;
                    }
                }
                if (hasCustomValue || (Object.keys(parsedVars).length === 0 && Object.keys(apiDefaultVariables).length > 0) ) {
                    localStorage.setItem(storageKey, JSON.stringify(varsToStore));
                } else {
                    localStorage.removeItem(storageKey); 
                }
            }
        }
    };

    const handleRestoreDefaults = useCallback(() => {
        setTextAreaValue(variablesToString(apiDefaultVariables));
        onVariablesChange(apiDefaultVariables);

        const storageKey = getLocalStorageKey(characterId);
        if (storageKey) {
            localStorage.removeItem(storageKey);
        }
    }, [characterId, apiDefaultVariables, onVariablesChange, getLocalStorageKey]);
    
    const displayName = getDisplayName(characterId);

    return (
        <div className="dslVariablesPanel">
            {!isMobileView && (
                <div className="panelHeader">
                    <h4>Variables: {displayName || "Select Character"}</h4>
                </div>
            )}
            
            {isLoading && <p className="loading-text">Loading variables...</p>}
            {error && <p className="error-text small-error">{error}</p>}
            {!isLoading && characterId && (
                <>
                    <textarea
                        className="variablesTextarea"
                        value={textAreaValue}
                        onChange={handleTextAreaChange}
                        placeholder={"key1=value1\nkey2=\"string value\"\nkey3=true\nkey4=123"}
                        disabled={!characterId}
                    />
                    <button 
                        className="panelButton"
                        onClick={handleRestoreDefaults} 
                        disabled={!characterId || Object.keys(apiDefaultVariables).length === 0}
                    >
                        Restore Default Values
                    </button>
                </>
            )}
            {!characterId && !isLoading && !error && (
                <p className="panelMessage" style={{textAlign: 'center', padding: '20px'}}>
                    Select a character to edit its variables.
                </p>
            )}
        </div>
    );
}

export default DslVariablesPanel;