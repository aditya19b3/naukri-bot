import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, 
  Square, 
  Settings as SettingsIcon, 
  Terminal, 
  Search, 
  RefreshCw, 
  Sliders, 
  User, 
  MapPin, 
  Briefcase, 
  ExternalLink, 
  FileText, 
  Plus, 
  X, 
  Wifi, 
  WifiOff, 
  Database,
  CheckCircle,
  FileSpreadsheet
} from 'lucide-react';

const decodeJwt = (token) => {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
};

export default function App() {
  // Navigation
  const [activeTab, setActiveTab] = useState('home');

  // Auth state
  const [authConfig, setAuthConfig] = useState({ users_mode: "2", google_client_id: "", auth_enabled: false });
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userProfile, setUserProfile] = useState(null);

  // Backend Connection
  const [backendUrl, setBackendUrl] = useState(() => {
    return localStorage.getItem('naukri_bot_backend_url') || 'http://127.0.0.1:8000';
  });
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState('');

  // Bot Status
  const [isRunning, setIsRunning] = useState(false);
  const [pid, setPid] = useState(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [stats, setStats] = useState({
    applied: 0,
    already_applied: 0,
    external_redirect: 0,
    skipped: 0,
    failed: 0,
    total: 0,
    quota_hit: false
  });

  // Logs and Results
  const [logs, setLogs] = useState('Checking connection to backend...');
  const [results, setResults] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  // Configurations
  const [config, setConfig] = useState({});
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [configSaveSuccess, setConfigSaveSuccess] = useState(false);

  // Dynamic tags input help states
  const [newKeyword, setNewKeyword] = useState('');
  const [newPrefLocation, setNewPrefLocation] = useState('');
  const [newSkill, setNewSkill] = useState('');

  const terminalEndRef = useRef(null);

  // Helper to construct Authorization header
  const getHeaders = (extraHeaders = {}) => {
    const token = localStorage.getItem('naukri_bot_google_token');
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...extraHeaders
    };
  };

  // Fetch auth config on startup
  const fetchAuthConfig = async () => {
    try {
      const cleanUrl = backendUrl.replace(/\/$/, '');
      const response = await fetch(`${cleanUrl}/api/auth-config`);
      if (response.ok) {
        const data = await response.json();
        setAuthConfig(data);
        
        if (data.auth_enabled) {
          const token = localStorage.getItem('naukri_bot_google_token');
          if (token) {
            const decoded = decodeJwt(token);
            if (decoded && decoded.exp * 1000 > Date.now()) {
              setUserProfile(decoded);
              setIsAuthenticated(true);
              return { auth_enabled: true, authenticated: true };
            } else {
              localStorage.removeItem('naukri_bot_google_token');
            }
          }
          setIsAuthenticated(false);
          return { auth_enabled: true, authenticated: false };
        } else {
          setIsAuthenticated(true); // Bypass auth
          return { auth_enabled: false, authenticated: true };
        }
      }
    } catch (err) {
      console.error('Error fetching auth config:', err);
    }
    return { auth_enabled: false, authenticated: false };
  };

  // Handle successful Google login
  const handleGoogleLoginSuccess = (response) => {
    const token = response.credential;
    const decoded = decodeJwt(token);
    if (decoded) {
      localStorage.setItem('naukri_bot_google_token', token);
      setUserProfile(decoded);
      setIsAuthenticated(true);
      checkConnection(true).then((connected) => {
        if (connected) {
          fetchStatus();
          fetchConfig();
          fetchResults();
          fetchLogs();
        }
      });
    } else {
      alert('Failed to parse Google Login token.');
    }
  };

  // Handle logout
  const handleLogout = () => {
    localStorage.removeItem('naukri_bot_google_token');
    setIsAuthenticated(false);
    setUserProfile(null);
    setActiveTab('home');
  };

  // Save backendUrl to localStorage when changed
  const handleBackendUrlChange = (e) => {
    const val = e.target.value.trim();
    setBackendUrl(val);
    localStorage.setItem('naukri_bot_backend_url', val);
  };

  // Test backend connection and load configurations
  const checkConnection = async (showLogs = false) => {
    try {
      const cleanUrl = backendUrl.replace(/\/$/, '');
      const response = await fetch(`${cleanUrl}/api/status`, { 
        headers: getHeaders(),
        signal: AbortSignal.timeout(3000) 
      });
      if (response.ok) {
        setIsConnected(true);
        setConnectionError('');
        if (showLogs) setLogs(prev => prev + '\n[UI] Connected to backend API successfully.');
        return true;
      } else {
        throw new Error('Non-200 response');
      }
    } catch (err) {
      setIsConnected(false);
      setConnectionError(`Could not connect to backend at ${backendUrl}. Make sure backend.py is running.`);
      if (showLogs) setLogs(prev => prev + `\n[UI] Connection failed. Target: ${backendUrl}`);
      return false;
    }
  };

  // Fetch bot status and statistics
  const fetchStatus = async () => {
    if (!backendUrl) return;
    try {
      const cleanUrl = backendUrl.replace(/\/$/, '');
      const response = await fetch(`${cleanUrl}/api/status`, { headers: getHeaders() });
      if (response.ok) {
        const data = await response.json();
        setIsRunning(data.running);
        setPid(data.pid);
        setElapsedSeconds(data.elapsed_seconds);
        setStats(data.stats);
        setIsConnected(true);
        setConnectionError('');
      }
    } catch (err) {
      setIsConnected(false);
    }
  };

  // Fetch execution logs
  const fetchLogs = async () => {
    if (!isConnected) return;
    try {
      const cleanUrl = backendUrl.replace(/\/$/, '');
      const response = await fetch(`${cleanUrl}/api/logs?lines=150`, { headers: getHeaders() });
      if (response.ok) {
        const data = await response.json();
        setLogs(data.logs);
      }
    } catch (err) {
      console.error('Error fetching logs:', err);
    }
  };

  // Fetch results table
  const fetchResults = async () => {
    if (!isConnected) return;
    try {
      const cleanUrl = backendUrl.replace(/\/$/, '');
      const response = await fetch(`${cleanUrl}/api/results`, { headers: getHeaders() });
      if (response.ok) {
        const data = await response.json();
        setResults(data);
      }
    } catch (err) {
      console.error('Error fetching results:', err);
    }
  };

  // Fetch configuration parameters from backend
  const fetchConfig = async () => {
    if (!isConnected) return;
    try {
      const cleanUrl = backendUrl.replace(/\/$/, '');
      const response = await fetch(`${cleanUrl}/api/config`, { headers: getHeaders() });
      if (response.ok) {
        const data = await response.json();
        setConfig(data);
      }
    } catch (err) {
      console.error('Error fetching config:', err);
    }
  };

  // Save configurations to backend
  const saveConfig = async (e) => {
    if (e) e.preventDefault();
    if (!isConnected) return;
    setIsSavingConfig(true);
    setConfigSaveSuccess(false);

    try {
      const cleanUrl = backendUrl.replace(/\/$/, '');
      const response = await fetch(`${cleanUrl}/api/config`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ settings: config })
      });
      if (response.ok) {
        setConfigSaveSuccess(true);
        setTimeout(() => setConfigSaveSuccess(false), 3000);
      } else {
        alert('Failed to save config.');
      }
    } catch (err) {
      alert(`Error saving config: ${err.message}`);
    } finally {
      setIsSavingConfig(false);
    }
  };

  // Start bot execution
  const startBot = async () => {
    if (!isConnected) return;
    try {
      const cleanUrl = backendUrl.replace(/\/$/, '');
      const response = await fetch(`${cleanUrl}/api/start`, { 
        method: 'POST',
        headers: getHeaders()
      });
      if (response.ok) {
        setIsRunning(true);
        setLogs('Starting Naukri bot run in background...\n');
        // Instantly poll status and results
        setTimeout(() => {
          fetchStatus();
          fetchLogs();
        }, 500);
      }
    } catch (err) {
      alert(`Error starting bot: ${err.message}`);
    }
  };

  // Stop bot execution
  const stopBot = async () => {
    if (!isConnected) return;
    try {
      const cleanUrl = backendUrl.replace(/\/$/, '');
      const response = await fetch(`${cleanUrl}/api/stop`, { 
        method: 'POST',
        headers: getHeaders()
      });
      if (response.ok) {
        fetchStatus();
        fetchLogs();
      }
    } catch (err) {
      alert(`Error stopping bot: ${err.message}`);
    }
  };

  // Handle standard config inputs (text/number/select)
  const handleConfigChange = (key, value) => {
    setConfig(prev => ({
      ...prev,
      [key]: value
    }));
  };

  // Handle boolean toggles in config
  const handleToggleChange = (key) => {
    const currentVal = config[key] || 'false';
    const newVal = currentVal.toLowerCase() === 'true' ? 'false' : 'true';
    setConfig(prev => ({
      ...prev,
      [key]: newVal
    }));
  };

  // Add tag (Helper)
  const addTag = (configKey, tagValue, clearInputFn) => {
    if (!tagValue.trim()) return;
    const currentTags = config[configKey] 
      ? config[configKey].split(',').map(t => t.trim()).filter(Boolean)
      : [];
    if (!currentTags.includes(tagValue.trim())) {
      const updatedTags = [...currentTags, tagValue.trim()].join(',');
      handleConfigChange(configKey, updatedTags);
    }
    clearInputFn('');
  };

  // Remove tag (Helper)
  const removeTag = (configKey, tagToRemove) => {
    const currentTags = config[configKey] 
      ? config[configKey].split(',').map(t => t.trim()).filter(Boolean)
      : [];
    const updatedTags = currentTags.filter(t => t !== tagToRemove).join(',');
    handleConfigChange(configKey, updatedTags);
  };

  // Fetch auth config on mount, then connection check
  useEffect(() => {
    fetchAuthConfig().then((authStatus) => {
      if (!authStatus || !authStatus.auth_enabled || authStatus.authenticated) {
        checkConnection(true).then((connected) => {
          if (connected) {
            fetchStatus();
            fetchConfig();
            fetchResults();
            fetchLogs();
          }
        });
      }
    });

    // Setup polling
    const interval = setInterval(() => {
      const token = localStorage.getItem('naukri_bot_google_token');
      const isAuth = !authConfig.auth_enabled || (token && decodeJwt(token)?.exp * 1000 > Date.now());
      if (isAuth) {
        fetchStatus();
        if (isRunning) {
          fetchLogs();
          fetchResults();
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [backendUrl, isRunning, authConfig.auth_enabled]);

  // Handle initialization of Google Sign-in button
  useEffect(() => {
    if (authConfig.auth_enabled && !isAuthenticated && authConfig.google_client_id) {
      const initGsi = () => {
        if (window.google) {
          window.google.accounts.id.initialize({
            client_id: authConfig.google_client_id,
            callback: handleGoogleLoginSuccess,
          });
          window.google.accounts.id.renderButton(
            document.getElementById('google-signin-btn'),
            { theme: 'filled_black', size: 'large', width: '280' }
          );
        }
      };

      if (window.google) {
        initGsi();
      } else {
        const script = document.querySelector('script[src="https://accounts.google.com/gsi/client"]');
        if (script) {
          script.addEventListener('load', initGsi);
        }
      }
    }
  }, [authConfig, isAuthenticated]);

  // Scroll terminal logs to bottom on update
  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Format seconds to HH:MM:SS
  const formatTime = (totalSeconds) => {
    const hrs = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    return [
      hrs.toString().padStart(2, '0'),
      mins.toString().padStart(2, '0'),
      secs.toString().padStart(2, '0')
    ].join(':');
  };

  // Parse logs line levels for terminal coloring
  const renderColoredLogs = () => {
    if (!logs) return null;
    return logs.split('\n').map((line, i) => {
      let className = 'log-line';
      if (line.includes('INFO')) className = 'log-info';
      else if (line.includes('WARNING') || line.includes('WARN')) className = 'log-warn';
      else if (line.includes('ERROR') || line.includes('FAILED')) className = 'log-error';
      else if (line.includes('Successfully applied') || line.includes('APPLIED')) className = 'log-success';
      
      // Extract timestamp block [2026-07-06...]
      const timeMatch = line.match(/^\[(.*?)\]/);
      if (timeMatch) {
        const timePart = timeMatch[0];
        const contentPart = line.substring(timePart.length);
        return (
          <div key={i} className="terminal-line">
            <span className="log-time">{timePart}</span>
            <span className={className}>{contentPart}</span>
          </div>
        );
      }
      return <div key={i} className={`terminal-line ${className}`}>{line}</div>;
    });
  };

  // Filter job applications results
  const filteredResults = results.filter(item => {
    const jobUrl = item.job_url || '';
    const errorMsg = item.error_message || '';
    const status = item.status || '';
    const searchMatch = jobUrl.toLowerCase().includes(searchTerm.toLowerCase()) || 
                        errorMsg.toLowerCase().includes(searchTerm.toLowerCase());
    const statusMatch = statusFilter === 'ALL' || status.toUpperCase() === statusFilter;
    return searchMatch && statusMatch;
  });

  // Calculate success rates
  const successRate = stats.total > 0 
    ? Math.round(((stats.applied + stats.already_applied) / stats.total) * 100)
    : 0;

  if (authConfig.auth_enabled && !isAuthenticated) {
    return (
      <div className="login-container" style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        backgroundColor: '#0f172a',
        color: '#fff',
        fontFamily: 'system-ui, sans-serif'
      }}>
        <div className="login-card" style={{
          padding: '40px',
          borderRadius: '16px',
          backgroundColor: '#1e293b',
          boxShadow: '0 4px 30px rgba(0, 0, 0, 0.5)',
          border: '1px solid #334155',
          textAlign: 'center',
          maxWidth: '400px',
          width: '100%'
        }}>
          <h1 style={{ fontSize: '32px', marginBottom: '8px', color: '#6366f1' }}>Naukri Ease</h1>
          <p style={{ color: '#94a3b8', marginBottom: '32px' }}>Login with your Google Account to manage settings and control your bots.</p>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <div id="google-signin-btn"></div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="logo-section">
          <div className="logo-icon">
            <Sliders size={20} color="#fff" />
          </div>
          <span className="logo-text">Naukri Ease</span>
        </div>

        <nav>
          <ul className="nav-links">
            <li 
              className={`nav-item ${activeTab === 'home' ? 'active' : ''}`}
              onClick={() => setActiveTab('home')}
            >
              <User size={18} />
              <span>Control Panel</span>
            </li>
            <li 
              className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => {
                setActiveTab('dashboard');
                fetchResults();
                fetchLogs();
              }}
            >
              <Terminal size={18} />
              <span>Real-Time Logs</span>
            </li>
            <li 
              className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
              onClick={() => {
                setActiveTab('settings');
                fetchConfig();
              }}
            >
              <SettingsIcon size={18} />
              <span>Bot Settings</span>
            </li>
          </ul>
        </nav>

        {isAuthenticated && userProfile && (
          <div className="user-profile-panel" style={{
            padding: '12px',
            borderTop: '1px solid #334155',
            borderBottom: '1px solid #334155',
            marginTop: 'auto',
            marginBottom: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            {userProfile.picture && (
              <img 
                src={userProfile.picture} 
                alt="Profile" 
                style={{ width: '32px', height: '32px', borderRadius: '50%' }} 
              />
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {userProfile.name}
              </div>
              <div style={{ fontSize: '10px', color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {userProfile.email}
              </div>
            </div>
            <button 
              onClick={handleLogout}
              style={{
                background: 'none',
                border: 'none',
                color: '#ef4444',
                cursor: 'pointer',
                fontSize: '11px',
                padding: '4px'
              }}
              title="Logout"
            >
              Logout
            </button>
          </div>
        )}

        {/* Connection status footer panel */}
        <div className="connection-status-panel">
          <div className="status-indicator">
            <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
            <span>{isConnected ? 'API Connected' : 'Disconnected'}</span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', wordBreak: 'break-all' }}>
            {backendUrl}
          </div>
          {!isConnected && (
            <button 
              className="btn btn-secondary" 
              style={{ padding: '0.25rem 0.5rem', fontSize: '10px', marginTop: '0.5rem', width: '100%' }}
              onClick={() => checkConnection(true)}
            >
              <RefreshCw size={10} /> Retry Connect
            </button>
          )}
        </div>
      </aside>

      {/* Main Content Pane */}
      <main className="main-content">
        
        {/* Header Section */}
        <header className="top-header">
          <div className="page-title">
            {activeTab === 'home' && (
              <>
                <h1>Bot Controller</h1>
                <p>Monitor status, toggle parameters, and launch the auto-apply agent.</p>
              </>
            )}
            {activeTab === 'dashboard' && (
              <>
                <h1>Application Dashboard</h1>
                <p>Track job metrics, scroll logs, and review processed job descriptions.</p>
              </>
            )}
            {activeTab === 'settings' && (
              <>
                <h1>Configurations Panel</h1>
                <p>Update credentials, search constraints, and candidate background information.</p>
              </>
            )}
          </div>

          <div className="header-controls">
            {/* Quick API Connection indicators */}
            {isConnected ? (
              <span className="badge badge-applied" style={{ textTransform: 'none', gap: '0.25rem' }}>
                <Wifi size={12} /> Live Bridge Active
              </span>
            ) : (
              <span className="badge badge-failed" style={{ textTransform: 'none', gap: '0.25rem' }}>
                <WifiOff size={12} /> Local API Offline
              </span>
            )}

            {/* Run bot controllers */}
            {isRunning ? (
              <button className="btn btn-danger animate-pulse" onClick={stopBot}>
                <Square size={16} fill="white" /> Stop Auto Apply
              </button>
            ) : (
              <button 
                className="btn btn-primary" 
                onClick={startBot} 
                disabled={!isConnected || stats.quota_hit}
              >
                <Play size={16} fill="white" /> Start Auto Apply
              </button>
            )}
          </div>
        </header>

        {/* Global Connection Error Notice */}
        {connectionError && (
          <div className="alert-banner">
            <WifiOff size={20} />
            <div>
              <strong>Connection Warning:</strong> {connectionError}
              <div style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>
                If you are running the bot from your phone, enter your PC's Ngrok tunnel URL in the <strong>Connection Settings</strong> section at the bottom of the Settings tab.
              </div>
            </div>
          </div>
        )}

        {/* Top Metric Cards (visible in Home and Dashboard) */}
        {activeTab !== 'settings' && (
          <section className="stats-grid">
            <div className="stat-card">
              <div className="stat-icon primary">
                <Briefcase size={22} />
              </div>
              <div className="stat-details">
                <h3>Total Scanned</h3>
                <p>{stats.total}</p>
              </div>
            </div>
            
            <div className="stat-card">
              <div className="stat-icon success">
                <CheckCircle size={22} />
              </div>
              <div className="stat-details">
                <h3>Applied</h3>
                <p>{stats.applied}</p>
              </div>
            </div>

            <div className="stat-card">
              <div className="stat-icon info">
                <FileSpreadsheet size={22} />
              </div>
              <div className="stat-details">
                <h3>Already Applied</h3>
                <p>{stats.already_applied}</p>
              </div>
            </div>

            <div className="stat-card">
              <div className="stat-icon warning">
                <ExternalLink size={22} />
              </div>
              <div className="stat-details">
                <h3>Redirects</h3>
                <p>{stats.external_redirect}</p>
              </div>
            </div>

            <div className="stat-card">
              <div className="stat-icon info">
                <ActivityIcon />
              </div>
              <div className="stat-details">
                <h3>Success Rate</h3>
                <p>{successRate}%</p>
              </div>
            </div>
          </section>
        )}

        {/* ======================================================== */}
        {/* TAB 1: HOME CONTROLLER VIEW */}
        {/* ======================================================== */}
        {activeTab === 'home' && (
          <div className="tab-content hero-view">
            <div className="hero-badge">NAUKRI AUTOMATION PORTAL</div>
            <h1>Automate Your Job Hunt</h1>
            <p>
              Connect to your local workstation, tweak profile answers, and auto-submit hundreds of applications directly to Naukri recruiters.
            </p>

            <div className="hero-actions">
              {isRunning ? (
                <button className="btn btn-danger btn-primary" style={{ padding: '0.85rem 2rem', fontSize: '1rem' }} onClick={stopBot}>
                  <Square size={18} fill="white" /> Stop Auto Apply
                </button>
              ) : (
                <button 
                  className="btn btn-primary" 
                  style={{ padding: '0.85rem 2rem', fontSize: '1rem' }} 
                  onClick={startBot} 
                  disabled={!isConnected || stats.quota_hit}
                >
                  <Play size={18} fill="white" /> Run Auto Apply
                </button>
              )}
              <button 
                className="btn btn-secondary" 
                style={{ padding: '0.85rem 2rem', fontSize: '1rem' }}
                onClick={() => setActiveTab('dashboard')}
              >
                <Terminal size={18} /> View Console Logs
              </button>
            </div>

            <div className="quick-specs-grid">
              <div className="spec-feature-card">
                <h3><CheckCircle size={16} color="var(--color-primary)" /> Automated Applications</h3>
                <p>Intelligently navigates search result pages, checks existing application history, and completes application sequences.</p>
              </div>
              <div className="spec-feature-card">
                <h3><Sliders size={16} color="var(--color-primary)" /> Conversational AI Solver</h3>
                <p>Uses Codex/GPT models to solve recruiter conversational chatbot questionnaires in real-time, matching details to your profile.</p>
              </div>
              <div className="spec-feature-card">
                <h3><Terminal size={16} color="var(--color-primary)" /> Mobile Dashboard Controls</h3>
                <p>Run tunnels on your computer to check execution, see Chrome logs, change targets, and monitor applications from your mobile device.</p>
              </div>
              <div className="spec-feature-card">
                <h3><FileText size={16} color="var(--color-primary)" /> Offline Fallback Solver</h3>
                <p>Equipped with rule-based heuristics that take over to solve questionnaire inputs safely when OpenAI tokens or connections fail.</p>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* TAB 2: REAL-TIME LOGS & RESULTS TABLE */}
        {/* ======================================================== */}
        {activeTab === 'dashboard' && (
          <div className="tab-content">
            <div className="dashboard-grid">
              
              {/* Left Panel: Monospace terminal */}
              <div className="panel">
                <div className="panel-header">
                  <h2><Terminal size={18} color="var(--color-primary)" /> Execution Terminal Console</h2>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    {isRunning && <span className="badge badge-applied animate-pulse">Active: PID {pid}</span>}
                    {isRunning && <span style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>Elapsed: {formatTime(elapsedSeconds)}</span>}
                    <button className="btn btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }} onClick={fetchLogs}>
                      <RefreshCw size={12} /> Refresh
                    </button>
                  </div>
                </div>
                <div className="terminal-container">
                  {renderColoredLogs()}
                  <div ref={terminalEndRef} />
                </div>
              </div>

              {/* Right Panel: Short Stats Summary */}
              <div className="panel" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <div className="panel-header">
                    <h2>Configuration Run Metrics</h2>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                      <span style={{ color: 'var(--color-text-secondary)' }}>Keywords Configured:</span>
                      <strong style={{ fontSize: '0.9rem', maxWidth: '180px', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                        {config.KEYWORDS || 'None'}
                      </strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                      <span style={{ color: 'var(--color-text-secondary)' }}>Preferred Locations:</span>
                      <strong>{config.LOCATION || 'Any'}</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                      <span style={{ color: 'var(--color-text-secondary)' }}>Max Scans Per Run:</span>
                      <strong>{config.MAX_APPLICATIONS || '10'}</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                      <span style={{ color: 'var(--color-text-secondary)' }}>Browser Window Mode:</span>
                      <strong>{config.HEADLESS === 'true' ? 'Headless (Hidden)' : 'Visible (Chrome)'}</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                      <span style={{ color: 'var(--color-text-secondary)' }}>Daily Quota Hit:</span>
                      <span className={stats.quota_hit ? 'log-error' : 'log-success'} style={{ fontWeight: 'bold' }}>
                        {stats.quota_hit ? 'YES (Limit Reached)' : 'NO'}
                      </span>
                    </div>
                  </div>
                </div>

                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)', marginTop: '2rem' }}>
                  <h4 style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginBottom: '0.5rem' }}>Quick Tip:</h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', lineHeight: '1.4' }}>
                    If the bot stops early, check the terminal logs. Quotas are governed by Naukri limits (usually 50-100 applications a day). Relogin might be required if session cookies expire.
                  </p>
                </div>
              </div>

            </div>

            {/* Bottom Row: Detailed Results table with searching and filtering */}
            <div className="panel">
              <div className="panel-header" style={{ marginBottom: '1.5rem' }}>
                <h2>Applied Job Tracking Log ({filteredResults.length} items)</h2>
                <button className="btn btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }} onClick={fetchResults}>
                  <RefreshCw size={12} /> Refresh History
                </button>
              </div>

              {/* Filtering Controls */}
              <div className="search-bar-container">
                <div className="search-input-wrapper">
                  <Search size={16} className="search-input-icon" />
                  <input 
                    type="text" 
                    placeholder="Search by Job URL, company name, or error logs..." 
                    className="form-input"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                  />
                </div>

                <div className="form-group" style={{ minWidth: '160px' }}>
                  <select 
                    className="form-input" 
                    value={statusFilter} 
                    onChange={(e) => setStatusFilter(e.target.value)}
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="APPLIED">Applied</option>
                    <option value="ALREADY_APPLIED">Already Applied</option>
                    <option value="EXTERNAL_REDIRECT">External Redirect</option>
                    <option value="FAILED">Failed</option>
                    <option value="SKIPPED">Skipped</option>
                  </select>
                </div>
              </div>

              {/* Table rendering */}
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Job Opportunity URL</th>
                      <th>Application Status</th>
                      <th>Time Registered</th>
                      <th>Redirect Info / Errors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredResults.length > 0 ? (
                      filteredResults.map((item, idx) => {
                        // Shorten job link
                        let shortUrl = item.job_url || 'Unknown URL';
                        if (shortUrl.startsWith('https://www.naukri.com/job-listings-')) {
                          shortUrl = shortUrl.replace('https://www.naukri.com/job-listings-', '').substring(0, 45) + '...';
                        }
                        
                        return (
                          <tr key={idx}>
                            <td>
                              <a href={item.job_url} target="_blank" rel="noopener noreferrer" className="log-info" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', textDecoration: 'none' }}>
                                {shortUrl} <ExternalLink size={12} />
                              </a>
                            </td>
                            <td>
                              <span className={`badge badge-${(item.status || 'failed').toLowerCase().replace('_', '')}`}>
                                {item.status || 'FAILED'}
                              </span>
                            </td>
                            <td style={{ color: 'var(--color-text-secondary)' }}>
                              {item.timestamp ? new Date(item.timestamp).toLocaleString() : 'N/A'}
                            </td>
                            <td>
                              {item.status === 'EXTERNAL_REDIRECT' && item.external_link && (
                                <a href={item.external_link} target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', color: 'var(--color-warning)' }}>
                                  Go to Company Site <ExternalLink size={12} />
                                </a>
                              )}
                              {item.status === 'FAILED' && (
                                <span className="log-error" style={{ fontSize: '0.85rem' }}>{item.error_message || 'Unknown Failure'}</span>
                              )}
                              {item.status !== 'EXTERNAL_REDIRECT' && item.status !== 'FAILED' && (
                                <span style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>—</span>
                              )}
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan="4" style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-secondary)' }}>
                          No job applications found matching filters.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* TAB 3: CONFIGURATION SETTINGS PANEL */}
        {/* ======================================================== */}
        {activeTab === 'settings' && (
          <div className="tab-content">
            
            {configSaveSuccess && (
              <div className="alert-banner success">
                <CheckCircle size={20} />
                <strong>Success:</strong> Configuration updated and saved to local .env successfully!
              </div>
            )}

            <form onSubmit={saveConfig}>
              <div className="settings-container">
                
                {/* Column Left: Credentials, Keywords & Driver */}
                <div className="settings-section">
                  
                  {/* Part 1: Login Credentials */}
                  <div className="panel">
                    <div className="settings-group-title">Naukri Login credentials</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '1rem' }}>
                      <div className="form-group">
                        <label>Naukri Registered Email Address</label>
                        <input 
                          type="email" 
                          required
                          className="form-input" 
                          value={config.NAUKRI_EMAIL || ''} 
                          onChange={(e) => handleConfigChange('NAUKRI_EMAIL', e.target.value)}
                        />
                      </div>
                      
                      <div className="form-group">
                        <label>Account Password</label>
                        <input 
                          type="password" 
                          required
                          className="form-input" 
                          value={config.NAUKRI_PASSWORD || ''} 
                          onChange={(e) => handleConfigChange('NAUKRI_PASSWORD', e.target.value)}
                        />
                      </div>

                      <div className="form-row">
                        <div className="form-group">
                          <label>Applicant First Name</label>
                          <input 
                            type="text" 
                            className="form-input" 
                            value={config.FIRST_NAME || ''} 
                            onChange={(e) => handleConfigChange('FIRST_NAME', e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Applicant Last Name</label>
                          <input 
                            type="text" 
                            className="form-input" 
                            value={config.LAST_NAME || ''} 
                            onChange={(e) => handleConfigChange('LAST_NAME', e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Part 2: Search Parameters */}
                  <div className="panel">
                    <div className="settings-group-title">Job Search Settings</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '1rem' }}>
                      
                      {/* Keywords Tags Input */}
                      <div className="form-group">
                        <label>Search Keywords (e.g. Gen AI Developer, Frontend Developer)</label>
                        <div className="tags-input-container">
                          {(config.KEYWORDS || '').split(',').map(t => t.trim()).filter(Boolean).map((kw, i) => (
                            <span key={i} className="tag-badge">
                              {kw}
                              <X size={12} className="tag-remove" onClick={() => removeTag('KEYWORDS', kw)} />
                            </span>
                          ))}
                          <input 
                            type="text" 
                            placeholder="Type keyword and press Enter..." 
                            className="tag-field-input"
                            value={newKeyword}
                            onChange={(e) => setNewKeyword(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                addTag('KEYWORDS', newKeyword, setNewKeyword);
                              }
                            }}
                          />
                        </div>
                      </div>

                      <div className="form-group">
                        <label>Preferred Locations (e.g. Bangalore, Remote)</label>
                        <input 
                          type="text" 
                          placeholder="Bangalore, Noida, Pune"
                          className="form-input" 
                          value={config.LOCATION || ''} 
                          onChange={(e) => handleConfigChange('LOCATION', e.target.value)}
                        />
                      </div>

                      <div className="form-row">
                        <div className="form-group">
                          <label>Pages per Keyword (to scan)</label>
                          <input 
                            type="number" 
                            min="1"
                            max="10"
                            className="form-input" 
                            value={config.PAGES_PER_KEYWORD || '1'} 
                            onChange={(e) => handleConfigChange('PAGES_PER_KEYWORD', e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Max Applications (cap per run)</label>
                          <input 
                            type="number" 
                            min="1"
                            max="200"
                            className="form-input" 
                            value={config.MAX_APPLICATIONS || '10'} 
                            onChange={(e) => handleConfigChange('MAX_APPLICATIONS', e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Part 3: Browser and Delays */}
                  <div className="panel">
                    <div className="settings-group-title">Automation & Driver Configurations</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '1rem' }}>
                      
                      <div className="switch-container">
                        <div className="switch-label">
                          <span>Run Headless Mode</span>
                          <span>Launch Chrome window invisibly in background</span>
                        </div>
                        <label className="switch">
                          <input 
                            type="checkbox" 
                            checked={(config.HEADLESS || 'false').toLowerCase() === 'true'} 
                            onChange={() => handleToggleChange('HEADLESS')}
                          />
                          <span className="slider"></span>
                        </label>
                      </div>

                      <div className="form-group">
                        <label>Explicit Wait Timeout (seconds)</label>
                        <input 
                          type="number" 
                          className="form-input" 
                          value={config.WAIT_TIMEOUT || '15'} 
                          onChange={(e) => handleConfigChange('WAIT_TIMEOUT', e.target.value)}
                        />
                      </div>

                      <div className="form-row">
                        <div className="form-group">
                          <label>Min Delay between steps (s)</label>
                          <input 
                            type="number" 
                            step="0.5"
                            className="form-input" 
                            value={config.MIN_DELAY || '2'} 
                            onChange={(e) => handleConfigChange('MIN_DELAY', e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Max Delay between steps (s)</label>
                          <input 
                            type="number" 
                            step="0.5"
                            className="form-input" 
                            value={config.MAX_DELAY || '5'} 
                            onChange={(e) => handleConfigChange('MAX_DELAY', e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                </div>

                {/* Column Right: AI settings and details */}
                <div className="settings-section">
                  
                  {/* Part 4: AI & Codex Settings */}
                  <div className="panel">
                    <div className="settings-group-title">AI Answering (Codex / OpenAI)</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '1rem' }}>
                      
                      <div className="form-group">
                        <label>OpenAI Codex API Secret Key</label>
                        <input 
                          type="password" 
                          placeholder="sk-proj-..."
                          className="form-input" 
                          value={config.CODEX_API_KEY || ''} 
                          onChange={(e) => handleConfigChange('CODEX_API_KEY', e.target.value)}
                        />
                      </div>

                      <div className="form-group">
                        <label>OpenAI Chat Base URL Endpoint</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          value={config.CODEX_API_BASE_URL || ''} 
                          onChange={(e) => handleConfigChange('CODEX_API_BASE_URL', e.target.value)}
                        />
                      </div>

                      <div className="form-group">
                        <label>GPT Completions Model</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          value={config.CODEX_MODEL || 'gpt-4o-mini'} 
                          onChange={(e) => handleConfigChange('CODEX_MODEL', e.target.value)}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Part 5: Detailed Answering Candidate Profile */}
                  <div className="panel">
                    <div className="settings-group-title">AI Questionnaire Profile Context</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '1rem' }}>
                      
                      <div className="form-row">
                        <div className="form-group">
                          <label>Total Experience (Years)</label>
                          <input 
                            type="text" 
                            className="form-input" 
                            value={config.YEARS_OF_EXPERIENCE || '3'} 
                            onChange={(e) => handleConfigChange('YEARS_OF_EXPERIENCE', e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Candidate Gender</label>
                          <select 
                            className="form-input" 
                            value={config.GENDER || 'Male'} 
                            onChange={(e) => handleConfigChange('GENDER', e.target.value)}
                          >
                            <option value="Male">Male</option>
                            <option value="Female">Female</option>
                            <option value="Other">Other</option>
                          </select>
                        </div>
                      </div>

                      <div className="form-row">
                        <div className="form-group">
                          <label>Current CTC (e.g. 8 LPA)</label>
                          <input 
                            type="text" 
                            className="form-input" 
                            value={config.CURRENT_CTC || ''} 
                            onChange={(e) => handleConfigChange('CURRENT_CTC', e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Expected CTC (e.g. 12 LPA)</label>
                          <input 
                            type="text" 
                            className="form-input" 
                            value={config.EXPECTED_CTC || ''} 
                            onChange={(e) => handleConfigChange('EXPECTED_CTC', e.target.value)}
                          />
                        </div>
                      </div>

                      <div className="form-row">
                        <div className="form-group">
                          <label>Notice Period (e.g. 30 days)</label>
                          <input 
                            type="text" 
                            className="form-input" 
                            value={config.NOTICE_PERIOD || ''} 
                            onChange={(e) => handleConfigChange('NOTICE_PERIOD', e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Graduation Passing Year</label>
                          <input 
                            type="text" 
                            className="form-input" 
                            value={config.GRADUATION_YEAR || '2024'} 
                            onChange={(e) => handleConfigChange('GRADUATION_YEAR', e.target.value)}
                          />
                        </div>
                      </div>

                      <div className="form-row">
                        <div className="form-group">
                          <label>Highest Degree/Qualification</label>
                          <input 
                            type="text" 
                            placeholder="B.Tech"
                            className="form-input" 
                            value={config.HIGHEST_QUALIFICATION || 'B.Tech'} 
                            onChange={(e) => handleConfigChange('HIGHEST_QUALIFICATION', e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Current Employer Company</label>
                          <input 
                            type="text" 
                            placeholder="Self Employed"
                            className="form-input" 
                            value={config.CURRENT_COMPANY || ''} 
                            onChange={(e) => handleConfigChange('CURRENT_COMPANY', e.target.value)}
                          />
                        </div>
                      </div>

                      <div className="form-row">
                        <div className="switch-container" style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
                          <div className="switch-label">
                            <span>Work Authorization</span>
                            <span>Eligible to work in India</span>
                          </div>
                          <label className="switch">
                            <input 
                              type="checkbox" 
                              checked={(config.WORK_AUTHORIZATION || 'Yes').toLowerCase() === 'yes' || (config.WORK_AUTHORIZATION || 'Yes').toLowerCase() === 'true'} 
                              onChange={() => handleConfigChange('WORK_AUTHORIZATION', (config.WORK_AUTHORIZATION || 'Yes').toLowerCase() === 'yes' ? 'No' : 'Yes')}
                            />
                            <span className="slider"></span>
                          </label>
                        </div>
                        <div className="switch-container" style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
                          <div className="switch-label">
                            <span>Shift Flexibility</span>
                            <span>Willing to work rotational shifts</span>
                          </div>
                          <label className="switch">
                            <input 
                              type="checkbox" 
                              checked={(config.SHIFT_FLEXIBILITY || 'Yes').toLowerCase() === 'yes' || (config.SHIFT_FLEXIBILITY || 'Yes').toLowerCase() === 'true'} 
                              onChange={() => handleConfigChange('SHIFT_FLEXIBILITY', (config.SHIFT_FLEXIBILITY || 'Yes').toLowerCase() === 'yes' ? 'No' : 'Yes')}
                            />
                            <span className="slider"></span>
                          </label>
                        </div>
                      </div>

                      <div className="form-group">
                        <label>Current Location City</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          value={config.CURRENT_LOCATION || ''} 
                          onChange={(e) => handleConfigChange('CURRENT_LOCATION', e.target.value)}
                        />
                      </div>

                      <div className="form-group">
                        <label>Preferred Locations (split by comma)</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          value={config.PREFERRED_LOCATIONS || ''} 
                          onChange={(e) => handleConfigChange('PREFERRED_LOCATIONS', e.target.value)}
                        />
                      </div>

                      <div className="form-group">
                        <label>Profile Keywords & Skills (tags)</label>
                        <div className="tags-input-container">
                          {(config.SKILLS || '').split(',').map(t => t.trim()).filter(Boolean).map((sk, i) => (
                            <span key={i} className="tag-badge">
                              {sk}
                              <X size={12} className="tag-remove" onClick={() => removeTag('SKILLS', sk)} />
                            </span>
                          ))}
                          <input 
                            type="text" 
                            placeholder="Type skill and press Enter..." 
                            className="tag-field-input"
                            value={newSkill}
                            onChange={(e) => setNewSkill(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                addTag('SKILLS', newSkill, setNewSkill);
                              }
                            }}
                          />
                        </div>
                      </div>

                    </div>
                  </div>

                  {/* Part 6: Google Sheets Integration */}
                  <div className="panel">
                    <div className="settings-group-title">Google Sheets Integration</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '1rem' }}>
                      
                      <div className="switch-container">
                        <div className="switch-label">
                          <span>Enable Spreadsheet Sync</span>
                          <span>Auto export results to Google Sheets</span>
                        </div>
                        <label className="switch">
                          <input 
                            type="checkbox" 
                            checked={(config.GOOGLE_SHEETS_ENABLED || 'false').toLowerCase() === 'true'} 
                            onChange={() => handleToggleChange('GOOGLE_SHEETS_ENABLED')}
                          />
                          <span className="slider"></span>
                        </label>
                      </div>

                      <div className="form-group">
                        <label>Google Spreadsheet ID</label>
                        <input 
                          type="text" 
                          placeholder="e.g. 1aBCdeF..."
                          className="form-input" 
                          value={config.GOOGLE_SHEETS_SPREADSHEET_ID || ''} 
                          onChange={(e) => handleConfigChange('GOOGLE_SHEETS_SPREADSHEET_ID', e.target.value)}
                        />
                      </div>

                      <div className="form-row">
                        <div className="form-group">
                          <label>Credentials Key Path</label>
                          <input 
                            type="text" 
                            className="form-input" 
                            value={config.GOOGLE_SHEETS_CREDENTIALS_PATH || 'service_account.json'} 
                            onChange={(e) => handleConfigChange('GOOGLE_SHEETS_CREDENTIALS_PATH', e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Worksheet Tab Name</label>
                          <input 
                            type="text" 
                            className="form-input" 
                            value={config.GOOGLE_SHEETS_WORKSHEET_NAME || 'Results'} 
                            onChange={(e) => handleConfigChange('GOOGLE_SHEETS_WORKSHEET_NAME', e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Part 7: Remote Connection Parameters */}
                  <div className="panel" style={{ border: '1px solid rgba(99,102,241,0.4)', background: 'linear-gradient(to right, rgba(99,102,241,0.02), rgba(99,102,241,0.06))' }}>
                    <div className="settings-group-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#818cf8' }}>
                      <Database size={18} /> Connection settings (Mobile / Remote Controls)
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '1rem' }}>
                      <div className="form-group">
                        <label style={{ color: '#a5b4fc' }}>Backend API URL Link</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          style={{ borderColor: 'rgba(99,102,241,0.3)', background: 'rgba(5,5,8,0.5)' }}
                          value={backendUrl} 
                          onChange={handleBackendUrlChange}
                        />
                        <p style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)', lineHeight: '1.4', marginTop: '0.25rem' }}>
                          Default: <code>http://127.0.0.1:8000</code>. When controlling from your phone outside the local network, start an Ngrok tunnel (<code>ngrok http 8000</code>) on your PC and enter the generated URL here.
                        </p>
                      </div>
                    </div>
                  </div>

                </div>

              </div>

              {/* Sticky bottom save bar */}
              <div className="panel" style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '2rem' }}>
                <button 
                  type="button" 
                  className="btn btn-secondary" 
                  onClick={fetchConfig}
                  disabled={!isConnected}
                >
                  Discard Changes
                </button>
                <button 
                  type="submit" 
                  className="btn btn-primary"
                  disabled={!isConnected || isSavingConfig}
                >
                  {isSavingConfig ? 'Saving Settings...' : 'Save Configuration'}
                </button>
              </div>
            </form>

          </div>
        )}

      </main>
    </div>
  );
}

// Minimal Activity icon
function ActivityIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
    </svg>
  );
}
