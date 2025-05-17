// File: frontend\src\contexts\AppContext.js
import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import { loginUser as apiLoginUser, getUserPromptsInfo as apiGetUserPromptsInfo, clearUserSpecificCaches } from '../services/api';

const AppContext = createContext();

export const useAppContext = () => useContext(AppContext);

export const AppProvider = ({ children }) => {
    const [token, setToken] = useState(localStorage.getItem('authToken'));
    const [isAuthenticated, setIsAuthenticated] = useState(!!token);
    const [currentUser, setCurrentUser] = useState(null); // Placeholder for user data like username
    
    const [userPromptsInfo, setUserPromptsInfo] = useState(null); // { user_prompts_message, user_prompts_relative_path }
    
    const [selectedCharacterId, setSelectedCharacterId] = useState(null);
    const [isLoading, setIsLoading] = useState(true); // App/auth loading state
    const [authError, setAuthError] = useState(null);

    const handleLogout = useCallback((clearCaches = true, errorMsg = null) => {
        localStorage.removeItem('authToken');
        setToken(null);
        setIsAuthenticated(false);
        setCurrentUser(null);
        setUserPromptsInfo(null);
        setSelectedCharacterId(null);
        if (errorMsg) setAuthError(errorMsg);
        else setAuthError(null);

        if (clearCaches) {
            clearUserSpecificCaches();
        }
        setIsLoading(false); // Ensure loading is false after logout
        console.log("User logged out.");
        // Future: redirect to login page using react-router history.push('/login')
    }, []);

    const fetchAuthenticatedUserData = useCallback(async () => {
        if (!token) {
            setIsAuthenticated(false);
            setIsLoading(false);
            return;
        }
        setIsLoading(true);
        try {
            const promptsInfoData = await apiGetUserPromptsInfo();
            setUserPromptsInfo(promptsInfoData);
            
            // Decode token to get username for display (example)
            // This is a simplified way; a /users/me endpoint is more robust
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                setCurrentUser({ username: payload.sub });
            } catch (e) {
                console.error("Failed to decode token for username:", e);
                // Still authenticated, but username might not be available this way
            }

            setIsAuthenticated(true);
            setAuthError(null);
        } catch (err) {
            console.error("Failed to fetch user data or initial settings:", err);
            handleLogout(true, err.message || "Session might be invalid. Please login again.");
        } finally {
            setIsLoading(false);
        }
    }, [token, handleLogout]);

    useEffect(() => {
        fetchAuthenticatedUserData();
        
        const handleAuthError = (event) => {
            console.warn("Global auth error (401) detected from API call to:", event.detail?.endpoint);
            handleLogout(true, "Your session has expired or is invalid. Please log in again.");
        };
        window.addEventListener('auth-error-401', handleAuthError);
        return () => {
            window.removeEventListener('auth-error-401', handleAuthError);
        };

    }, [fetchAuthenticatedUserData, handleLogout]); // token change triggers fetchAuthenticatedUserData

    const handleLogin = async (username, password) => {
        setIsLoading(true);
        setAuthError(null);
        try {
            const data = await apiLoginUser(username, password);
            localStorage.setItem('authToken', data.access_token);
            setToken(data.access_token); // This will trigger useEffect to fetch user data
            // fetchAuthenticatedUserData will be called by useEffect due to token change
            // No need to setIsLoading(false) here, fetchAuthenticatedUserData will do it.
            return true; 
        } catch (err) {
            console.error("Login failed:", err);
            handleLogout(false, err.message || "Login failed. Please check credentials."); // Logout without clearing caches if login itself failed
            return false;
        }
    };
    
    const value = {
        token,
        isAuthenticated,
        currentUser,
        login: handleLogin,
        logout: handleLogout,
        authError,
        setAuthError, // Allow components to clear auth errors displayed in UI

        userPromptsInfo,
        
        selectedCharacterId,
        setSelectedCharacterId,
        
        isLoading, 
    };

    return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};