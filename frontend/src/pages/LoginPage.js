// File: frontend\src\pages\LoginPage.js
import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppContext } from '../contexts/AppContext';
import { registerUser as apiRegisterUser } from '../services/api'; 
import '../styles/LoginPage.css';

function LoginPage() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState(''); 
    const [inviteCode, setInviteCode] = useState(''); 
    const [isRegisterView, setIsRegisterView] = useState(false); 

    const [isProcessing, setIsProcessing] = useState(false); 
    const { login, isAuthenticated, authError, setAuthError, isLoading: isAppLoading } = useAppContext();
    const navigate = useNavigate();
    const location = useLocation();

    const from = location.state?.from?.pathname || "/editor"; 

    useEffect(() => {
        if (isAuthenticated && !isAppLoading) {
            navigate(from, { replace: true });
        }
    }, [isAuthenticated, navigate, from, isAppLoading]); 

    const handleLoginSubmit = async (e) => {
        e.preventDefault();
        if (!username || !password) {
            setAuthError("Username and password are required.");
            return;
        }
        setIsProcessing(true);
        setAuthError(null);
        const success = await login(username, password); 
        setIsProcessing(false);
        if (success) {
            navigate(from, { replace: true });
        }
    };

    const handleRegisterSubmit = async (e) => {
        e.preventDefault();
        if (!username || !password || !confirmPassword || !inviteCode) {
            setAuthError("All fields are required for registration.");
            return;
        }
        if (password.length < 6) {
            setAuthError("Password must be at least 6 characters long.");
            return;
        }
        if (password !== confirmPassword) {
            setAuthError("Passwords do not match.");
            return;
        }
        setIsProcessing(true);
        setAuthError(null);
        try {
            await apiRegisterUser(username, password, inviteCode);
            alert("Registration successful! Please log in.");
            setIsRegisterView(false); 
            setPassword('');
            setConfirmPassword('');
            setInviteCode(''); 
        } catch (error) {
            setAuthError(error.message || "Registration failed. Please try again.");
        } finally {
            setIsProcessing(false);
        }
    };

    const toggleView = () => {
        setIsRegisterView(!isRegisterView);
        setAuthError(null); 
        setUsername('');
        setPassword('');
        setConfirmPassword('');
        setInviteCode('');
    };

    if (isAppLoading && !isAuthenticated) { 
        return <div className="login-page-loading">Loading...</div>;
    }

    return (
        <div className="login-page-container">
            <div className="login-card">
                <h1 className="login-title">
                    {isRegisterView ? 'Create Account' : 'Welcome Back'}
                </h1>
                <p className="login-subtitle">
                    {isRegisterView ? 'Get started with the Prompt Editor.' : 'Sign in to continue to the Prompt Editor.'}
                </p>

                <form onSubmit={isRegisterView ? handleRegisterSubmit : handleLoginSubmit} className="login-form">
                    <div className="form-group">
                        <label htmlFor="username">Username</label>
                        <input
                            type="text"
                            id="username"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            disabled={isProcessing}
                            autoFocus
                            required
                            autoComplete="username"
                            placeholder="Enter your username"
                        />
                    </div>
                    <div className="form-group">
                        <label htmlFor="password">Password</label>
                        <input
                            type="password"
                            id="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            disabled={isProcessing}
                            required
                            minLength={isRegisterView ? 6 : undefined}
                            autoComplete={isRegisterView ? "new-password" : "current-password"}
                            placeholder={isRegisterView ? "Create a password (min. 6 chars)" : "Enter your password"}
                        />
                    </div>
                    {isRegisterView && (
                        <>
                            <div className="form-group">
                                <label htmlFor="confirmPassword">Confirm Password</label>
                                <input
                                    type="password"
                                    id="confirmPassword"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    disabled={isProcessing}
                                    required
                                    minLength={6}
                                    autoComplete="new-password"
                                    placeholder="Confirm your password"
                                />
                            </div>
                            <div className="form-group">
                                <label htmlFor="inviteCode">Invite Code</label>
                                <input
                                    type="text" 
                                    id="inviteCode"
                                    value={inviteCode}
                                    onChange={(e) => setInviteCode(e.target.value)}
                                    disabled={isProcessing}
                                    required
                                    placeholder="Enter your invite code"
                                />
                            </div>
                        </>
                    )}
                    {authError && <p className="error-message">{authError}</p>}
                    <button type="submit" className="login-button" disabled={isProcessing || (isRegisterView && password.length >0 && password.length < 6)}>
                        {isProcessing ? (
                            <span className="spinner" /> 
                        ) : (isRegisterView ? 'Register' : 'Login')}
                    </button>
                </form>
                <div className="toggle-view-container">
                    <button type="button" onClick={toggleView} className="toggle-view-button">
                        {isRegisterView ? 'Already have an account? Sign In' : "Don't have an account? Sign Up"}
                    </button>
                </div>
            </div>
        </div>
    );
}

export default LoginPage;