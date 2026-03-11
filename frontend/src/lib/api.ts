export type RiskLevel = 'low' | 'medium' | 'high' | 'emergency'

export type HealthProfile = {
  age_range?: string
  sex?: string
  conditions?: string[]
  medications?: string[]
  allergies?: string[]
  pregnancy_status?: string
  symptom_duration?: string
}

export type ChatRequest = {
  device_id?: string
  user_id?: string
  locale: string
  region_code: string
  message: string
  health_profile?: HealthProfile
  session_id?: string
}

export type ChatResponse = {
  answer: {
    summary: string
    risk_level: RiskLevel
    next_steps: string[]
    emergency_guidance?: string | null
    disclaimer: string
    stage: 'intake' | 'conclusion'
    follow_up_questions?: string[] | null
  }
  meta: {
    session_id: string
    used_context_turns: number
    model: string
    user_id?: string | null
  }
}

export type SessionItem = {
  id: string
  device_id: string
  user_id?: string | null
  locale: string
  region_code: string
  latest_risk: RiskLevel
  created_at: string
  updated_at: string
}

export type UserProfile = {
  id: string
  username: string
  locale: string
  region_code: string
  birth_year: string
  sex: string
  conditions: string[]
  medications: string[]
  allergies: string[]
  created_at: string
  updated_at: string
  last_active_at: string
}

export type UserCreateRequest = {
  username: string
  locale: string
  region_code: string
  birth_year: string
  sex: string
  conditions: string[]
  medications: string[]
  allergies: string[]
}

export type UserUpdateRequest = Partial<Omit<UserCreateRequest, 'username'>> & {
  mark_active?: boolean
}

export type GraphSummaryBundle = {
  persistent_features: Record<string, string[]>
  profile_highlights?: string[]
  recent_timeline: Array<{ node_type: string; label: string; payload: Record<string, unknown> }>
  recent_journey?: Array<{
    title: string
    detail: string
    session_id: string
    is_current_session: boolean
    sort_time: string
    severity_hint: RiskLevel | string
  }>
  risk_signals: Array<
    | string
    | {
        label: string
        risk_level: RiskLevel | string
        session_id: string
        is_current_session: boolean
        is_active: boolean
        sort_time: string
      }
  >
  summary_labels: string[]
}

export type UserGraphResponse = {
  user_id: string
  nodes: Array<{
    id: string
    node_type: string
    label: string
    payload: Record<string, unknown>
    source: string
    created_at: string
    updated_at: string
  }>
  edges: Array<{
    id: string
    from_node_id: string
    to_node_id: string
    edge_type: string
    payload: Record<string, unknown>
    created_at: string
  }>
  summary_bundle: GraphSummaryBundle
}

export type LegacyImportRequest = {
  profiles: UserCreateRequest[]
  active_username?: string
}

export type MessageItem = {
  id: number
  role: 'user' | 'assistant'
  content: string
  risk_level?: RiskLevel
  created_at: string
}

export type ModelConfigStatus = {
  configured: boolean
  base_url: string
  model_name: string
  provider_mode: 'codex_cli' | 'oauth_cli' | 'http_api'
  oauth_cli_available: boolean
  oauth_logged_in: boolean
  oauth_status_message: string
  oauth_account_id?: string | null
  mcp_available: boolean
  mcp_status_message: string
}

export type ModelConfigRequest = {
  provider_mode: 'codex_cli' | 'oauth_cli' | 'http_api'
  base_url?: string
  api_key?: string
  model_name?: string
}

export type OAuthStatus = {
  provider: string
  cli_available: boolean
  logged_in: boolean
  status_message: string
  account_id?: string | null
  mcp_available: boolean
  mcp_status_message: string
}

export type OAuthAction = {
  ok: boolean
  message: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function callApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`API ${response.status}: ${detail}`)
  }
  return response.json() as Promise<T>
}

export async function postChat(payload: ChatRequest): Promise<ChatResponse> {
  return callApi<ChatResponse>('/api/v1/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getSessions(deviceId: string): Promise<{ sessions: SessionItem[] }> {
  return callApi<{ sessions: SessionItem[] }>(`/api/v1/sessions/${deviceId}`)
}

export async function getUserSessions(userId: string): Promise<{ sessions: SessionItem[] }> {
  return callApi<{ sessions: SessionItem[] }>(`/api/v1/users/${userId}/sessions`)
}

export async function getMessages(sessionId: string): Promise<{ session_id: string; messages: MessageItem[] }> {
  return callApi<{ session_id: string; messages: MessageItem[] }>(`/api/v1/sessions/${sessionId}/messages`)
}

export async function deleteSession(sessionId: string): Promise<{ deleted: boolean; session_id: string }> {
  return callApi<{ deleted: boolean; session_id: string }>(`/api/v1/sessions/${sessionId}`, {
    method: 'DELETE',
  })
}

export async function getModelConfigStatus(): Promise<ModelConfigStatus> {
  return callApi<ModelConfigStatus>('/api/v1/model-config/status')
}

export async function saveModelConfig(payload: ModelConfigRequest): Promise<ModelConfigStatus> {
  return callApi<ModelConfigStatus>('/api/v1/model-config', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getOAuthStatus(): Promise<OAuthStatus> {
  return callApi<OAuthStatus>('/api/v1/auth/oauth/status')
}

export async function startOAuthLogin(): Promise<OAuthAction> {
  return callApi<OAuthAction>('/api/v1/auth/oauth/login/start', {
    method: 'POST',
  })
}

export async function logoutOAuth(): Promise<OAuthAction> {
  return callApi<OAuthAction>('/api/v1/auth/oauth/logout', {
    method: 'POST',
  })
}

export async function getUsers(): Promise<{ users: UserProfile[] }> {
  return callApi<{ users: UserProfile[] }>('/api/v1/users')
}

export async function createUser(payload: UserCreateRequest): Promise<UserProfile> {
  return callApi<UserProfile>('/api/v1/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateUser(userId: string, payload: UserUpdateRequest): Promise<UserProfile> {
  return callApi<UserProfile>(`/api/v1/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function exportUserReport(userId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/v1/users/${userId}/export?format=markdown`)
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`API ${response.status}: ${detail}`)
  }
  return response.blob()
}

export async function deleteUser(userId: string): Promise<{ deleted: boolean; user_id: string }> {
  return callApi<{ deleted: boolean; user_id: string }>(`/api/v1/users/${userId}`, {
    method: 'DELETE',
  })
}

export async function getUserGraph(userId: string): Promise<UserGraphResponse> {
  return callApi<UserGraphResponse>(`/api/v1/users/${userId}/graph`)
}

export async function importLegacyUsers(payload: LegacyImportRequest): Promise<{ users: UserProfile[] }> {
  return callApi<{ users: UserProfile[] }>('/api/v1/users/import-legacy', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
