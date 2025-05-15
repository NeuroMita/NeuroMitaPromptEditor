import React from 'react';
import { AppProvider } from './contexts/AppContext';
import EditorPage from './pages/EditorPage';
import './styles/App.css'; // You'll create this for global styles

function App() {
  return (
    <AppProvider>
      <div className="App">
        <EditorPage />
      </div>
    </AppProvider>
  );
}

export default App;