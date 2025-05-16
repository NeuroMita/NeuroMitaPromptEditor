// File: frontend\src\components\Panels\DslResultModal.js
import React from 'react';
import '../../styles/DslResultModal.css';

function DslResultModal({ title, content, onClose }) {

    return (
        <div className="modalOverlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="dsl-result-title">
            <div className="modalContent" onClick={e => e.stopPropagation()}>
                <div className="modalHeader">
                    <h3 id="dsl-result-title" className="modalTitle">{title}</h3>
                    <button onClick={onClose} aria-label="Close modal" className="modalCloseButton">×</button>
                </div>
                <div className="modalBody">
                    {content}
                </div>
                <div className="modalFooter">
                    <button onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
}

export default DslResultModal;