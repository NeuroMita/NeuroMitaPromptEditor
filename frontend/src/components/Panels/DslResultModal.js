// frontend/src/components/Panels/DslResultModal.js
import React from 'react';

const modalOverlayStyle = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
};

const modalContentStyle = {
    backgroundColor: '#fff',
    padding: '20px',
    borderRadius: '5px',
    width: '80%',
    maxWidth: '700px',
    maxHeight: '80vh',
    display: 'flex',
    flexDirection: 'column',
    boxShadow: '0 4px 8px rgba(0,0,0,0.2)',
    color: '#333', // Reset text color for modal content
};

const modalHeaderStyle = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottom: '1px solid #eee',
    paddingBottom: '10px',
    marginBottom: '10px',
};

const modalBodyStyle = {
    flex: 1,
    overflowY: 'auto',
    whiteSpace: 'pre-wrap',
    fontFamily: 'monospace',
    fontSize: '13px',
    backgroundColor: '#f9f9f9',
    padding: '10px',
    border: '1px solid #ddd',
};

const modalFooterStyle = {
    borderTop: '1px solid #eee',
    paddingTop: '10px',
    marginTop: '10px',
    textAlign: 'right',
};

function DslResultModal({ title, content, onClose }) {
    // Optional: Add token count/cost display here if you move that logic to frontend
    // For now, just displays the generated prompt.

    return (
        <div style={modalOverlayStyle} onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="dsl-result-title">
            <div style={modalContentStyle} onClick={e => e.stopPropagation()}> {/* Prevent closing when clicking inside modal */}
                <div style={modalHeaderStyle}>
                    <h3 id="dsl-result-title" style={{ margin: 0 }}>{title}</h3>
                    <button onClick={onClose} aria-label="Close modal" style={{background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer'}}>×</button>
                </div>
                <div style={modalBodyStyle}>
                    {content}
                </div>
                <div style={modalFooterStyle}>
                    <button onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
}

export default DslResultModal;