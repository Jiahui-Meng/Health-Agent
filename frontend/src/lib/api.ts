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
  device_id: string
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
  }
}

export type SessionItem = {
  id: string
  device_id: string
  locale: string
  region_code: string
  latest_risk: RiskLevel
  created_at: string
  updated_at: string
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
