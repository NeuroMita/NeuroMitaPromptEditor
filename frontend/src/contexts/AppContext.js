import React, { createContext, useState, useContext, useEffect } from 'react';
import { getPromptsRoot } from '../services/api';

const AppContext = createContext();

export const useAppContext = () => useContext(AppContext);

export const AppProvider = ({ children }) => {
    const [promptsRoot, setPromptsRoot] = useState('');
    const [selectedCharacterId, setSelectedCharacterId] = useState(null); // e.g., "Hero"
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchInitialData = async () => {
            setIsLoading(true);
            try {
                const rootData = await getPromptsRoot();
                setPromptsRoot(rootData.prompts_root_path);
                setError(null);
            } catch (err) {
                console.error("Failed to fetch prompts root:", err);
                setError(err.message || "Failed to load initial configuration.");
                setPromptsRoot('/error/could/not/load/prompts_root'); // Fallback or error display
            } finally {
                setIsLoading(false);
            }
        };
        fetchInitialData();
    }, []);

    const value = {
        promptsRoot,
        selectedCharacterId,
        setSelectedCharacterId,
        isLoading,
        error,
    };

    return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};