const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

let currentToken: string | null = null;

async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers || {});
  if (currentToken) {
    headers.set("Authorization", `Bearer ${currentToken}`);
  }
  
  const res = await fetch(url, { ...options, headers });
  return res;
}

export const api = {
  base: API_BASE,
  ws: WS_BASE,

  setToken(token: string | null) {
    currentToken = token;
  },

  // ── Auth ──────────────────────────────────────────────────
  async login(email: string, password: string) {
    const formData = new URLSearchParams();
    formData.append("username", email);
    formData.append("password", password);
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Login failed");
    }
    return res.json();
  },

  async getMe() {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/auth/me`);
    if (!res.ok) throw new Error("Unauthorized");
    return res.json();
  },

  async getUsers() {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/auth/users`);
    if (!res.ok) throw new Error("Failed to fetch users");
    return res.json();
  },

  async createUser(data: any) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/auth/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to create user");
    return res.json();
  },

  async updateUser(id: string, data: any) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/auth/users/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update user");
    return res.json();
  },

  async deleteUser(id: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/auth/users/${id}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete user");
    return res.json();
  },

  // ── Analytics ─────────────────────────────────────────────
  async getSummary(params?: { camera_id?: string; date_from?: string; date_to?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/analytics/summary${q ? `?${q}` : ""}`);
    if (!res.ok) return { total_entries: 0, unique_visitors: 0, avg_dwell_seconds: 0, peak_count: 0 };
    return res.json().catch(() => ({ total_entries: 0, unique_visitors: 0, avg_dwell_seconds: 0, peak_count: 0 }));
  },

  async getHourlyTraffic(params?: { camera_id?: string; target_date?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/analytics/traffic/hourly${q ? `?${q}` : ""}`);
    if (!res.ok) return [];
    const data = await res.json().catch(() => []);
    return Array.isArray(data) ? data : [];
  },

  async getDailyTraffic(days: number = 30, camera_id?: string) {
    const params: Record<string, string> = { days: String(days) };
    if (camera_id) params.camera_id = camera_id;
    const q = new URLSearchParams(params).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/analytics/traffic/daily?${q}`);
    if (!res.ok) return [];
    const data = await res.json().catch(() => []);
    return Array.isArray(data) ? data : [];
  },

  async getDwell(params?: { camera_id?: string; target_date?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/analytics/dwell${q ? `?${q}` : ""}`);
    if (!res.ok) return { distribution: [] };
    const data = await res.json().catch(() => ({ distribution: [] }));
    if (!data.distribution) data.distribution = [];
    return data;
  },

  async getHeatmap(camera_id: string, target_date?: string) {
    const params: Record<string, string> = { camera_id };
    if (target_date) params.target_date = target_date;
    const q = new URLSearchParams(params).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/analytics/heatmap?${q}`);
    if (!res.ok) throw new Error("Failed to fetch heatmap");
    return res.json();
  },

  async getQueue(arg1?: string | { camera_id?: string; zone_name?: string; target_date?: string }, arg2?: { zone_name?: string; target_date?: string }) {
    let params: Record<string, string> = {};
    if (typeof arg1 === "string") {
      params.camera_id = arg1;
      if (arg2) params = { ...params, ...(arg2 as Record<string, string>) };
    } else if (arg1) {
      params = { ...(arg1 as Record<string, string>) };
    }
    const q = new URLSearchParams(params).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/analytics/queue${q ? `?${q}` : ""}`);
    if (!res.ok) throw new Error("Failed to fetch queue");
    return res.json();
  },

  async getConversion(params?: { camera_id?: string; target_date?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/analytics/conversion${q ? `?${q}` : ""}`);
    if (!res.ok) throw new Error("Failed to fetch conversion");
    return res.json();
  },

  async getLive(camera_id?: string) {
    const params: Record<string, string> = {};
    if (camera_id) params.camera_id = camera_id;
    const q = new URLSearchParams(params).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/events/status${q ? `?${q}` : ""}`);
    if (!res.ok) throw new Error("Failed to fetch live counts");
    return res.json();
  },

  async getTimelineEvents(params?: { limit?: number; offset?: number; camera_id?: string; date_from?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/timeline${q ? `?${q}` : ""}`);
    if (!res.ok) return [];
    const json = await res.json();
    return json.data || json || [];
  },

  // ── Event Lines ──────────────────────────────────────────
  async getLines(camera_id: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/events/lines/${camera_id}`);
    if (!res.ok) return { lines: [] };
    return res.json().catch(() => ({ lines: [] }));
  },

  async createLine(data: any) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/events/lines`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to create line");
    return res.json();
  },

  async deleteLine(camera_id: string, line_id: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/events/lines/${camera_id}/${line_id}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete line");
    return res.json();
  },

  // ── Cameras ───────────────────────────────────────────────
  async getCameras(params?: { status?: string; include_inactive?: boolean }) {
    const q = params ? new URLSearchParams(params as Record<string, string>).toString() : "";
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras${q ? `?${q}` : ""}`);
    if (!res.ok) return { cameras: [], summary: { total: 0, active: 0, degraded: 0, error: 0 } };
    return res.json().catch(() => ({ cameras: [], summary: { total: 0, active: 0, degraded: 0, error: 0 } }));
  },

  async getCameraStats() {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/stats`);
    if (!res.ok) throw new Error("Failed to fetch camera stats");
    return res.json();
  },

  async getCamera(id: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/${id}`);
    if (!res.ok) throw new Error("Camera not found");
    return res.json();
  },

  async getCameraHealth(id: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/${id}/health`);
    if (!res.ok) throw new Error("Failed to fetch camera health");
    return res.json();
  },

  async getAllHealth() {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/health/all`);
    if (!res.ok) throw new Error("Failed to fetch all health");
    return res.json();
  },

  async validateUrl(url: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/validate-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) throw new Error("Validation request failed");
    return res.json();
  },

  async testConnection(url: string, username?: string, password?: string, timeout = 8) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/test-connection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, username: username || null, password: password || null, timeout }),
    });
    if (!res.ok) throw new Error("Test request failed");
    return res.json();
  },

  async createCamera(data: any) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to create camera");
    }
    return res.json();
  },

  async updateCamera(id: string, data: Record<string, unknown>) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to update camera");
    }
    return res.json();
  },

  async deleteCamera(id: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete camera");
  },

  async restartCamera(id: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/${id}/restart`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to restart camera");
    return res.json();
  },

  async enableCamera(id: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/${id}/enable`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to enable camera");
    return res.json();
  },

  async disableCamera(id: string) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/${id}/disable`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to disable camera");
    return res.json();
  },

  async updateZones(id: string, zone_config: unknown) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cameras/${id}/zones`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(zone_config),
    });
    if (!res.ok) throw new Error("Failed to update zones");
    return res.json();
  },

  // ── Reports ───────────────────────────────────────────────
  async getReportData(timeframe: "daily" | "weekly" | "monthly", days_back: number = 30, camera_id?: string) {
    const params: Record<string, string> = { timeframe, days_back: String(days_back) };
    if (camera_id) params.camera_id = camera_id;
    const q = new URLSearchParams(params).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/reports/data?${q}`);
    if (!res.ok) throw new Error("Failed to fetch report");
    return res.json();
  },

  exportCSVUrl(timeframe: "daily" | "weekly" | "monthly", days_back: number = 30, camera_id?: string) {
    const params: Record<string, string> = { timeframe, days_back: String(days_back) };
    if (camera_id) params.camera_id = camera_id;
    // Export URLs might need token if downloading directly via link, 
    // but usually a link won't have headers. For now, we leave as standard URL.
    return `${API_BASE}/api/v1/reports/export/csv?${new URLSearchParams(params)}`;
  },

  exportExcelUrl(timeframe: "daily" | "weekly" | "monthly", days_back: number = 30, camera_id?: string) {
    const params: Record<string, string> = { timeframe, days_back: String(days_back) };
    if (camera_id) params.camera_id = camera_id;
    return `${API_BASE}/api/v1/reports/export/excel?${new URLSearchParams(params)}`;
  },

  exportPDFUrl(timeframe: "daily" | "weekly" | "monthly", days_back: number = 30, camera_id?: string) {
    const params: Record<string, string> = { timeframe, days_back: String(days_back) };
    if (camera_id) params.camera_id = camera_id;
    return `${API_BASE}/api/v1/reports/export/pdf?${new URLSearchParams(params)}`;
  },

  // ── Cloud Dashboard ───────────────────────────────────────
  async getCloudDashboard() {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cloud/dashboard`);
    if (!res.ok) throw new Error("Failed to fetch cloud dashboard");
    return res.json();
  },

  async syncCloud() {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/cloud/sync`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to sync with cloud");
    return res.json();
  },

  // ── Settings ──────────────────────────────────────────────
  async getSettings() {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/settings`);
    if (!res.ok) throw new Error("Failed to fetch settings");
    return res.json();
  },

  async updateSettings(data: any) {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update settings");
    return res.json();
  },

  // ── Health ────────────────────────────────────────────────
  async getHealth() {
    const res = await fetchWithAuth(`${API_BASE}/api/health`);
    if (!res.ok) throw new Error("Backend unavailable");
    return res.json();
  },

  // ── Transaction Intelligence ──────────────────────────────

  async getTxnLiveSessions() {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/transactions/intelligence/sessions/live`);
    if (!res.ok) return { sessions: [], total: 0, at_checkout: 0, likely_purchases: 0 };
    return res.json().catch(() => ({ sessions: [], total: 0, at_checkout: 0, likely_purchases: 0 }));
  },

  async getTxnSessions(params?: { camera_id?: string; confidence_level?: string; target_date?: string; limit?: number }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/transactions/intelligence/sessions${q ? `?${q}` : ""}`);
    if (!res.ok) return { sessions: [], total: 0 };
    return res.json().catch(() => ({ sessions: [], total: 0 }));
  },

  async getTxnStats(params?: { camera_id?: string; target_date?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/transactions/intelligence/stats${q ? `?${q}` : ""}`);
    if (!res.ok) return {
      total_sessions: 0, likely_purchases: 0, estimated_conversion_rate: 0,
      checkout_visitors: 0, checkout_abandonment: 0, avg_confidence: 0,
      payment_type_distribution: { cash: 0, card: 0, upi: 0 },
      live_at_checkout: 0, live_sessions: 0,
    };
    return res.json().catch(() => ({ total_sessions: 0, likely_purchases: 0, estimated_conversion_rate: 0 }));
  },

  async getTxnFunnel(params?: { camera_id?: string; target_date?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/transactions/intelligence/funnel${q ? `?${q}` : ""}`);
    if (!res.ok) return { funnel: [], total_entries: 0 };
    return res.json().catch(() => ({ funnel: [], total_entries: 0 }));
  },

  async getTxnDistribution(params?: { camera_id?: string; target_date?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/transactions/intelligence/distribution${q ? `?${q}` : ""}`);
    if (!res.ok) return { distribution: [], total: 0 };
    return res.json().catch(() => ({ distribution: [], total: 0 }));
  },

  async getTxnTimeline(limit?: number) {
    const q = limit ? `?limit=${limit}` : "";
    const res = await fetchWithAuth(`${API_BASE}/api/v1/transactions/intelligence/timeline${q}`);
    if (!res.ok) return { events: [], total: 0 };
    return res.json().catch(() => ({ events: [], total: 0 }));
  },

  async getTxnQueueMetrics(params?: { camera_id?: string; target_date?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/transactions/intelligence/queue-metrics${q ? `?${q}` : ""}`);
    if (!res.ok) return { queue_completions: 0, checkout_entries: 0, queue_success_rate: 0 };
    return res.json().catch(() => ({ queue_completions: 0, checkout_entries: 0, queue_success_rate: 0 }));
  },

  // ── Zone Distribution ─────────────────────────────────────────────────────
  async getZones(params?: { camera_id?: string; target_date?: string }) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/analytics/zones${q ? `?${q}` : ""}`);
    if (!res.ok) return { zones: [], total_zone_visits: 0 };
    return res.json().catch(() => ({ zones: [], total_zone_visits: 0 }));
  },

  // ── Conversion Trend ──────────────────────────────────────────────────────
  async getConversionTrend(params?: { camera_id?: string; days?: number }) {
    const p: Record<string, string> = {};
    if (params?.camera_id) p.camera_id = params.camera_id;
    if (params?.days) p.days = String(params.days);
    const q = new URLSearchParams(p).toString();
    const res = await fetchWithAuth(`${API_BASE}/api/v1/analytics/conversion-trend${q ? `?${q}` : ""}`);
    if (!res.ok) return { trend: [], days: 7 };
    return res.json().catch(() => ({ trend: [], days: 7 }));
  },
};


export const WS_LIVE_URL = `${WS_BASE}/ws/live`;
export const WS_TIMELINE_URL = `${WS_BASE}/ws/timeline`;
