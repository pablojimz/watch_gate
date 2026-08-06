export type RoleName = 'admin_organizacion' | 'mantenedor' | 'revisor'
export type Semaforo = 'verde' | 'amarillo' | 'rojo'
export type FeedbackValue = 'correcto' | 'falso_positivo'

export interface LayerResult {
  layer_name: string
  risk_score: number
  justification: string
  skipped: boolean
  skip_reason: string | null
}

export interface ScoreOut {
  id: number
  score: number
  semaforo: Semaforo
  layer_results: Record<string, LayerResult>
  weights_used: Record<string, number>
  pr_id: string
  repo: string
  timestamp: string
  author_login: string | null
  human_feedback: FeedbackValue | null
}

export interface MeResponse {
  login: string
  is_admin: boolean
  repos: string[]
}

export interface RepoSettings {
  weights: Record<string, number>
  thresholds: Record<string, number>
  layers_enabled: Record<string, boolean>
  risk_colors: Record<string, string>
  block_on_high: boolean
  require_feedback_on_high: boolean
  source: 'default' | 'repo'
}

export type LlmProvider = 'anthropic' | 'gemini' | 'openai' | 'local'

export interface LlmSettings {
  provider: LlmProvider
  model: string
  base_url: string | null
  api_key_set: boolean
  api_key_masked: string | null
  monthly_budget_tokens: number | null
  max_diff_tokens: number | null
}

export interface LlmSettingsUpdate {
  provider: LlmProvider
  model: string
  base_url: string | null
  api_key?: string | null
  clear_api_key?: boolean
  monthly_budget_tokens: number | null
  max_diff_tokens: number | null
}

export interface RepoMetricRow {
  repo: string
  prs: number
  avg_score: number
  verde: number
  amarillo: number
  rojo: number
  feedback_pending: number
}

export interface OrgMetrics {
  total_prs: number
  avg_score: number
  repos_count: number
  by_semaforo: Record<string, number>
  feedback_correct: number
  feedback_false_positive: number
  feedback_pending: number
  layer_avg: Record<string, number>
  by_repo: RepoMetricRow[]
  trend: { day: string; avg_score: number; count: number }[]
}

export interface UiSettings {
  primary_color: string
  accent_color: string
  radius: 'none' | 'sm' | 'md' | 'lg'
  font_scale: 'sm' | 'md' | 'lg'
  density: 'compact' | 'comfortable'
  default_theme: 'light' | 'dark' | 'system'
}

export interface RepoRole {
  user_login: string
  repo: string
  role: RoleName
}

const API = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!response.ok) {
    const detail = await response.text()
    try {
      const parsed = JSON.parse(detail) as { detail?: string }
      throw new Error(parsed.detail || detail || response.statusText)
    } catch (err) {
      if (err instanceof Error && err.message !== detail) throw err
      throw new Error(detail || response.statusText)
    }
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  me: () => request<MeResponse>('/auth/me'),
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),
  login: (username: string, password: string) =>
    request<{ login: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  devLogin: (login: string, role: RoleName) =>
    request<{ login: string; role: string }>('/auth/dev-login', {
      method: 'POST',
      body: JSON.stringify({ login, role }),
    }),
  listRepos: () => request<string[]>('/repos'),
  listScores: (repo: string) => request<ScoreOut[]>(`/repos/${repo}/scores`),
  myRole: (repo: string) =>
    request<{ repo: string; role: RoleName }>(`/repos/${repo}/role`),
  getSettings: (repo: string) => request<RepoSettings>(`/repos/${repo}/settings`),
  putSettings: (repo: string, body: RepoSettings) =>
    request<RepoSettings>(`/repos/${repo}/settings`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  resetSettings: (repo: string) =>
    request<RepoSettings>(`/repos/${repo}/settings`, { method: 'DELETE' }),
  getDefaultSettings: () => request<RepoSettings>('/settings/defaults'),
  putDefaultSettings: (body: RepoSettings) =>
    request<RepoSettings>('/settings/defaults', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  getMetrics: () => request<OrgMetrics>('/metrics'),
  getLlmSettings: () => request<LlmSettings>('/settings/llm'),
  putLlmSettings: (body: LlmSettingsUpdate) =>
    request<LlmSettings>('/settings/llm', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  getUiSettings: () => request<UiSettings>('/settings/ui'),
  putUiSettings: (body: UiSettings) =>
    request<UiSettings>('/settings/ui', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  submitFeedback: (scoreId: number, feedback: FeedbackValue) =>
    request<ScoreOut>(`/scores/${scoreId}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ feedback }),
    }),
  listRoles: () => request<RepoRole[]>('/admin/roles'),
  upsertRole: (body: RepoRole) =>
    request<RepoRole>('/admin/roles', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deleteRole: (userLogin: string, repo: string) =>
    request<void>(`/admin/roles/${encodeURIComponent(userLogin)}/${repo}`, {
      method: 'DELETE',
    }),
}
