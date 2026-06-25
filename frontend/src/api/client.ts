import type {
  ActiveRecipe,
  AlertEvent,
  AppConfig,
  DashboardSummary,
  DashboardState,
  HistoryResponse,
  Machine,
  Recipe,
  RecipeLimitsResponse,
  Section,
  SectionLiveResponse
} from '../types';

const API_BASE = '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const error = await response.json();
      message = error.detail || error.message || message;
    } catch {
      // keep default
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  getConfig: () => request<AppConfig>('/api/config'),
  listMachines: () => request<Machine[]>('/api/machines'),
  getMachine: (machineId: number) => request<Machine>(`/api/machines/${machineId}`),
  getSummary: (machineId: number) => request<DashboardSummary>(`/api/machines/${machineId}/summary`),
  syncMachine: (machineId: number) => request(`/api/machines/${machineId}/sync`, { method: 'POST' }),
  getDashboard: (machineId: number) => request<DashboardState>(`/api/machines/${machineId}/dashboard`),
  getSections: (machineId: number, includeHidden = true) =>
    request<Section[]>(`/api/machines/${machineId}/sections?include_hidden=${includeHidden}`),
  updateSection: (sectionId: number, payload: Partial<Section>) =>
    request<Section>(`/api/sections/${sectionId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  getSectionLive: (machineId: number, sectionKey: string, includeHidden = true) =>
    request<SectionLiveResponse>(
      `/api/machines/${machineId}/sections/${encodeURIComponent(sectionKey)}/live?include_hidden=${includeHidden}`
    ),
  updateTagConfig: (
    machineId: number,
    tagId: number,
    payload: { is_visible?: boolean; show_in_history_default?: boolean; sort_order?: number }
  ) => request(`/api/machines/${machineId}/tags/${tagId}/config`, { method: 'PATCH', body: JSON.stringify(payload) }),
  getHistory: (machineId: number, start: string, end: string, tagIds: number[], sectionKey?: string | null) => {
    const params = new URLSearchParams();
    if (sectionKey) {
      params.set('section_key', sectionKey);
    }
    params.set('start', start);
    params.set('end', end);
    tagIds.forEach((id) => params.append('tag_ids', String(id)));
    return request<HistoryResponse>(`/api/machines/${machineId}/history?${params.toString()}`);
  },
  listRecipes: (machineId: number) => request<Recipe[]>(`/api/machines/${machineId}/recipes`),
  createRecipe: (machineId: number, payload: { recipe_name: string; recipe_code?: string; description?: string }) =>
    request<Recipe>(`/api/machines/${machineId}/recipes`, { method: 'POST', body: JSON.stringify(payload) }),
  updateRecipe: (recipeId: number, payload: Partial<Recipe>) =>
    request<Recipe>(`/api/recipes/${recipeId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  getRecipeLimits: (recipeId: number, sectionKey: string) =>
    request<RecipeLimitsResponse>(`/api/recipes/${recipeId}/limits?section_key=${encodeURIComponent(sectionKey)}`),
  updateRecipeLimits: (
    recipeId: number,
    limits: { tag_id: number; min_value?: number | null; max_value?: number | null; is_enabled: boolean }[]
  ) => request(`/api/recipes/${recipeId}/limits`, { method: 'PUT', body: JSON.stringify({ limits }) }),
  getActiveRecipe: (machineId: number) => request<ActiveRecipe | null>(`/api/machines/${machineId}/active-recipe`),
  setActiveRecipe: (machineId: number, recipeId: number | null, selectionMode: 'manual' | 'automatic' = 'manual') =>
    request<ActiveRecipe | null>(`/api/machines/${machineId}/active-recipe`, {
      method: 'PUT',
      body: JSON.stringify({ recipe_id: recipeId, selection_mode: selectionMode })
    }),
  evaluateAlerts: (machineId: number) =>
    request(`/api/machines/${machineId}/evaluate-alerts`, { method: 'POST' }),
  listAlerts: (machineId: number, activeOnly = true, limit = 200) =>
    request<AlertEvent[]>(`/api/machines/${machineId}/alerts?active_only=${activeOnly}&limit=${limit}`),
  acknowledgeAlert: (alertId: number, acknowledgedBy = 'dashboard', acknowledgeNote = '') =>
    request<AlertEvent>(`/api/alerts/${alertId}/acknowledge`, {
      method: 'POST',
      body: JSON.stringify({ acknowledged_by: acknowledgedBy, acknowledge_note: acknowledgeNote })
    })
};
