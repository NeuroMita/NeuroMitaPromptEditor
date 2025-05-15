// frontend/src/components/Panels/LogPanel.js
import React, { useEffect, useRef } from 'react';

const panelStyle = {
    padding: '10px',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: '#1e1e1e', // Dark background for logs
    color: '#d4d4d4',
};

const logAreaStyle = {
    flex: 1,
    overflowY: 'auto',
    fontFamily: 'monospace',
    fontSize: '12px',
    whiteSpace: 'pre-wrap', // Preserve whitespace and newlines
    wordBreak: 'break-all',
    border: '1px solid #333',
    padding: '5px',
};

const getLogLevelColor = (level) => {
    switch (level?.toUpperCase()) {
        case 'ERROR':
        case 'CRITICAL':
            return '#f48771'; // Reddish
        case 'WARNING':
            return '#f8c271'; // Orange/Yellow
        case 'INFO':
            return '#71b0f8'; // Blueish
        case 'DEBUG':
            return '#8c8c8c'; // Grey
        default:
            return '#d4d4d4'; // Default text color
    }
};

function LogPanel({ logs, onClearLogs }) { // logs: [{ level, message, name?, timestamp? }]
    const logAreaRef = useRef(null);

    useEffect(() => {
        if (logAreaRef.current) {
            logAreaRef.current.scrollTop = logAreaRef.current.scrollHeight;
        }
    }, [logs]); // Scroll to bottom when logs change

    return (
        <div style={panelStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
                <h4>Logs</h4>
                {onClearLogs && <button onClick={onClearLogs}>Clear Logs</button>}
            </div>
            <div ref={logAreaRef} style={logAreaStyle}>
                {logs && logs.length > 0 ? (
                    logs.map((log, index) => (
                        <div key={index} style={{ color: getLogLevelColor(log.level), marginBottom: '2px' }}>
                            {log.timestamp && `[${log.timestamp}] `}
                            {log.name && `[${log.name}] `}
                            {log.level && `[${log.level.toUpperCase()}] `}
                            {log.message}
                        </div>
                    ))
                ) : (
                    <p>No logs yet.</p>
                )}
            </div>
        </div>
    );
}

export default LogPanel;