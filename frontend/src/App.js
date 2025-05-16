import React from 'react';
import { AppProvider } from './contexts/AppContext';
import EditorPage from './pages/EditorPage';
import './styles/App.css'; 

function App() {
  return (
    <AppProvider>
      <div className="App"> {/* .App class from App.css */}
        <EditorPage />
      </div>
    </AppProvider>
  );
}

export default App;