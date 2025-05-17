// File: frontend\src\components\Auth\PrivateRoute.js
import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAppContext } from '../../contexts/AppContext';

const PrivateRoute = ({ children }) => {
    const { isAuthenticated, isLoading } = useAppContext();
    const location = useLocation();

    if (isLoading) {
        return <div className="app-loading-spinner">Loading application...</div>;
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    return children;
};

export default PrivateRoute;