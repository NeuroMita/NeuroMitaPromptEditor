// File: frontend\src\pages\LoginPage.js
import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppContext } from '../contexts/AppContext';
import { registerUser as apiRegisterUser } from '../services/api'; // Import registerUser
import '../styles/LoginPage.css';

function LoginPage() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState(''); // For registration
    const [inviteCode, setInviteCode] = useState(''); // For registration
    const [isRegisterView, setIsRegisterView] = useState(false); // Toggle between login and register

    const [isProcessing, setIsProcessing] = useState(false); // Combined loading state for login/register
    const { login, isAuthenticated, authError, setAuthError, isLoading: isAppLoading } = useAppContext();
    const navigate = useNavigate();
    const location = useLocation();

    const from = location.state?.from?.pathname || "/editor"; // Redirect to editor page after successful login

    useEffect(() => {
        if (isAuthenticated && !isAppLoading) {
            navigate(from, { replace: true });
        }
        // Clear auth error when component mounts or view changes (e.g. login to register)
        // This is now handled in toggleView and when submitting forms
        // return () => {
        //     setAuthError(null); 
        // };
    }, [isAuthenticated, navigate, from, isAppLoading]); // Removed setAuthError from deps

    const handleLoginSubmit = async (e) => {
        e.preventDefault();
        if (!username || !password) {
            setAuthError("Username and password are required.");
            return;
        }
        setIsProcessing(true);
        setAuthError(null);
        const success = await login(username, password); // login comes from AppContext
        setIsProcessing(false);
        if (success) {
            navigate(from, { replace: true });
        }
        // authError will be set by AppContext's login if it fails
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
            setIsRegisterView(false); // Switch back to login view
            // Keep username, clear other fields for login
            setPassword('');
            setConfirmPassword('');
            setInviteCode(''); // This field is not in login view anyway
        } catch (error) {
            setAuthError(error.message || "Registration failed. Please try again.");
        } finally {
            setIsProcessing(false);
        }
    };

    const toggleView = () => {
        setIsRegisterView(!isRegisterView);
        setAuthError(null); // Clear errors when switching views
        // Clear all form fields when toggling for a cleaner experience
        setUsername('');
        setPassword('');
        setConfirmPassword('');
        setInviteCode('');
    };

    if (isAppLoading && !isAuthenticated) { // Only show page loading if app context is loading and not yet authed
        return <div className="login-page-loading">Loading...</div>;
    }

    return (
        <div className="login-page-container">
            <div className="login-form-wrapper">
                <h2>{isRegisterView ? 'Register New Account' : 'Login to Prompt Editor'}</h2>
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
                                />
                            </div>
                        </>
                    )}
                    {authError && <p className="error-message">{authError}</p>}
                    <button type="submit" className="login-button" disabled={isProcessing}>
                        {isProcessing ? 'Processing...' : (isRegisterView ? 'Register' : 'Login')}
                    </button>
                </form>
                <div className="toggle-view-container">
                    <button type="button" onClick={toggleView} className="toggle-view-button">
                        {isRegisterView ? 'Already have an account? Login' : 'Need an account? Register'}
                    </button>
                </div>
                {!isRegisterView && (
                    <div className="login-info">
                        <p>Default users (if available):</p>
                        <ul>
                            <li>admin / password123</li>
                            <li>testuser / testpass</li>
                        </ul>
                    </div>
                )}
            </div>
        </div>
    );
}

export default LoginPage;