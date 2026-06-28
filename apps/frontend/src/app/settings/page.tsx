"use client";

import { Building2, Camera, Cloud, Cpu, Users, Plus, Trash2, Edit2, ShieldAlert, Check, X, LogOut } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useState, useEffect } from "react";

function ToggleSwitch({ isOn, label, description, onChange }: any) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0">
      <div>
        <div className="text-xs font-bold text-gray-900">{label}</div>
        <p className="text-[10px] text-gray-500 mt-0.5">{description}</p>
      </div>
      <button 
        onClick={() => onChange(!isOn)}
        className={`w-8 h-4 rounded-full flex items-center p-0.5 transition-colors ${isOn ? 'bg-emerald-500' : 'bg-gray-200'}`}
      >
        <div className={`w-3 h-3 bg-white rounded-full shadow-sm transform transition-transform ${isOn ? 'translate-x-4' : 'translate-x-0'}`} />
      </button>
    </div>
  );
}

export default function SettingsPage() {
  const queryClient = useQueryClient();

  // Settings
  const { data: settingsData } = useQuery({ queryKey: ["settings"], queryFn: () => api.getSettings() });
  const updateSettings = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] })
  });

  // Cameras
  const { data: camerasData } = useQuery({ queryKey: ["cameras"], queryFn: () => api.getCameras() });
  const cameras = camerasData?.cameras || [];
  const deleteCamera = useMutation({
    mutationFn: api.deleteCamera,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] })
  });
  const createCamera = useMutation({
    mutationFn: api.createCamera,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      setShowAddCamera(false);
      setNewCamera({ name: "", url: "" });
    }
  });

  // Cloud Dashboard
  const { data: cloudData } = useQuery({ queryKey: ["cloud_dashboard"], queryFn: () => api.getCloudDashboard() });

  // Users
  const { data: usersData } = useQuery({ queryKey: ["users"], queryFn: () => api.getUsers() });
  const usersList = usersData || [];
  const createUser = useMutation({
    mutationFn: api.createUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setShowAddUser(false);
      setNewUser({ email: "", password: "", full_name: "", role: "viewer" });
    }
  });
  const editUserMutation = useMutation({
    mutationFn: ({ id, data }: { id: string, data: any }) => api.updateUser(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEditingUser(null);
    }
  });
  const deleteUser = useMutation({
    mutationFn: api.deleteUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] })
  });

  // Local States for Inputs
  const [storeInfo, setStoreInfo] = useState({
    name: "", region: "", address: "", timezone: "", currency: ""
  });
  const [toggles, setToggles] = useState({
    autoSync: true, metadata: true, analytics: true, reports: true, video: false,
    queue: true, transaction: true, heatmap: true, zone: true, face: true
  });
  const [aiSettings, setAiSettings] = useState({
    detectionConfidence: 0.6, frameEvaluationRate: 5
  });

  const [isSaved, setIsSaved] = useState(false);
  const [isOutage, setIsOutage] = useState(false);

  const [showAddCamera, setShowAddCamera] = useState(false);
  const [newCamera, setNewCamera] = useState({ name: "", url: "" });

  const [showAddUser, setShowAddUser] = useState(false);
  const [newUser, setNewUser] = useState({ email: "", password: "", full_name: "", role: "viewer" });
  
  const [editingUser, setEditingUser] = useState<any>(null);

  // Sync state from backend settings
  useEffect(() => {
    if (settingsData) {
      setStoreInfo({
        name: settingsData.name || "",
        region: settingsData.region || "",
        address: settingsData.address || "",
        timezone: settingsData.timezone || "",
        currency: settingsData.currency || ""
      });
      setToggles({
        autoSync: settingsData.auto_sync ?? true,
        metadata: settingsData.sync_metadata ?? true,
        analytics: settingsData.sync_analytics ?? true,
        reports: settingsData.sync_reports ?? true,
        video: settingsData.sync_video ?? false,
        queue: settingsData.queue_detection ?? true,
        transaction: settingsData.transaction_detection ?? true,
        heatmap: settingsData.heatmap_generation ?? true,
        zone: settingsData.zone_tracking ?? true,
        face: settingsData.face_anonymization ?? true
      });
      setAiSettings({
        detectionConfidence: settingsData.detection_confidence ?? 0.6,
        frameEvaluationRate: settingsData.frame_evaluation_rate ?? 5
      });
    }
  }, [settingsData]);

  const handleSaveStoreInfo = () => {
    updateSettings.mutate(storeInfo, {
      onSuccess: () => {
        setIsSaved(true);
        setTimeout(() => setIsSaved(false), 2000);
      }
    });
  };

  const updateToggle = (key: keyof typeof toggles, backendKey: string) => (val: boolean) => {
    setToggles(prev => ({ ...prev, [key]: val }));
    updateSettings.mutate({ [backendKey]: val });
  };

  const updateAiSetting = (key: keyof typeof aiSettings, backendKey: string) => (val: number) => {
    setAiSettings(prev => ({ ...prev, [key]: val }));
    updateSettings.mutate({ [backendKey]: val });
  };

  const handleAddUser = () => {
    if (!newUser.full_name || !newUser.email || !newUser.password) return;
    createUser.mutate(newUser);
  };
  
  const handleEditUser = () => {
    if (!editingUser.full_name || !editingUser.email) return;
    const payload = {
      full_name: editingUser.full_name,
      email: editingUser.email,
      role: editingUser.role,
      ...(editingUser.password ? { password: editingUser.password } : {})
    };
    editUserMutation.mutate({ id: editingUser.id, data: payload });
  };

  return (
    <div className="max-w-[1600px] mx-auto pb-10 space-y-6 relative">

      {/* Store Information */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="p-4 border-b border-gray-100 flex items-center gap-2">
          <Building2 className="w-4 h-4 text-emerald-500" />
          <div>
            <h2 className="text-sm font-bold text-gray-900">Store Information</h2>
            <p className="text-[10px] text-gray-500">Local store identity and configuration</p>
          </div>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 mb-6">
            {Object.entries(storeInfo).map(([k, v]) => (
              <div key={k}>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">{k}</label>
                <input 
                  type="text" 
                  value={v} 
                  onChange={e => setStoreInfo({...storeInfo, [k]: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500" 
                />
              </div>
            ))}
          </div>
          <div className="flex justify-end items-center gap-4">
            {isSaved && <span className="text-xs font-bold text-emerald-600 flex items-center gap-1"><Check className="w-3.5 h-3.5"/> Saved</span>}
            <button onClick={handleSaveStoreInfo} disabled={updateSettings.isPending} className="px-4 py-2 bg-emerald-600 text-white text-xs font-bold rounded-lg shadow-sm hover:bg-emerald-700 transition-colors disabled:opacity-50">
              Save Changes
            </button>
          </div>
        </div>
      </div>

      {/* Camera Management */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/30">
          <div className="flex items-center gap-2">
            <Camera className="w-4 h-4 text-gray-400" />
            <div>
              <h2 className="text-sm font-bold text-gray-900">Camera Management</h2>
              <p className="text-[10px] text-gray-500">{cameras.length} active video streams</p>
            </div>
          </div>
          <button onClick={() => setShowAddCamera(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-xs font-bold text-gray-700 hover:bg-gray-50">
            <Plus className="w-3.5 h-3.5" /> Add Camera
          </button>
        </div>
        <div className="p-4">
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            {cameras.map((c: any, i: number) => (
              <div key={c.id || i} className="flex items-center justify-between p-3 border-b border-gray-100 last:border-0 hover:bg-gray-50/50">
                <div>
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-bold text-gray-900">{c.name}</span>
                    <span className="px-1.5 py-0.5 bg-emerald-50 text-emerald-600 text-[9px] font-bold rounded border border-emerald-100 uppercase tracking-widest">Active</span>
                  </div>
                  <span className="text-[10px] text-gray-400 font-mono">{c.url}</span>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-[10px] font-bold text-gray-500 text-right">
                    {c.fps || "15"} FPS <span className="text-gray-300 mx-1">•</span> {c.bitrate || "450"} kbps
                  </div>
                  <button onClick={() => c.id ? deleteCamera.mutate(c.id) : null} className="p-1.5 text-rose-400 hover:bg-rose-50 rounded-md transition-colors" title="Delete Camera">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
            {cameras.length === 0 && <div className="p-4 text-xs text-gray-500 text-center">No cameras configured.</div>}
          </div>
        </div>
      </div>

      {/* Cloud Sync */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/30">
          <div className="flex items-center gap-2">
            <Cloud className={`w-4 h-4 ${isOutage ? 'text-rose-500' : 'text-emerald-500'}`} />
            <div>
              <h2 className="text-sm font-bold text-gray-900">Cloud Sync</h2>
              <p className={`text-[10px] ${isOutage ? 'text-rose-500 font-bold' : 'text-gray-500'}`}>{isOutage ? 'Outage Simulated (Local Only)' : 'Local-first cloud data synchronization'}</p>
            </div>
          </div>
          <button onClick={() => setIsOutage(!isOutage)} className={`flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-xs font-bold transition-colors ${isOutage ? 'bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100' : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'}`}>
            <Cloud className="w-3.5 h-3.5" /> {isOutage ? 'End Outage Simulation' : 'Simulate Outage'}
          </button>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-2 gap-8 mb-6">
            <div>
              <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Sync Endpoint</label>
              <input type="text" readOnly value={cloudData?.endpoint || "https://cloud.retail-agent.example.com"} className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg bg-gray-50/50 outline-none" />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Sync Status</label>
              <div className="flex items-center gap-4">
                <span className="text-xs font-bold text-gray-700">Pending: <span className="text-emerald-600">{cloudData?.pending_records || 0}</span></span>
                <span className="text-xs font-bold text-gray-700">Synced: <span className="text-emerald-600">{cloudData?.synced_records || 0}</span></span>
                <span className="text-xs font-bold text-gray-700">Failed: <span className="text-rose-600">{cloudData?.failed_records || 0}</span></span>
              </div>
            </div>
          </div>
          <div className="border border-gray-200 rounded-lg p-4 mb-4">
            <ToggleSwitch isOn={toggles.autoSync} onChange={updateToggle('autoSync', 'auto_sync')} label="Auto Sync" description="Sync telemetry and events to cloud when online" />
            <ToggleSwitch isOn={toggles.metadata} onChange={updateToggle('metadata', 'sync_metadata')} label="Sync Metadata" description="Store level configuration sync" />
            <ToggleSwitch isOn={toggles.analytics} onChange={updateToggle('analytics', 'sync_analytics')} label="Sync Analytics" description="Aggregated traffic and zone analytics" />
            <ToggleSwitch isOn={toggles.reports} onChange={updateToggle('reports', 'sync_reports')} label="Sync Reports" description="Generated PDF/Excel reports" />
            <ToggleSwitch isOn={toggles.video} onChange={updateToggle('video', 'sync_video')} label={<span className="flex items-center gap-1 text-amber-600"><ShieldAlert className="w-3 h-3" /> Upload Video Footage</span>} description="WARNING: High bandwidth - Upload raw video clips for cloud ML" />
          </div>
          <div className="px-3 py-2 bg-emerald-50 border border-emerald-100 rounded-lg text-[10px] text-emerald-800 font-medium flex items-start gap-2">
            <span className="text-emerald-500">✓</span> Source of Truth: The local database instance is the master copy. Cloud database is a synchronized copy.
          </div>
        </div>
      </div>

      {/* AI Engine Settings */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="p-4 border-b border-gray-100 flex items-center gap-2 bg-gray-50/30">
          <Cpu className="w-4 h-4 text-orange-500" />
          <div>
            <h2 className="text-sm font-bold text-gray-900">AI Engine Settings</h2>
            <p className="text-[10px] text-gray-500">Local inferencing and processing</p>
          </div>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-2 gap-8 mb-8">
            <div>
              <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2">Detection Model</label>
              <div className="flex items-center gap-2 px-3 py-2 border border-emerald-200 bg-emerald-50/30 rounded-lg w-max">
                <span className="text-xs font-bold text-emerald-600 bg-white px-2 py-0.5 rounded border border-emerald-100">YOLOv11n</span>
                <span className="text-[10px] font-medium text-gray-500">Lightweight - 14 FPS on CPU</span>
              </div>
            </div>
            <div>
              <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2">Tracker Model</label>
              <div className="flex items-center gap-2 px-3 py-2 border border-sky-200 bg-sky-50/30 rounded-lg w-max">
                <span className="text-xs font-bold text-sky-600 bg-white px-2 py-0.5 rounded border border-sky-100">ByteTrack</span>
                <span className="text-[10px] font-medium text-gray-500">Multi-object tracking</span>
              </div>
            </div>
          </div>
          
          <div className="space-y-6 mb-8">
            <div>
              <div className="flex justify-between items-end mb-2">
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider">Detection Confidence Threshold</label>
                <span className="text-xs font-bold text-gray-900">{Math.round(aiSettings.detectionConfidence * 100)}%</span>
              </div>
              <input 
                type="range" 
                min="0.1" 
                max="0.95" 
                step="0.05" 
                value={aiSettings.detectionConfidence}
                onChange={(e) => setAiSettings({...aiSettings, detectionConfidence: parseFloat(e.target.value)})}
                onMouseUp={() => updateAiSetting('detectionConfidence', 'detection_confidence')(aiSettings.detectionConfidence)}
                className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
            </div>
            <div>
              <div className="flex justify-between items-end mb-2">
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider">Frame Evaluation Rate</label>
                <span className="text-xs font-bold text-gray-900">{aiSettings.frameEvaluationRate} FPS</span>
              </div>
              <input 
                type="range" 
                min="1" 
                max="30" 
                step="1" 
                value={aiSettings.frameEvaluationRate}
                onChange={(e) => setAiSettings({...aiSettings, frameEvaluationRate: parseInt(e.target.value)})}
                onMouseUp={() => updateAiSetting('frameEvaluationRate', 'frame_evaluation_rate')(aiSettings.frameEvaluationRate)}
                className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
            </div>
          </div>

          <div className="border border-gray-200 rounded-lg p-4 mb-4">
            <ToggleSwitch isOn={toggles.queue} onChange={updateToggle('queue', 'queue_detection')} label="Queue Detection" description="Detect people in queues and measure wait times" />
            <ToggleSwitch isOn={toggles.transaction} onChange={updateToggle('transaction', 'transaction_detection')} label="Transaction Detection" description="Detect checkout interactions and POS proxy events" />
            <ToggleSwitch isOn={toggles.heatmap} onChange={updateToggle('heatmap', 'heatmap_generation')} label="Heatmap Generation" description="Aggregate customer density visualization" />
            <ToggleSwitch isOn={toggles.zone} onChange={updateToggle('zone', 'zone_tracking')} label="Zone Tracking" description="Track visitors across defined store zones" />
            <ToggleSwitch isOn={toggles.face} onChange={updateToggle('face', 'face_anonymization')} label="Face Anonymization" description="Blur all faces in video feeds - recommended for privacy" />
          </div>

          <div className="px-3 py-2 bg-rose-50 border border-rose-100 rounded-lg text-[10px] text-rose-800 font-medium flex items-start gap-2">
            <ShieldAlert className="w-3.5 h-3.5 text-rose-500 shrink-0" />
            <span><strong>Privacy Disclaimer:</strong> No facial recognition. No biometric data collection. All tracking is anonymous (Visitor ID only).</span>
          </div>
        </div>
      </div>

      {/* User Management */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/30">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-gray-400" />
            <div>
              <h2 className="text-sm font-bold text-gray-900">User Management</h2>
              <p className="text-[10px] text-gray-500">Local admin and dashboard access</p>
            </div>
          </div>
          <button onClick={() => setShowAddUser(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-xs font-bold text-gray-700 hover:bg-gray-50">
            <Plus className="w-3.5 h-3.5" /> Add User
          </button>
        </div>
        <div className="p-4">
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            {usersList.map((u: any) => (
              <div key={u.id} className="flex items-center justify-between p-3 border-b border-gray-100 last:border-0 hover:bg-gray-50/50">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-500 border border-gray-200 uppercase">
                    {u.full_name ? u.full_name.charAt(0) : "U"}
                  </div>
                  <div>
                    <div className="text-xs font-bold text-gray-900 mb-0.5">{u.full_name}</div>
                    <div className="text-[10px] text-gray-400">{u.email}</div>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  <span className="text-[10px] font-bold text-gray-500 w-16 uppercase">{u.role}</span>
                  <span className={`w-20 text-center px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-widest bg-emerald-50 text-emerald-600 border border-emerald-100`}>
                    Active
                  </span>
                  <button onClick={() => setEditingUser(u)} className="px-3 py-1.5 bg-white border border-gray-200 rounded text-[10px] font-bold text-gray-700 hover:bg-gray-50">
                    Edit
                  </button>
                  <button onClick={() => deleteUser.mutate(u.id)} className="p-1.5 text-rose-400 hover:bg-rose-50 rounded-md transition-colors" title="Delete User">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Add Camera Modal */}
      {showAddCamera && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-gray-50">
              <h3 className="text-sm font-bold text-gray-900">Add Camera</h3>
              <button onClick={() => setShowAddCamera(false)} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Camera Name</label>
                <input 
                  type="text" 
                  value={newCamera.name} 
                  onChange={e => setNewCamera({...newCamera, name: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500" 
                  placeholder="e.g. Back Entrance"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">RTSP Stream URL</label>
                <input 
                  type="text" 
                  value={newCamera.url} 
                  onChange={e => setNewCamera({...newCamera, url: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500" 
                  placeholder="rtsp://admin:password@10.0.0.100/stream"
                />
              </div>
            </div>
            <div className="p-4 border-t border-gray-100 flex justify-end gap-3 bg-gray-50">
              <button onClick={() => setShowAddCamera(false)} className="px-4 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 rounded-lg">Cancel</button>
              <button 
                onClick={() => createCamera.mutate({ name: newCamera.name, rtsp_url: newCamera.url })}
                disabled={createCamera.isPending || !newCamera.name || !newCamera.url}
                className="px-4 py-2 bg-emerald-600 text-white text-xs font-bold rounded-lg shadow-sm hover:bg-emerald-700 disabled:opacity-50"
              >
                {createCamera.isPending ? "Connecting..." : "Connect Camera"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add User Modal */}
      {showAddUser && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-gray-50">
              <h3 className="text-sm font-bold text-gray-900">Add User</h3>
              <button onClick={() => setShowAddUser(false)} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Full Name</label>
                <input 
                  type="text" 
                  value={newUser.full_name} 
                  onChange={e => setNewUser({...newUser, full_name: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500" 
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Email</label>
                <input 
                  type="email" 
                  value={newUser.email} 
                  onChange={e => setNewUser({...newUser, email: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500" 
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Password</label>
                <input 
                  type="password" 
                  value={newUser.password} 
                  onChange={e => setNewUser({...newUser, password: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500" 
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Role</label>
                <select 
                  value={newUser.role} 
                  onChange={e => setNewUser({...newUser, role: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500 bg-white"
                >
                  <option value="admin">Admin</option>
                  <option value="manager">Manager</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
            </div>
            <div className="p-4 border-t border-gray-100 flex justify-end gap-3 bg-gray-50">
              <button onClick={() => setShowAddUser(false)} className="px-4 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 rounded-lg">Cancel</button>
              <button 
                onClick={handleAddUser}
                disabled={!newUser.full_name || !newUser.email || !newUser.password || createUser.isPending}
                className="px-4 py-2 bg-emerald-600 text-white text-xs font-bold rounded-lg shadow-sm hover:bg-emerald-700 disabled:opacity-50"
              >
                {createUser.isPending ? "Adding..." : "Add User"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {editingUser && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-gray-50">
              <h3 className="text-sm font-bold text-gray-900">Edit User</h3>
              <button onClick={() => setEditingUser(null)} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Full Name</label>
                <input 
                  type="text" 
                  value={editingUser.full_name} 
                  onChange={e => setEditingUser({...editingUser, full_name: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500" 
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Email</label>
                <input 
                  type="email" 
                  value={editingUser.email} 
                  onChange={e => setEditingUser({...editingUser, email: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500" 
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">New Password (optional)</label>
                <input 
                  type="password" 
                  value={editingUser.password || ""} 
                  onChange={e => setEditingUser({...editingUser, password: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500" 
                  placeholder="Leave blank to keep unchanged"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Role</label>
                <select 
                  value={editingUser.role} 
                  onChange={e => setEditingUser({...editingUser, role: e.target.value})}
                  className="w-full text-sm font-medium text-gray-900 px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500 bg-white"
                >
                  <option value="admin">Admin</option>
                  <option value="manager">Manager</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
            </div>
            <div className="p-4 border-t border-gray-100 flex justify-end gap-3 bg-gray-50">
              <button onClick={() => setEditingUser(null)} className="px-4 py-2 text-xs font-bold text-gray-700 hover:bg-gray-100 rounded-lg">Cancel</button>
              <button 
                onClick={handleEditUser}
                disabled={!editingUser.full_name || !editingUser.email || editUserMutation.isPending}
                className="px-4 py-2 bg-emerald-600 text-white text-xs font-bold rounded-lg shadow-sm hover:bg-emerald-700 disabled:opacity-50"
              >
                {editUserMutation.isPending ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
