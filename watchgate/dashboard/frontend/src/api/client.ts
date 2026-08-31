export type RoleName = 'admin_organizacion' | 'mantenedor' | 'revisor'
export type Semaforo = 'verde' | 'amarillo' | 'rojo'
export type FeedbackValue = 'correcto' | 'falso_positivo'

// "vulnerabilidad" | "malicioso" | "incertidumbre" -- ver ThreatNature en
// watchgate/core/models.py. Reglas estáticas (Semgrep/YARA) etiquetan cada
// hallazgo con esto vía el campo `finding_type` de la propia regla.
export type ThreatNature = 'vulnerabilidad' | 'malicioso' | 'incertidumbre'
export type Confidence = 'alta' | 'media' | 'baja'

export interface Finding {
  file_path: string
  line: number | null
  end_line: number | null
  rule_id: string
  message: string
  severity: string
  threat_nature: ThreatNature
}

export interface LayerResult {
  layer_name: string
  risk_score: number
  justification: string
  findings: Finding[]
  category: string | null
  confidence: Confidence | null
  skipped: boolean
  skip_reason: string | null
  // Naturaleza dominante de los hallazgos de esta capa (jerarquía
  // MALICIOUS > VULNERABILITY > UNCERTAIN).
  threat_nature: ThreatNature | null
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
  accepted_by: string | null
  accepted_at: string | null
  // Conteo de hallazgos de TODA la PR por naturaleza, p. ej.
  // { malicioso: 1, vulnerabilidad: 3, incertidumbre: 0 }.
  threat_summary: Record<string, number>
  // 'open' (por defecto) | 'closed' -- la PR se cerró/mergeó en GitHub
  // desde el último barrido (ver RepoPollingService.mark_prs_closed). El
  // análisis y su histórico se conservan igual, solo deja de contar como
  // pendiente.
  pr_state: 'open' | 'closed'
}

// Respuesta de POST /scores/{id}/accept -- además de aceptar, intenta
// mergear el PR real en GitHub (solo si el repo tiene una conexión real
// guardada y el PR es real, ver accept_score en el backend).
// merge_attempted=false: no había nada que mergear (score de ingesta
// genérica o análisis local, sin PR real) -- se comporta como antes.
export interface AcceptScoreOut extends ScoreOut {
  merge_attempted: boolean
  merged: boolean | null
  merge_message: string | null
}

export interface MeResponse {
  login: string
  is_admin: boolean
  // Auditoría: `is_admin` mezcla dos cosas distintas -- admin de la
  // propia organización e instancia completa (ver org_scope.py). Se
  // conservan por separado para poder ocultar acciones que exigen
  // superadmin de sitio (p. ej. aprobar/rechazar reglas YARA generadas)
  // aunque `is_admin` sea true por ser admin_organizacion.
  is_org_admin?: boolean
  is_site_superadmin?: boolean
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
  github_api_url?: string
  github_token_set?: boolean
  github_token_masked?: string | null
}

export interface LlmSettingsUpdate {
  provider: LlmProvider
  model: string
  base_url: string | null
  api_key?: string | null
  clear_api_key?: boolean
  monthly_budget_tokens: number | null
  max_diff_tokens: number | null
  github_api_url?: string | null
  github_token?: string | null
  clear_github_token?: boolean
}

export interface MyRepoRole {
  repo: string
  role: RoleName
}

export interface UserSettings {
  login: string
  display_name: string
  // Rol más alto agregado -- repo_roles de abajo es el desglose completo
  // (un elemento por repo), ver watchgate/dashboard/backend/db.py::get_user_settings.
  role: RoleName
  repo_roles: MyRepoRole[]
  github_api_url: string
  github_token_set: boolean
  github_token_masked?: string | null
  ui_settings?: UiSettings | null
}

export interface UserSettingsUpdate {
  display_name?: string | null
  github_api_url?: string | null
  github_token?: string | null
  clear_github_token?: boolean
  ui_settings?: UiSettings | null
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

export interface RagCorpusCase {
  id: string
  title: string
  type: 'caso_real' | 'aviso' | 'mitre_attck' | 'tecnica' | 'patron' | 'otro'
  summary: string
}

export interface RagCorpusCaseDetail extends RagCorpusCase {
  content: string
}

export interface UiSettings {
  primary_color: string
  accent_color: string
  radius: 'none' | 'sm' | 'md' | 'lg'
  font_scale: 'sm' | 'md' | 'lg'
  density: 'compact' | 'comfortable'
  default_theme: 'light' | 'dark' | 'system'
  logo_data_url: string | null
}

export interface RepoRole {
  user_login: string
  repo: string
  role: RoleName
  // 'audited' | 'managed' | null (null = repo no conectado en Auditoría
  // Externa, p. ej. llegó por ingesta directa del adaptador de CI).
  monitor_type: string | null
}

// Cuenta local (login/contraseña) del Dashboard -- distinto de RepoRole,
// que es qué puede ver/administrar una vez dentro. Un login puede tener
// roles sin cuenta local aquí (entra por GitHub/OIDC).
export interface DashboardUser {
  login: string
  display_name: string
}

export interface ApiKey {
  id: string
  name: string
  key_prefix: string
  scopes: string
  created_at: string
  expires_at: string | null
  last_used_at: string | null
  // NULL solo en claves legado creadas antes de exigir repo -- toda clave
  // NUEVA se crea siempre con un repo asignado (ver ApiKeysPage.tsx).
  monitored_repo_id: string | null
  repo_path: string | null
}

export interface CreatedApiKey extends ApiKey {
  raw_token: string
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
    // El backend normalmente responde JSON con `{"detail": "..."}`, pero un
    // proxy delante (502/504) o un error de framework puede devolver texto
    // plano o HTML -- si `JSON.parse` falla ahí, no es el error real, es solo
    // que el cuerpo no era JSON: se usa el texto crudo tal cual, no el
    // mensaje del parser (antes se filtraba a través del mismo catch que el
    // caso JSON válido y un `SyntaxError` como "Unexpected token <" se colaba
    // como si fuera el mensaje de error del backend).
    let message = detail || response.statusText
    try {
      const parsed = JSON.parse(detail) as { detail?: string }
      if (parsed.detail) message = parsed.detail
    } catch {
      // cuerpo no-JSON: se mantiene `message` tal cual.
    }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export interface AgentMetricRow {
  agent_id: string
  tokens_used: number
  analyses_count: number
  avg_score: number
}

export interface AgentUsageMetrics {
  total_tokens_used: number
  agents_count: number
  by_agent: AgentMetricRow[]
  llm_provider: string
  llm_model: string
}

export interface MonitoredRepoResponse {
  id: string
  vcs_connection_id: string | null
  repo_path: string
  monitor_type: string
  status: string
  last_scanned_at: string | null
  last_polled_at: string | null
  consecutive_errors: number
  created_at: string
}

// category: "entrypoint"|"api"|"model"|"test"|"config"|"infra"|"ui"|"util"|"docs"|"unknown"
// -- ver _FILE_SUMMARY_CATEGORIES en watchgate/core/layers/_semantic/client.py
export interface RepoGraphNode {
  file_path: string
  language: string | null
  category: string
  summary: string
  symbols: string[]
  imports: string[]
  loc: number
}

export interface RepoKnowledgeGraphModule {
  name: string
  file_count: number
  dominant_category: string
  sample_summaries: string[]
}

export interface RepoKnowledgeGraph {
  status: 'pending' | 'building' | 'ready' | 'error'
  error_message: string | null
  overview: string
  project_type: string | null
  languages: string | null
  module_breakdown: RepoKnowledgeGraphModule[]
  node_count: number
  edge_count: number
  built_at: string | null
  nodes: RepoGraphNode[]
}

export interface BlockedAuthor {
  author_login: string
  reason: string
  blocked_by: string
  blocked_at: string
}

// Bucle de retroalimentación: regla YARA propuesta por la capa semántica
// (ver core/layers/_semantic/tools.py::propose_yara_rule), pendiente de
// revisión humana antes de activarse -- nunca se activa sola.
export interface PendingYaraRule {
  id: string
  org_id: string | null
  repo: string
  pr_id: string
  rule_name: string
  category: string
  yara_source: string
  rationale: string
  status: 'pending' | 'approved' | 'rejected'
  reviewed_by: string | null
  reviewed_at: string | null
  created_at: string
}

export interface ApprovedYaraRule extends PendingYaraRule {
  // Nombres de fixture benignos que la regla, ya aprobada, coincidió --
  // aviso, no bloqueo (ver yara_review_fixtures/ en el backend).
  benign_matches: string[]
}

export const api = {
  me: () => request<MeResponse>('/auth/me'),
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),
  login: (username: string, password: string) =>
    request<{ login: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  listRepos: () => request<string[]>('/repos'),
  listScores: (repo: string) => request<ScoreOut[]>(`/repos/${repo}/scores`),
  getKnowledgeGraph: (repo: string) =>
    request<RepoKnowledgeGraph>(`/repos/${repo}/knowledge-graph`),
  rebuildKnowledgeGraph: (repo: string) =>
    request<{ enqueued: boolean; repo_path: string }>(
      `/repos/${repo}/knowledge-graph/rebuild`,
      { method: 'POST' },
    ),
  myRole: (repo: string) =>
    request<{ repo: string; role: RoleName }>(`/repos/${repo}/role`),
  listBlockedAuthors: (repo: string) =>
    request<BlockedAuthor[]>(`/repos/${repo}/blocked-authors`),
  blockAuthor: (repo: string, authorLogin: string, reason: string) =>
    request<BlockedAuthor>(`/repos/${repo}/blocked-authors`, {
      method: 'POST',
      body: JSON.stringify({ author_login: authorLogin, reason }),
    }),
  unblockAuthor: (repo: string, authorLogin: string) =>
    request<{ unblocked: string }>(
      `/repos/${repo}/blocked-authors/${encodeURIComponent(authorLogin)}`,
      { method: 'DELETE' },
    ),
  getSettings: (repo: string) => request<RepoSettings>(`/repos/${repo}/settings`),
  putSettings: (repo: string, body: RepoSettings) =>
    request<RepoSettings>(`/repos/${repo}/settings`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  resetSettings: (repo: string) =>
    request<RepoSettings>(`/repos/${repo}/settings`, { method: 'DELETE' }),
  // Acotado a UN repo (RBAC de "dueño de repo") -- distinto de `listRoles`
  // (`/admin/roles`, exige admin_organizacion y trae TODA la organización).
  listRepoRoles: (repo: string) => request<RepoRole[]>(`/repos/${repo}/roles`),
  getDefaultSettings: () => request<RepoSettings>('/settings/defaults'),
  putDefaultSettings: (body: RepoSettings) =>
    request<RepoSettings>('/settings/defaults', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  getMetrics: () => request<OrgMetrics>('/metrics'),
  getAgentUsageMetrics: () => request<AgentUsageMetrics>('/metrics/agent-usage'),
  getRagCorpus: () => request<RagCorpusCase[]>('/rag/corpus'),
  getRagCorpusCase: (id: string) =>
    request<RagCorpusCaseDetail>(`/rag/corpus/${encodeURIComponent(id)}`),
  getLlmSettings: () => request<LlmSettings>('/settings/llm'),
  putLlmSettings: (body: LlmSettingsUpdate) =>
    request<LlmSettings>('/settings/llm', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  getUserSettings: () => request<UserSettings>('/settings/user'),
  putUserSettings: (body: UserSettingsUpdate) =>
    request<UserSettings>('/settings/user', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>('/settings/user/password', {
      method: 'PUT',
      body: JSON.stringify({ current_password, new_password }),
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
  acceptScore: (scoreId: number) =>
    request<AcceptScoreOut>(`/scores/${scoreId}/accept`, { method: 'POST' }),
  listRoles: () => request<RepoRole[]>('/admin/roles'),
  // Sin `monitor_type`: es informativo, solo de lectura (se resuelve en
  // el servidor a partir de MonitoredRepo, no algo que se pueda asignar
  // aquí).
  upsertRole: (body: Pick<RepoRole, 'user_login' | 'repo' | 'role'>) =>
    request<RepoRole>('/admin/roles', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deleteRole: (userLogin: string, repo: string) =>
    request<void>(`/admin/roles/${encodeURIComponent(userLogin)}/${repo}`, {
      method: 'DELETE',
    }),
  listUsers: () => request<DashboardUser[]>('/admin/users'),
  // repo/role opcionales: si se pasan los dos, el alta asigna ese rol
  // inicial en el mismo paso (ver DashboardUserCreate en schemas.py) --
  // sin repetir el viaje aparte a la gestión de roles para el caso más
  // común (usuario nuevo con acceso a un solo repo).
  createUser: (
    login: string,
    display_name: string,
    password: string,
    repo?: string,
    role?: RoleName,
  ) =>
    request<DashboardUser>('/admin/users', {
      method: 'POST',
      body: JSON.stringify({ login, display_name, password, repo: repo || null, role: role || null }),
    }),
  deleteUser: (login: string) =>
    request<void>(`/admin/users/${encodeURIComponent(login)}`, { method: 'DELETE' }),
  listApiKeys: () => request<ApiKey[]>('/keys'),
  // `monitored_repo_id` es obligatorio -- ya no se permiten claves
  // generales de organización sin repo asignado.
  createApiKey: (name: string, monitored_repo_id: string) =>
    request<CreatedApiKey>('/keys', {
      method: 'POST',
      body: JSON.stringify({ name, monitored_repo_id }),
    }),
  deleteApiKey: (id: string) =>
    request<{ status: string; id: string }>(`/keys/${id}`, { method: 'DELETE' }),
  listExternalRepos: () => request<MonitoredRepoResponse[]>('/repos/external'),
  addExternalRepo: (repo_path: string, monitor_type: string, vcs_connection_id?: string | null) => 
    request<MonitoredRepoResponse>('/repos/external', {
      method: 'POST',
      body: JSON.stringify({ repo_path, monitor_type, vcs_connection_id }),
    }),
  getGithubAppInfo: () =>
    request<{ configured: boolean; install_url: string | null }>(
      '/repos/external/github-app',
    ),
  // Da de alta un repo de servidor Git propio (monitor_type "git_server")
  // Y una API key ya atada a él, en un solo paso -- pensado para copiar/
  // pegar directamente en el hook `pre-receive` del servidor
  // (docs/manual_git_hooks.md §6), sin pasar por la página de API Keys.
  connectGitServerRepo: (repo_path: string) =>
    request<{
      repo: MonitoredRepoResponse
      api_key: string
      key_prefix: string
      engine_api_url: string
      hook_download_url: string
    }>('/repos/external/git-server', {
      method: 'POST',
      body: JSON.stringify({ repo_path }),
    }),
  claimInstallation: (installation_id: string) =>
    request<{
      vcs_connection_id: string
      installation_id: string
      app_configured: boolean
      repos: MonitoredRepoResponse[]
    }>('/repos/external/installations/claim', {
      method: 'POST',
      body: JSON.stringify({ installation_id }),
    }),
  scanExternalRepo: (id: string, pr_number?: number | null) =>
    request<{message: string; repo_path: string; pr_number?: number; prs_enqueued?: number}>(`/repos/external/${id}/scan`, {
      method: 'POST',
      body: JSON.stringify({ pr_number: pr_number || 0 }),
    }),
  scanMainBranch: (id: string) =>
    request<{ message: string; repo_path: string; enqueued: boolean }>(
      `/repos/external/${id}/scan-main`,
      { method: 'POST' },
    ),
  updateExternalRepo: (id: string, data: { status?: string }) =>
    request<MonitoredRepoResponse>(`/repos/external/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteExternalRepo: (id: string) =>
    request<void>(`/repos/external/${id}`, { method: 'DELETE' }),
  deleteRepo: (repo: string) =>
    request<{ repo: string; scores_deleted: number; monitored_repo_deleted: boolean }>(
      `/repos/${repo}`,
      { method: 'DELETE' },
    ),
  // Bucle de retroalimentación (ver PendingYaraRule): `status` por
  // defecto en el backend es "pending" si no se pasa nada.
  listPendingYaraRules: (status?: PendingYaraRule['status']) =>
    request<PendingYaraRule[]>(
      `/admin/yara-rules${status ? `?status=${encodeURIComponent(status)}` : ''}`,
    ),
  approveYaraRule: (id: string) =>
    request<ApprovedYaraRule>(`/admin/yara-rules/${encodeURIComponent(id)}/approve`, {
      method: 'POST',
    }),
  rejectYaraRule: (id: string) =>
    request<PendingYaraRule>(`/admin/yara-rules/${encodeURIComponent(id)}/reject`, {
      method: 'POST',
    }),
}
