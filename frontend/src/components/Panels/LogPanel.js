// File: frontend\src\components\Panels\LogPanel.js
import React, { useState, useEffect, useMemo, useRef } from 'react';
import '../../styles/LogPanel.css';

const LOG_LEVEL_MAP = { // Mapping text levels to numeric for comparison
    ALL: 0,
    DEBUG: 10,
    INFO: 20,
    WARNING: 30,
    ERROR: 40,
};

const LOG_LEVEL_DISPLAY_NAMES = {
    [LOG_LEVEL_MAP.ALL]: "All Levels",
    [LOG_LEVEL_MAP.DEBUG]: "Debug",
    [LOG_LEVEL_MAP.INFO]: "Info",
    [LOG_LEVEL_MAP.WARNING]: "Warning",
    [LOG_LEVEL_MAP.ERROR]: "Error",
};

const ALL_LOGGERS_SENTINEL = "<All Loggers>";
const MAX_DISPLAY_LOGS = 1000; // Limit number of logs displayed for performance

function LogPanel({ logs, onClearLogs }) {
    const [currentLevelFilter, setCurrentLevelFilter] = useState(LOG_LEVEL_MAP.ALL);
    const [currentLoggerFilter, setCurrentLoggerFilter] = useState(ALL_LOGGERS_SENTINEL);
    const [searchTerm, setSearchTerm] = useState("");

    const logAreaRef = useRef(null);
    const isScrolledToBottomRef = useRef(true); // Track if user is at the bottom

    const { availableLoggers, warningCount, errorCount } = useMemo(() => {
        const loggerNames = new Set([ALL_LOGGERS_SENTINEL]);
        let warnings = 0;
        let errors = 0;
        (logs || []).forEach(log => {
            if (log.name) {
                loggerNames.add(log.name);
            }
            const levelNum = LOG_LEVEL_MAP[log.level?.toUpperCase()] || LOG_LEVEL_MAP.INFO;
            if (levelNum === LOG_LEVEL_MAP.WARNING) {
                warnings++;
            } else if (levelNum >= LOG_LEVEL_MAP.ERROR) {
                errors++;
            }
        });
        return {
            availableLoggers: Array.from(loggerNames).sort(),
            warningCount: warnings,
            errorCount: errors,
        };
    }, [logs]);

    const filteredLogs = useMemo(() => {
        return (logs || [])
            .filter(log => {
                const levelNum = LOG_LEVEL_MAP[log.level?.toUpperCase()] || LOG_LEVEL_MAP.INFO;
                const levelPass = currentLevelFilter === LOG_LEVEL_MAP.ALL || levelNum >= currentLevelFilter;
                const loggerPass = currentLoggerFilter === ALL_LOGGERS_SENTINEL || log.name === currentLoggerFilter;
                
                const messageContent = log.message || "";
                const nameContent = log.name || "";
                const searchPass = searchTerm === "" || 
                                   messageContent.toLowerCase().includes(searchTerm.toLowerCase()) ||
                                   nameContent.toLowerCase().includes(searchTerm.toLowerCase());
                return levelPass && loggerPass && searchPass;
            })
            .slice(-MAX_DISPLAY_LOGS);
    }, [logs, currentLevelFilter, currentLoggerFilter, searchTerm]);

    useEffect(() => {
        if (logAreaRef.current && isScrolledToBottomRef.current) {
            logAreaRef.current.scrollTop = logAreaRef.current.scrollHeight;
        }
    }, [filteredLogs]);

    const handleScroll = () => {
        if (logAreaRef.current) {
            const { scrollHeight, clientHeight, scrollTop } = logAreaRef.current;
            // Check if scrolled to bottom (with a small tolerance)
            isScrolledToBottomRef.current = scrollHeight - clientHeight <= scrollTop + 10;
        }
    };

    const handleClear = () => {
        if (onClearLogs) {
            onClearLogs();
        }
        // Counts will auto-reset via useMemo when logs prop becomes empty
    };

    const getLogLevelClass = (levelStr) => {
        const levelUpper = levelStr?.toUpperCase();
        if (levelUpper === "ERROR") return "ERROR";
        if (levelUpper === "WARNING") return "WARNING";
        if (levelUpper === "INFO") return "INFO";
        if (levelUpper === "DEBUG") return "DEBUG";
        return "";
    };
    
    const formatLogMessage = (log) => {
        // If log.message comes pre-formatted (e.g. with timestamp from Python backend)
        // we can just return it. Otherwise, assemble it here.
        // For now, assume log.message is the primary content.
        return log.message; 
    };

    return (
        <div className="logPanel">
            <div className="logPanelHeader"> {/* This is now a .panelHeader from App.css */}
                <div className="logFilters">
                    <label htmlFor="logLevelFilter" className="logFilterLabel">Level:</label>
                    <select
                        id="logLevelFilter"
                        className="logFilterSelect"
                        value={currentLevelFilter}
                        onChange={(e) => {
                            setCurrentLevelFilter(Number(e.target.value));
                            isScrolledToBottomRef.current = true; // Auto-scroll on filter change
                        }}
                    >
                        {Object.entries(LOG_LEVEL_DISPLAY_NAMES).map(([levelVal, levelName]) => (
                            <option key={levelVal} value={levelVal}>{levelName}</option>
                        ))}
                    </select>

                    <label htmlFor="loggerFilter" className="logFilterLabel">Logger:</label>
                    <select
                        id="loggerFilter"
                        className="logFilterSelect"
                        value={currentLoggerFilter}
                        onChange={(e) => {
                            setCurrentLoggerFilter(e.target.value);
                            isScrolledToBottomRef.current = true; // Auto-scroll on filter change
                        }}
                    >
                        {availableLoggers.map(loggerName => (
                            <option key={loggerName} value={loggerName}>{loggerName}</option>
                        ))}
                    </select>
                     <input 
                        type="text" 
                        placeholder="Search logs..."
                        className="logSearchInput"
                        value={searchTerm}
                        onChange={(e) => {
                            setSearchTerm(e.target.value);
                            isScrolledToBottomRef.current = true; // Auto-scroll on filter change
                        }}
                    />
                </div>
                <div className="logCountersAndActions">
                    <span className="logCounterItem" title={`Warnings: ${warningCount}`}>
                        <span className="logIcon warningIcon">⚠️</span> {warningCount}
                    </span>
                    <span className="logCounterItem" title={`Errors: ${errorCount}`}>
                        <span className="logIcon errorIcon">🛑</span> {errorCount}
                    </span>
                    <button onClick={handleClear} className="clearLogsButton" title="Clear Logs">
                        🗑️ Clear
                    </button>
                </div>
            </div>
            <div ref={logAreaRef} className="logArea" onScroll={handleScroll}>
                {(filteredLogs || []).length > 0 ? (
                    filteredLogs.map((log, index) => (
                        <div key={index} className={`logEntry ${getLogLevelClass(log.level)}`}>
                            {log.timestamp && <span className="logEntryTimestamp">{`[${log.timestamp}]`}</span>}
                            {log.name && <span className="logEntryName">{`[${log.name}]`}</span>}
                            {log.level && <span className="logEntryLevel">{`[${log.level.toUpperCase()}]`}</span>}
                            <span className="logEntryMessage">{formatLogMessage(log)}</span>
                        </div>
                    ))
                ) : (
                    <p className="noLogsMessage">
                        {(logs || []).length > 0 ? "No logs match current filters." : "No logs yet."}
                    </p>
                )}
            </div>
        </div>
    );
}

export default LogPanel;