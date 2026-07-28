import React, { useState, useEffect, useRef } from 'react';
import { 
  DownloadCloud, KeyRound, ExternalLink, ChevronUp, ChevronDown, 
  RefreshCw, LogIn, Sliders, Download, ListVideo, Terminal, Lock, 
  Circle, ArrowUpDown, CheckSquare, Square, LogOut, CheckCircle2
} from 'lucide-react';

interface Lesson {
  order: number;
  name: string;
  id: string;
  downloaded: boolean;
  has_video: boolean;
  has_pdf: boolean;
  has_attached: boolean;
}

interface Module {
  order: number;
  name: string;
  lessons: Lesson[];
}

interface SubdomainItem {
  subdomain: string;
  source: string;
  name: string;
}

export default function App() {
  // State variables
  const [token, setToken] = useState('');
  const [subdomain, setSubdomain] = useState('');
  const [manualSubdomain, setManualSubdomain] = useState('');
  const [downloadDir, setDownloadDir] = useState('');
  const [subdomains, setSubdomains] = useState<SubdomainItem[]>([]);
  const [tokenPresent, setTokenPresent] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loginError, setLoginError] = useState('');
  
  const [modules, setModules] = useState<Module[]>([]);
  const [selectedLessonIds, setSelectedLessonIds] = useState<Set<string>>(new Set());
  const [activeDownloads, setActiveDownloads] = useState<Record<string, { percentage: number; status: string }>>({});
  const [logs, setLogs] = useState('Loading logs...');
  
  const [activeTab, setActiveTab] = useState<'modules' | 'logs'>('modules');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  
  // UI States
  const [isCredsCollapsed, setIsCredsCollapsed] = useState(false);
  const [isCredsFloating, setIsCredsFloating] = useState(false);
  const [expandedModules, setExpandedModules] = useState<Record<number, boolean>>({});

  const wsRef = useRef<WebSocket | null>(null);

  // Backend host (change to localhost:8000 when running dev servers)
  const apiHost = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';
  const wsHost = window.location.hostname === 'localhost' ? 'ws://localhost:8000' : '';

  // Get initial status
  useEffect(() => {
    fetch(`${apiHost}/`)
      .then(res => res.json())
      .then(data => {
        if (data.env_download_dir) setDownloadDir(data.env_download_dir);
        if (data.env_token_present) setTokenPresent(true);
      })
      .catch(err => console.error("Error checking root status:", err));

    loadSubdomains();
  }, []);

  // Set up WebSocket connection for progress updates
  useEffect(() => {
    function connectWS() {
      const socket = new WebSocket(`${wsHost || (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host}/ws/progress`);
      wsRef.current = socket;

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        setActiveDownloads(prev => ({
          ...prev,
          [data.lesson_id]: {
            percentage: data.percentage,
            status: data.status
          }
        }));
        
        // If completed, update modules downloaded state
        if (data.status === 'Completed') {
          setModules(prevMods => 
            prevMods.map(mod => ({
              ...mod,
              lessons: mod.lessons.map(les => 
                les.id === data.lesson_id ? { ...les, downloaded: true } : les
              )
            }))
          );
        }
      };

      socket.onclose = () => {
        setTimeout(connectWS, 3000);
      };
    }

    connectWS();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // Polling active download status on mount or when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      fetch(`${apiHost}/api/downloads/status`)
        .then(res => res.json())
        .then(data => {
          setActiveDownloads(data);
        })
        .catch(err => console.error("Error fetching downloads status:", err));
    }
  }, [isAuthenticated]);

  const loadSubdomains = async () => {
    try {
      const res = await fetch(`${apiHost}/api/subdomains`);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      setSubdomains(data.subdomains || []);
      setTokenPresent(data.token_present || false);
    } catch (err: any) {
      console.error("Error loading subdomains:", err);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setLoginError('');

    const targetSubdomain = subdomain || manualSubdomain;
    if (!token) {
      setLoginError('Please enter the Bearer token.');
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${apiHost}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token,
          subdomain: targetSubdomain,
          download_dir: downloadDir
        })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Unknown auth error.');

      setModules(data.modules || []);
      setIsAuthenticated(true);
      
      // Auto expand first module
      if (data.modules && data.modules.length > 0) {
        setExpandedModules({ [data.modules[0].order]: true });
      }
    } catch (err: any) {
      setLoginError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setModules([]);
    setSelectedLessonIds(new Set());
  };

  const fetchLogs = async () => {
    try {
      const res = await fetch(`${apiHost}/api/logs`);
      const data = await res.json();
      setLogs(data.logs || 'No logs.');
    } catch (err: any) {
      setLogs(`Error: ${err.message}`);
    }
  };

  useEffect(() => {
    if (activeTab === 'logs') {
      fetchLogs();
      const interval = setInterval(fetchLogs, 4000);
      return () => clearInterval(interval);
    }
  }, [activeTab]);

  const toggleModule = (modOrder: number) => {
    setExpandedModules(prev => ({
      ...prev,
      [modOrder]: !prev[modOrder]
    }));
  };

  // Selection handlers
  const handleSelectLesson = (lessonId: string) => {
    const next = new Set(selectedLessonIds);
    if (next.has(lessonId)) {
      next.delete(lessonId);
    } else {
      next.add(lessonId);
    }
    setSelectedLessonIds(next);
  };

  const selectAll = () => {
    const allIds = new Set<string>();
    modules.forEach(mod => {
      mod.lessons.forEach(l => allIds.add(l.id));
    });
    setSelectedLessonIds(allIds);
  };

  const deselectAll = () => {
    setSelectedLessonIds(new Set());
  };

  const selectMissing = () => {
    const missingIds = new Set<string>();
    modules.forEach(mod => {
      mod.lessons.forEach(l => {
        if (!l.downloaded) missingIds.add(l.id);
      });
    });
    setSelectedLessonIds(missingIds);
  };

  const selectAllInModule = (mod: Module, e: React.MouseEvent) => {
    e.stopPropagation();
    const next = new Set(selectedLessonIds);
    mod.lessons.forEach(l => next.add(l.id));
    setSelectedLessonIds(next);
  };

  const deselectAllInModule = (mod: Module, e: React.MouseEvent) => {
    e.stopPropagation();
    const next = new Set(selectedLessonIds);
    mod.lessons.forEach(l => next.delete(l.id));
    setSelectedLessonIds(next);
  };

  const triggerDownload = async (lessonIds: string[]) => {
    if (lessonIds.length === 0) return;
    
    // Add temporary status to local UI state
    setActiveDownloads(prev => {
      const next = { ...prev };
      lessonIds.forEach(id => {
        next[id] = { percentage: 0, status: 'Queued' };
      });
      return next;
    });

    try {
      const res = await fetch(`${apiHost}/api/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lesson_ids: lessonIds })
      });
      if (!res.ok) throw new Error('Failed to start download');
    } catch (err: any) {
      alert(err.message);
    }
  };

  const downloadSelected = () => {
    triggerDownload(Array.from(selectedLessonIds));
  };

  const downloadMissing = () => {
    const missingIds: string[] = [];
    modules.forEach(mod => {
      mod.lessons.forEach(l => {
        if (!l.downloaded) missingIds.push(l.id);
      });
    });
    triggerDownload(missingIds);
  };

  // Sorting
  const sortedModules = [...modules].sort((a, b) => {
    return sortOrder === 'asc' ? a.order - b.order : b.order - a.order;
  });

  return (
    <div className="bg-slate-950 text-slate-100 min-h-screen flex flex-col font-sans selection:bg-brand-500/30 selection:text-white">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-brand-500/10 rounded-lg border border-brand-500/30 text-brand-500">
              <DownloadCloud className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-white">Hotmart Downloader</h1>
              <p className="text-xs text-slate-400">Phase 2: Decoupled Web App</p>
            </div>
          </div>
          {isAuthenticated && (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-slate-800 border border-slate-700 text-xs text-slate-300">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                Authenticated
              </div>
              <button 
                onClick={handleLogout}
                className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-red-400 transition" 
                title="Disconnect"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-8 flex flex-col lg:flex-row gap-8 relative">
        
        {/* Left Column: Settings / Credentials */}
        <div 
          className={`w-full lg:w-1/3 space-y-6 ${
            isCredsFloating 
              ? 'lg:fixed lg:bottom-6 lg:left-6 lg:z-40 lg:max-w-xs' 
              : ''
          }`}
        >
          <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-2xl transition-all duration-300 flex flex-col">
            {/* Panel Header */}
            <div className="flex items-center justify-between p-5 pb-3 border-b border-slate-800 select-none cursor-default">
              <div className="flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-brand-500" />
                <h2 className="font-semibold text-base text-white">Credentials</h2>
              </div>
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => setIsCredsFloating(!isCredsFloating)} 
                  className={`p-1.5 rounded transition ${isCredsFloating ? 'text-brand-500 bg-brand-500/10' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}
                  title="Toggle Floating Mode"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
                <button 
                  onClick={() => setIsCredsCollapsed(!isCredsCollapsed)}
                  className="text-slate-400 hover:text-white p-1.5 hover:bg-slate-800 rounded transition"
                  title="Collapse Panel"
                >
                  <ChevronUp className={`w-3.5 h-3.5 transform transition-transform duration-200 ${isCredsCollapsed ? 'rotate-180' : ''}`} />
                </button>
              </div>
            </div>

            {/* Panel Body */}
            <div className={`p-5 pt-4 space-y-4 ${isCredsCollapsed ? 'hidden' : ''}`}>
              {!isAuthenticated ? (
                <form onSubmit={handleLogin} className="space-y-4">
                  {/* Subdomain Detection / Selection */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">Subdomain</label>
                      <button 
                        type="button"
                        onClick={loadSubdomains}
                        className="text-[10px] text-slate-500 hover:text-brand-500 transition flex items-center gap-1"
                      >
                        <RefreshCw className="w-3 h-3" /> Refresh
                      </button>
                    </div>
                    
                    <div className="flex flex-wrap gap-1.5 min-h-[32px] items-center">
                      {subdomains.length === 0 ? (
                        <span className="text-xs text-slate-500 italic">No subdomains detected. Enter manually.</span>
                      ) : (
                        subdomains.map(item => (
                          <button
                            key={item.subdomain}
                            type="button"
                            onClick={() => {
                              setSubdomain(item.subdomain);
                              setManualSubdomain('');
                            }}
                            className={`flex items-center gap-1 px-2.5 py-1 rounded-full border text-xs transition cursor-pointer ${
                              subdomain === item.subdomain
                                ? 'border-brand-500 text-brand-400 bg-brand-500/10'
                                : 'border-slate-800 text-slate-400 bg-slate-950 hover:border-slate-700'
                            }`}
                          >
                            <Circle className={`w-1.5 h-1.5 fill-current ${subdomain === item.subdomain ? 'text-brand-500' : 'text-slate-600'}`} />
                            {item.name}
                            <span className="text-[8px] opacity-60 ml-0.5 uppercase">
                              {item.source === 'config' ? 'cfg' : 'auto'}
                            </span>
                          </button>
                        ))
                      )}
                    </div>

                    <input 
                      type="text" 
                      placeholder="Or enter subdomain manually..." 
                      value={manualSubdomain}
                      onChange={(e) => {
                        setManualSubdomain(e.target.value);
                        setSubdomain('');
                      }}
                      className="w-full bg-slate-950 border border-slate-800 focus:border-brand-500 focus:ring-1 focus:ring-brand-500 rounded-lg px-3 py-2 text-sm text-slate-200 outline-none transition" 
                    />
                  </div>

                  {/* Token Field */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">Bearer / SSO Token</label>
                      {tokenPresent && (
                        <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20 font-semibold animate-pulse">Pre-loaded from .env</span>
                      )}
                    </div>
                    <textarea 
                      rows={3} 
                      placeholder="Paste token or config block..." 
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 focus:border-brand-500 focus:ring-1 focus:ring-brand-500 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none transition font-mono"
                    />
                  </div>

                  {/* Download Dir Field */}
                  <div className="space-y-1">
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">Download Folder (Optional)</label>
                    <input 
                      type="text" 
                      placeholder="e.g. /mnt/c/downloads" 
                      value={downloadDir}
                      onChange={(e) => setDownloadDir(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 focus:border-brand-500 focus:ring-1 focus:ring-brand-500 rounded-lg px-3 py-2 text-sm text-slate-200 outline-none transition" 
                    />
                  </div>

                  <button 
                    type="submit"
                    disabled={loading}
                    className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 active:bg-brand-700 rounded-lg text-sm font-semibold transition text-white shadow-lg shadow-brand-500/20 flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {loading ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <LogIn className="w-4 h-4" />
                    )}
                    Connect & Load Course
                  </button>

                  {loginError && (
                    <div className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 p-3 rounded-lg leading-relaxed whitespace-pre-wrap">
                      {loginError}
                    </div>
                  )}
                </form>
              ) : (
                <div className="space-y-3">
                  <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1 text-xs">
                    <p className="text-slate-400">Connected to subdomain:</p>
                    <p className="font-semibold text-brand-400 truncate">{subdomain || manualSubdomain}</p>
                    {downloadDir && (
                      <>
                        <p className="text-slate-400 mt-2">Target directory:</p>
                        <p className="font-mono text-[10px] text-slate-300 break-all">{downloadDir}</p>
                      </>
                    )}
                  </div>
                  <button 
                    onClick={handleLogout}
                    className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition flex items-center justify-center gap-1"
                  >
                    Disconnect
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Download Actions Panel (only visible when authenticated) */}
          {isAuthenticated && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4">
              <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
                <Sliders className="w-5 h-5 text-brand-500" />
                <h2 className="font-semibold text-base text-white">Download Actions</h2>
              </div>
              <div className="flex flex-col gap-2">
                <button 
                  onClick={downloadMissing}
                  className="w-full py-3 bg-amber-600 hover:bg-amber-700 rounded-lg text-sm font-semibold text-white transition flex items-center justify-center gap-2 shadow-lg shadow-amber-600/10"
                >
                  <DownloadCloud className="w-4 h-4" />
                  Download Missing Classes
                </button>
                <button 
                  onClick={downloadSelected}
                  disabled={selectedLessonIds.size === 0}
                  className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-800 disabled:text-slate-500 rounded-lg text-sm font-semibold text-white transition flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/10"
                >
                  <Download className="w-4 h-4" />
                  Download Selected ({selectedLessonIds.size})
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Navigation & Classes List */}
        <div className="flex-1 space-y-6">
          {loading && (
            <div className="flex flex-col items-center justify-center py-20 bg-slate-900 border border-slate-800 rounded-xl">
              <div className="w-12 h-12 border-4 border-slate-800 border-t-brand-500 rounded-full animate-spin mb-4"></div>
              <p className="text-sm text-slate-400 font-medium">Fetching course navigation from Hotmart...</p>
            </div>
          )}

          {!isAuthenticated && !loading && (
            <div className="flex flex-col items-center justify-center py-24 bg-slate-900/50 border border-dashed border-slate-800 rounded-xl text-center px-4">
              <div className="w-16 h-16 bg-slate-900 rounded-full border border-slate-800 flex items-center justify-center text-slate-500 mb-4">
                <Lock className="w-8 h-8" />
              </div>
              <h3 className="font-semibold text-lg text-white mb-1">Enter your credentials</h3>
              <p className="text-sm text-slate-400 max-w-sm">Enter your Hotmart subdomain and Bearer Token to access and manage your course downloads.</p>
            </div>
          )}

          {isAuthenticated && !loading && (
            <>
              {/* Tab Selector */}
              <div className="flex items-center border-b border-slate-800 space-x-2">
                <button 
                  onClick={() => setActiveTab('modules')}
                  className={`py-2.5 px-4 text-sm font-semibold border-b-2 flex items-center gap-2 transition ${
                    activeTab === 'modules' 
                      ? 'border-brand-500 text-brand-500 font-bold' 
                      : 'border-transparent text-slate-400 hover:text-white'
                  }`}
                >
                  <ListVideo className="w-4 h-4" />
                  Modules & Classes
                </button>
                <button 
                  onClick={() => setActiveTab('logs')}
                  className={`py-2.5 px-4 text-sm font-semibold border-b-2 flex items-center gap-2 transition ${
                    activeTab === 'logs' 
                      ? 'border-brand-500 text-brand-500 font-bold' 
                      : 'border-transparent text-slate-400 hover:text-white'
                  }`}
                >
                  <Terminal className="w-4 h-4" />
                  Logs
                </button>
              </div>

              {/* Modules View */}
              {activeTab === 'modules' && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4">
                  {/* Controls Header */}
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <ListVideo className="w-5 h-5 text-brand-500" />
                      <h2 className="font-semibold text-base text-white">Course Outline</h2>
                    </div>
                    <div className="flex items-center gap-2 text-xs flex-wrap">
                      <button 
                        onClick={() => setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')} 
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-700 text-slate-400 hover:text-brand-500 hover:border-brand-500/50 transition font-medium"
                      >
                        <ArrowUpDown className="w-3.5 h-3.5" />
                        Sort: <span className="capitalize font-semibold text-slate-200">{sortOrder}</span>
                      </button>
                      <button 
                        onClick={selectMissing} 
                        className="px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 hover:bg-amber-500/20 transition font-medium"
                      >
                        Select Missing
                      </button>
                      <button 
                        onClick={selectAll} 
                        className="px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white transition font-medium"
                      >
                        Select All
                      </button>
                      <button 
                        onClick={deselectAll} 
                        className="px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white transition font-medium"
                      >
                        Deselect All
                      </button>
                    </div>
                  </div>

                  {/* Modules Accordion */}
                  <div className="space-y-3 max-h-[65vh] overflow-y-auto pr-1">
                    {sortedModules.map(mod => {
                      const isExpanded = !!expandedModules[mod.order];
                      return (
                        <div key={mod.order} className="border border-slate-800/80 rounded-lg overflow-hidden bg-slate-950/45">
                          {/* Header */}
                          <div 
                            onClick={() => toggleModule(mod.order)}
                            className="flex items-center justify-between p-3.5 bg-slate-900/60 cursor-pointer hover:bg-slate-900 transition select-none"
                          >
                            <div className="flex items-center gap-2 min-w-0 mr-4">
                              <span className="text-[10px] text-brand-500 bg-brand-500/10 px-2 py-0.5 rounded border border-brand-500/20 font-bold whitespace-nowrap">
                                Module {mod.order}
                              </span>
                              <span className="text-sm font-semibold text-slate-200 truncate">{mod.name}</span>
                            </div>
                            <div className="flex items-center gap-3">
                              <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                                <button 
                                  onClick={(e) => selectAllInModule(mod, e)}
                                  className="px-2 py-0.5 bg-slate-800 hover:bg-brand-500 hover:text-white text-[9px] rounded border border-slate-700 hover:border-brand-500 transition text-slate-300 font-medium"
                                >
                                  Select All
                                </button>
                                <button 
                                  onClick={(e) => deselectAllInModule(mod, e)}
                                  className="px-2 py-0.5 bg-slate-800 hover:bg-brand-500 hover:text-white text-[9px] rounded border border-slate-700 hover:border-brand-500 transition text-slate-300 font-medium"
                                >
                                  Deselect All
                                </button>
                              </div>
                              <span className="text-xs text-slate-400 font-normal whitespace-nowrap">{mod.lessons.length} classes</span>
                              <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`} />
                            </div>
                          </div>

                          {/* Lessons List */}
                          {isExpanded && (
                            <div className="border-t border-slate-800 bg-slate-900/10">
                              {mod.lessons.map(les => {
                                const isSelected = selectedLessonIds.has(les.id);
                                const download = activeDownloads[les.id];
                                return (
                                  <div key={les.id} className="flex flex-col p-3 hover:bg-slate-900/50 border-b border-slate-900/30 transition last:border-b-0">
                                    <div className="flex items-center justify-between gap-4">
                                      <div className="flex items-center gap-2.5 min-w-0">
                                        <button 
                                          type="button"
                                          onClick={() => handleSelectLesson(les.id)}
                                          className="text-slate-400 hover:text-brand-500 transition-colors"
                                        >
                                          {isSelected ? (
                                            <CheckSquare className="w-4 h-4 text-brand-500" />
                                          ) : (
                                            <Square className="w-4 h-4 text-slate-600" />
                                          )}
                                        </button>
                                        <span className="text-xs font-semibold text-slate-500">{mod.order}.{les.order}</span>
                                        <span className="text-xs font-medium text-slate-200 truncate">{les.name}</span>
                                      </div>
                                      
                                      <div className="flex items-center gap-2 shrink-0">
                                        {/* Attachment Indicators */}
                                        <div className="flex items-center gap-1 mr-2 text-[10px] text-slate-500">
                                          {les.has_video && <span className="bg-slate-800 px-1 rounded text-slate-400">Video</span>}
                                          {les.has_pdf && <span className="bg-slate-800 px-1 rounded text-slate-400">PDF</span>}
                                          {les.has_attached && <span className="bg-slate-800 px-1 rounded text-slate-400">Files</span>}
                                        </div>

                                        {/* Status badge */}
                                        {les.downloaded && (
                                          <span className="flex items-center gap-1 text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20">
                                            <CheckCircle2 className="w-2.5 h-2.5" />
                                            Downloaded
                                          </span>
                                        )}
                                        
                                        {download && download.status !== 'Completed' && (
                                          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${
                                            download.status.startsWith('Error')
                                              ? 'bg-red-500/10 text-red-400 border-red-500/20'
                                              : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                                          }`}>
                                            {download.status}
                                          </span>
                                        )}
                                      </div>
                                    </div>

                                    {/* Progress row */}
                                    {download && (
                                      <div className="mt-2.5 pl-6 flex items-center gap-3">
                                        <div className="flex-1 bg-slate-950 rounded-full h-1.5 overflow-hidden border border-slate-800">
                                          <div 
                                            className="bg-brand-500 h-full transition-all duration-300"
                                            style={{ width: `${download.percentage}%` }}
                                          ></div>
                                        </div>
                                        <span className="text-[10px] font-mono text-slate-400 min-w-[32px] text-right">
                                          {download.percentage}%
                                        </span>
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Logs View */}
              {activeTab === 'logs' && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <div className="flex items-center gap-2">
                      <Terminal className="w-5 h-5 text-brand-500" />
                      <h2 className="font-semibold text-base text-white">System Logs</h2>
                    </div>
                    <button 
                      onClick={fetchLogs} 
                      className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white transition text-xs font-medium"
                    >
                      <RefreshCw className="w-3.5 h-3.5" /> Refresh
                    </button>
                  </div>
                  <pre className="bg-slate-950 border border-slate-800/80 rounded-lg p-4 font-mono text-xs text-slate-300 max-h-[60vh] overflow-y-auto whitespace-pre-wrap leading-relaxed">
                    {logs}
                  </pre>
                </div>
              )}
            </>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 py-4 text-center text-xs text-slate-500 mt-auto">
        Developed in React & TypeScript | Connected to FastAPI Backend
      </footer>
    </div>
  );
}
