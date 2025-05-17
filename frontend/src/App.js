// File: frontend\src\App.js
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider, useAppContext } from './contexts/AppContext';
import EditorPage from './pages/EditorPage';
import LoginPage from './pages/LoginPage';
import PrivateRoute from './components/Auth/PrivateRoute'; // Import PrivateRoute
import './styles/App.css';
import './syntax/syntaxHighlighter.css';

// A small component to handle the root path redirection based on auth state
// This is useful if you want '/' to go to login or editor based on auth.
const RootRedirect = () => {
  const { isAuthenticated, isLoading } = useAppContext();

  if (isLoading) {
    return <div className="app-loading-spinner">Loading...</div>; // Consistent loading
  }

  return isAuthenticated ? <Navigate to="/editor" replace /> : <Navigate to="/login" replace />;
};


function AppContent() {
  // AppContent can now use useAppContext if needed, or just define routes
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route 
        path="/editor" 
        element={
          <PrivateRoute>
            <EditorPage />
          </PrivateRoute>
        } 
      />
      <Route path="/" element={<RootRedirect />} /> 
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AppProvider>
      <Router>
        <div className="App">
          <AppContent />
        </div>
      </Router>
    </AppProvider>
  );
}

export default App;