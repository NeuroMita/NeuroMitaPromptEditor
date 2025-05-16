// File: frontend\src\components\Panels\LogPanel.js
import React, { useEffect, useRef } from 'react';
import '../../styles/LogPanel.css';

function LogPanel({ logs, onClearLogs }) {
    const logAreaRef = useRef(null);

    useEffect(() => {
        if (logAreaRef.current) {
            logAreaRef.current.scrollTop = logAreaRef.current.scrollHeight;
        }
    }, [logs]);

    return (
        <div className="logPanel">
            <div className="logPanelHeader">
                <h4>Logs</h4>
                {onClearLogs && <button onClick={onClearLogs}>Clear Logs</button>}
            </div>
            <div ref={logAreaRef} className="logArea">
                {logs && logs.length > 0 ? (
                    logs.map((log, index) => (
                        <div key={index} className={`logEntry ${log.level ? log.level.toUpperCase() : ''}`}>
                            {log.timestamp && <span className="logEntryTimestamp">{`[${log.timestamp}]`}</span>}
                            {log.name && <span className="logEntryName">{`[${log.name}]`}</span>}
                            {log.level && <span className="logEntryLevel">{`[${log.level.toUpperCase()}]`}</span>}
                            {log.message}
                        </div>
                    ))
                ) : (
                    <p className="noLogsMessage">No logs yet.</p>
                )}
            </div>
        </div>
    );
}

export default LogPanel;