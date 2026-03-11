import { FormEvent, useEffect, useMemo, useState } from 'react'
import {
  ChatResponse,
  HealthProfile,
  MessageItem,
  SessionItem,
  deleteSession,
  getOAuthStatus,
  getMessages,
  getModelConfigStatus,
  getSessions,
  logoutOAuth,
  postChat,
  saveModelConfig,
  startOAuthLogin,
} from './lib/api'

type ParsedAssistant = ChatResponse['answer']
type ClientStatus = 'sending' | 'failed'
type UIMessage = Omit<MessageItem, 'id'> & { id: number | string; client_status?: ClientStatus }

type LocalUserProfile = {
  username: string
  locale: string
  regionCode: string
  birthYear: string
  sex: string
  conditions: string[]
  medications: string[]
  allergies: string[]
}

type UserDraft = {
  username: string
  locale: string
  regionCode: string
  birthYear: string
  sex: string
  conditionsText: string
  medicationsText: string
  allergiesText: string
}

const BIGMODEL_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'
const BIGMODEL_DEFAULT_MODEL = 'glm-4.7-flash'
const OPENAI_BASE_URL = 'https://api.openai.com/v1'
const OPENAI_DEFAULT_MODEL = 'gpt-5.4'
const CODEX_MODEL_OPTIONS = [
  { value: 'gpt-5.4', label: 'gpt-5.4 (Recommended)' },
  { value: 'gpt-5.3-codex', label: 'gpt-5.3-codex' },
  { value: 'gpt-5.3-codex-spark', label: 'gpt-5.3-codex-spark (ChatGPT Pro preview)' },
  { value: 'gpt-5.1-codex-max', label: 'gpt-5.1-codex-max' },
] as const
const USER_PROFILES_KEY = 'health_agent_user_profiles'
const ACTIVE_USER_KEY = 'health_agent_active_user'

const UI_TEXT = {
  zh: {
    heroSubtitle: '专注健康分诊与咨询的 AI 助手，内置严格安全防护与长期上下文记忆。',
    userProfile: '本地用户档案',
    currentUser: '当前用户',
    addUser: '新增用户',
    editUser: '编辑用户',
    noUserHint: '请先创建一个本地用户档案。',
    locale: '语言',
    localeZh: '中文 (zh-CN)',
    localeEn: '英文 (en-US)',
    region: '地区',
    birthYear: '出生年份',
    birthYearPlaceholder: '例如 1990',
    sex: '性别',
    sexPlaceholder: '例如 女',
    conditions: '既往病史（逗号分隔）',
    conditionsPlaceholder: '哮喘, 糖尿病',
    medications: '当前用药（逗号分隔）',
    medicationsPlaceholder: '二甲双胍',
    allergies: '过敏史（逗号分隔）',
    allergiesPlaceholder: '青霉素',
    username: '用户名',
    usernamePlaceholder: '例如 张三',
    modelApi: '模型 API',
    hide: '收起',
    edit: '编辑',
    statusLabel: '状态',
    statusConfigured: '已配置',
    statusNotConfigured: '未配置',
    baseUrl: 'Base URL',
    modelName: '模型名称',
    codexModel: 'Codex 模型',
    apiKeyToken: 'API Key (Token)',
    providerMode: '接入方式',
    providerOAuth: 'Codex CLI (via MCP tools)',
    providerHttp: 'HTTP API Key',
    oauthLogin: '登录 Codex',
    oauthLogout: '退出登录',
    oauthRefresh: '刷新状态',
    oauthStatus: 'Codex 状态',
    oauthNeedLogin: '请先完成 Codex 登录，并确保 MCP 可用。',
    apiKeyPlaceholder: '输入你的 API Token',
    saveApiConfig: '保存 API 配置',
    saving: '保存中...',
    fillApiError: '请完整填写 Base URL、模型名称和 API Key。',
    saveUser: '保存用户',
    userModalTitle: '创建本地用户',
    userModalEditTitle: '编辑本地用户',
    userModalDesc: '仅本地保存，不需要登录。你可以创建多个用户并切换。',
    usernameRequired: '用户名不能为空。',
    usernameDuplicated: '用户名已存在，请换一个。',
    startPrompt: '请先描述你的症状、持续时间和变化情况。',
    composerPlaceholder: '请描述症状、出现时间、变化趋势，以及你最担心的问题...',
    thinking: '思考中...',
    send: '发送',
    sendingTag: '发送中...',
    failedTag: '发送失败',
    history: '历史会话',
    newSession: '新建会话',
    delete: '删除',
    modalTitle: '连接你的大模型',
    modalDesc: '默认使用 Codex CLI + MCP tools。请先完成 Codex 登录；如需回退也可切换到 HTTP API。',
    mcpStatus: 'MCP 状态',
    saveAndStart: '保存并开始',
    intakeTag: '问诊中',
    intakeHint: '请按下面问题补充信息，系统会在 3-5 轮后给出总结建议。',
    risk: {
      low: '低风险',
      medium: '中风险',
      high: '高风险',
      emergency: '紧急',
    },
  },
  en: {
    heroSubtitle: 'AI health triage assistant with strict safety guardrails and longitudinal context memory.',
    userProfile: 'Local User Profile',
    currentUser: 'Current User',
    addUser: 'Add User',
    editUser: 'Edit User',
    noUserHint: 'Create a local user profile first.',
    locale: 'Locale',
    localeZh: 'Chinese (zh-CN)',
    localeEn: 'English (en-US)',
    region: 'Region',
    birthYear: 'Birth Year',
    birthYearPlaceholder: 'e.g. 1990',
    sex: 'Sex',
    sexPlaceholder: 'e.g. female',
    conditions: 'Conditions (comma)',
    conditionsPlaceholder: 'asthma, diabetes',
    medications: 'Medications (comma)',
    medicationsPlaceholder: 'metformin',
    allergies: 'Allergies (comma)',
    allergiesPlaceholder: 'penicillin',
    username: 'Username',
    usernamePlaceholder: 'e.g. Alice',
    modelApi: 'Model API',
    hide: 'Hide',
    edit: 'Edit',
    statusLabel: 'Status',
    statusConfigured: 'Configured',
    statusNotConfigured: 'Not configured',
    baseUrl: 'Base URL',
    modelName: 'Model Name',
    codexModel: 'Codex Model',
    apiKeyToken: 'API Key (Token)',
    providerMode: 'Provider',
    providerOAuth: 'Codex CLI (via MCP tools)',
    providerHttp: 'HTTP API Key',
    oauthLogin: 'Login Codex',
    oauthLogout: 'Logout',
    oauthRefresh: 'Refresh Status',
    oauthStatus: 'Codex Status',
    oauthNeedLogin: 'Please login with Codex first and ensure MCP is available.',
    apiKeyPlaceholder: 'your-api-token',
    saveApiConfig: 'Save API Config',
    saving: 'Saving...',
    fillApiError: 'Please provide Base URL, model name, and API key.',
    saveUser: 'Save User',
    userModalTitle: 'Create Local User',
    userModalEditTitle: 'Edit Local User',
    userModalDesc: 'Stored locally only. No login required. You can create and switch multiple users.',
    usernameRequired: 'Username is required.',
    usernameDuplicated: 'Username already exists.',
    startPrompt: 'Start by describing your symptoms and concerns.',
    composerPlaceholder: 'Describe symptoms, timeline, and what has changed...',
    thinking: 'Thinking...',
    send: 'Send',
    sendingTag: 'Sending...',
    failedTag: 'Failed to send',
    history: 'History',
    newSession: 'New Session',
    delete: 'Delete',
    modalTitle: 'Connect Your LLM',
    modalDesc: 'Default mode is Codex CLI with MCP tools. Login with Codex first, or switch to HTTP API as fallback.',
    mcpStatus: 'MCP Status',
    saveAndStart: 'Save and Start',
    intakeTag: 'Intake',
    intakeHint: 'Please answer the questions below. A conclusion is generated after 3-5 rounds.',
    risk: {
      low: 'LOW',
      medium: 'MEDIUM',
      high: 'HIGH',
      emergency: 'EMERGENCY',
    },
  },
} as const

function parseAssistant(content: string): ParsedAssistant | null {
  try {
    const parsed = JSON.parse(content)
    if (!parsed.summary || !parsed.risk_level) {
      return null
    }
    return parsed as ParsedAssistant
  } catch {
    return null
  }
}

function toList(raw: string): string[] {
  return raw
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function toCsv(values: string[]): string {
  return values.join(', ')
}

function normalizeUsername(name: string): string {
  return name.trim().replace(/\s+/g, ' ')
}

function buildDeviceId(username: string): string {
  const slug = username
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return `device_${slug || 'local_user'}`
}

function loadProfilesFromStorage(): { profiles: LocalUserProfile[]; activeUsername: string } {
  try {
    const rawProfiles = localStorage.getItem(USER_PROFILES_KEY)
    const rawActive = localStorage.getItem(ACTIVE_USER_KEY) || ''
    const parsed = rawProfiles ? (JSON.parse(rawProfiles) as Array<Record<string, unknown>>) : []
    const profiles = Array.isArray(parsed)
      ? parsed
          .map((item) => {
            const username = String(item.username || '').trim()
            if (!username) return null
            return {
              username,
              locale: String(item.locale || 'zh-CN'),
              regionCode: String(item.regionCode || 'HK'),
              birthYear: String(item.birthYear || ''),
              sex: String(item.sex || ''),
              conditions: Array.isArray(item.conditions) ? item.conditions.map((v) => String(v)) : [],
              medications: Array.isArray(item.medications) ? item.medications.map((v) => String(v)) : [],
              allergies: Array.isArray(item.allergies) ? item.allergies.map((v) => String(v)) : [],
            } satisfies LocalUserProfile
          })
          .filter((item): item is LocalUserProfile => item !== null)
      : []
    return { profiles, activeUsername: rawActive }
  } catch {
    return { profiles: [], activeUsername: '' }
  }
}

function blankDraft(): UserDraft {
  return {
    username: '',
    locale: 'zh-CN',
    regionCode: 'HK',
    birthYear: '',
    sex: '',
    conditionsText: '',
    medicationsText: '',
    allergiesText: '',
  }
}

function profileToDraft(profile: LocalUserProfile): UserDraft {
  return {
    username: profile.username,
    locale: profile.locale,
    regionCode: profile.regionCode,
    birthYear: profile.birthYear,
    sex: profile.sex,
    conditionsText: toCsv(profile.conditions),
    medicationsText: toCsv(profile.medications),
    allergiesText: toCsv(profile.allergies),
  }
}

function draftToProfile(draft: UserDraft): LocalUserProfile {
  return {
    username: normalizeUsername(draft.username),
    locale: draft.locale,
    regionCode: draft.regionCode,
    birthYear: draft.birthYear.trim(),
    sex: draft.sex.trim(),
    conditions: toList(draft.conditionsText),
    medications: toList(draft.medicationsText),
    allergies: toList(draft.allergiesText),
  }
}

export default function App() {
  const [sessionId, setSessionId] = useState<string | undefined>(undefined)

  const [profiles, setProfiles] = useState<LocalUserProfile[]>([])
  const [activeUsername, setActiveUsername] = useState('')
  const [showUserModal, setShowUserModal] = useState(false)
  const [isEditingUser, setIsEditingUser] = useState(false)
  const [userDraft, setUserDraft] = useState<UserDraft>(blankDraft())
  const [userError, setUserError] = useState('')

  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [checkingModelConfig, setCheckingModelConfig] = useState(true)

  const [modelConfigured, setModelConfigured] = useState(false)
  const [showModelConfigModal, setShowModelConfigModal] = useState(false)
  const [showApiConfigForm, setShowApiConfigForm] = useState(false)

  const [providerMode, setProviderMode] = useState<'codex_cli' | 'http_api'>('codex_cli')
  const [modelBaseUrl, setModelBaseUrl] = useState(OPENAI_BASE_URL)
  const [modelName, setModelName] = useState(OPENAI_DEFAULT_MODEL)
  const [modelApiKey, setModelApiKey] = useState('')
  const [modelConfigError, setModelConfigError] = useState('')
  const [modelConfigSaving, setModelConfigSaving] = useState(false)
  const [oauthCliAvailable, setOauthCliAvailable] = useState(false)
  const [oauthLoggedIn, setOauthLoggedIn] = useState(false)
  const [oauthStatusMessage, setOauthStatusMessage] = useState('')
  const [oauthAccountId, setOauthAccountId] = useState<string | null>(null)
  const [mcpAvailable, setMcpAvailable] = useState(false)
  const [mcpStatusMessage, setMcpStatusMessage] = useState('')
  const [oauthActionLoading, setOauthActionLoading] = useState(false)

  const activeProfile = useMemo(
    () => profiles.find((profile) => profile.username === activeUsername) || null,
    [profiles, activeUsername],
  )

  const activeLocale = activeProfile?.locale || 'zh-CN'
  const displayLocale = showUserModal ? userDraft.locale || activeLocale : activeLocale
  const regionCode = activeProfile?.regionCode || 'HK'
  const isZh = displayLocale.startsWith('zh')
  const t = isZh ? UI_TEXT.zh : UI_TEXT.en

  const deviceId = useMemo(() => (activeProfile ? buildDeviceId(activeProfile.username) : ''), [activeProfile])

  const profile = useMemo<HealthProfile>(
    () => ({
      age_range: activeProfile?.birthYear
        ? `${activeLocale.startsWith('zh') ? '出生年份' : 'Birth year'}: ${activeProfile.birthYear}`
        : undefined,
      sex: activeProfile?.sex || undefined,
      conditions: activeProfile?.conditions || [],
      medications: activeProfile?.medications || [],
      allergies: activeProfile?.allergies || [],
    }),
    [activeProfile, activeLocale],
  )

  useEffect(() => {
    const { profiles: storedProfiles, activeUsername: storedActive } = loadProfilesFromStorage()
    setProfiles(storedProfiles)

    if (storedProfiles.length > 0) {
      const exists = storedProfiles.some((p) => p.username === storedActive)
      setActiveUsername(exists ? storedActive : storedProfiles[0].username)
      setShowUserModal(false)
    } else {
      setShowUserModal(true)
      setIsEditingUser(false)
      setUserDraft(blankDraft())
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(USER_PROFILES_KEY, JSON.stringify(profiles))
  }, [profiles])

  useEffect(() => {
    if (activeUsername) {
      localStorage.setItem(ACTIVE_USER_KEY, activeUsername)
    }
  }, [activeUsername])

  useEffect(() => {
    async function bootstrapModelConfig() {
      setCheckingModelConfig(true)
      try {
        const status = await getModelConfigStatus()
        const nextProvider = status.provider_mode === 'http_api' ? 'http_api' : 'codex_cli'
        setProviderMode(nextProvider)
        setModelBaseUrl(status.base_url || OPENAI_BASE_URL)
        setModelName(status.model_name || OPENAI_DEFAULT_MODEL)
        setModelConfigured(status.configured)
        setOauthCliAvailable(status.oauth_cli_available)
        setOauthLoggedIn(status.oauth_logged_in)
        setOauthStatusMessage(status.oauth_status_message || '')
        setOauthAccountId(status.oauth_account_id || null)
        setMcpAvailable(status.mcp_available)
        setMcpStatusMessage(status.mcp_status_message || '')
        setShowModelConfigModal(!status.configured)
        setShowApiConfigForm(!status.configured)
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setCheckingModelConfig(false)
      }
    }

    bootstrapModelConfig().catch((e) => setError((e as Error).message))
  }, [])

  useEffect(() => {
    async function syncSessions() {
      if (!modelConfigured || !deviceId) {
        setSessions([])
        setMessages([])
        setSessionId(undefined)
        return
      }
      try {
        const data = await getSessions(deviceId)
        setSessions(data.sessions)
      } catch (e) {
        setError((e as Error).message)
      }
    }

    syncSessions().catch((e) => setError((e as Error).message))
  }, [modelConfigured, deviceId])

  async function refreshSessions() {
    if (!deviceId) {
      setSessions([])
      return
    }
    const data = await getSessions(deviceId)
    setSessions(data.sessions)
  }

  async function loadMessages(targetSessionId: string) {
    const data = await getMessages(targetSessionId)
    setMessages(data.messages.map((msg) => ({ ...msg })))
    setSessionId(targetSessionId)
  }

  async function refreshOAuthStatus() {
    const status = await getOAuthStatus()
    setOauthCliAvailable(status.cli_available)
    setOauthLoggedIn(status.logged_in)
    setOauthStatusMessage(status.status_message)
    setOauthAccountId(status.account_id || null)
    setMcpAvailable(status.mcp_available)
    setMcpStatusMessage(status.mcp_status_message || '')
    return status
  }

  async function onOAuthLogin() {
    setModelConfigError('')
    setOauthActionLoading(true)
    try {
      const result = await startOAuthLogin()
      setOauthStatusMessage(result.message || oauthStatusMessage)
      await refreshOAuthStatus()
      const cfg = await getModelConfigStatus()
      setModelConfigured(cfg.configured)
      setShowModelConfigModal(!cfg.configured)
    } catch (e) {
      setModelConfigError((e as Error).message)
    } finally {
      setOauthActionLoading(false)
    }
  }

  async function onOAuthLogout() {
    setModelConfigError('')
    setOauthActionLoading(true)
    try {
      const result = await logoutOAuth()
      setOauthStatusMessage(result.message || oauthStatusMessage)
      const status = await refreshOAuthStatus()
      setModelConfigured(status.logged_in && status.mcp_available && providerMode === 'codex_cli')
    } catch (e) {
      setModelConfigError((e as Error).message)
    } finally {
      setOauthActionLoading(false)
    }
  }

  function openCreateUserModal() {
    setIsEditingUser(false)
    setUserError('')
    setUserDraft(blankDraft())
    setShowUserModal(true)
  }

  function openEditUserModal() {
    if (!activeProfile) return
    setIsEditingUser(true)
    setUserError('')
    setUserDraft(profileToDraft(activeProfile))
    setShowUserModal(true)
  }

  async function onSaveUser(event: FormEvent) {
    event.preventDefault()
    const normalized = normalizeUsername(userDraft.username)
    if (!normalized) {
      setUserError(t.usernameRequired)
      return
    }

    const duplicate = profiles.some(
      (p) => p.username.toLowerCase() === normalized.toLowerCase() && p.username !== activeUsername,
    )
    if (duplicate) {
      setUserError(t.usernameDuplicated)
      return
    }

    const savedProfile = draftToProfile({ ...userDraft, username: normalized })

    if (isEditingUser && activeProfile) {
      setProfiles((prev) => prev.map((p) => (p.username === activeProfile.username ? savedProfile : p)))
    } else {
      setProfiles((prev) => [...prev, savedProfile])
    }

    setActiveUsername(savedProfile.username)
    setShowUserModal(false)
    setUserError('')
    setMessages([])
    setSessionId(undefined)
    setError('')

    if (modelConfigured) {
      try {
        await refreshSessions()
      } catch (e) {
        setError((e as Error).message)
      }
    }
  }

  async function submitModelConfig() {
    if (providerMode === 'http_api' && (!modelBaseUrl.trim() || !modelName.trim())) {
      setModelConfigError(t.fillApiError)
      return false
    }
    if (providerMode === 'codex_cli' && !modelName.trim()) {
      setModelConfigError(t.fillApiError)
      return false
    }
    if (providerMode === 'http_api' && !modelApiKey.trim()) {
      setModelConfigError(t.fillApiError)
      return false
    }
    if (providerMode === 'codex_cli' && (!oauthLoggedIn || !mcpAvailable)) {
      setModelConfigError(t.oauthNeedLogin)
      return false
    }

    setModelConfigError('')
    setModelConfigSaving(true)
    try {
      const status = await saveModelConfig({
        provider_mode: providerMode,
        base_url: providerMode === 'http_api' ? modelBaseUrl.trim() : '',
        model_name: modelName.trim(),
        api_key: providerMode === 'http_api' ? modelApiKey.trim() : '',
      })
      setModelConfigured(status.configured)
      setShowModelConfigModal(!status.configured)
      setProviderMode(status.provider_mode === 'http_api' ? 'http_api' : 'codex_cli')
      setModelBaseUrl(status.base_url || OPENAI_BASE_URL)
      setModelName(status.model_name || OPENAI_DEFAULT_MODEL)
      setModelApiKey('')
      if (status.configured) {
        setShowApiConfigForm(false)
        await refreshSessions()
      }
      return status.configured
    } catch (e) {
      setModelConfigError((e as Error).message)
      return false
    } finally {
      setModelConfigSaving(false)
    }
  }

  async function onSaveModelConfig(event: FormEvent) {
    event.preventDefault()
    await submitModelConfig()
  }

  async function onSend(event: FormEvent) {
    event.preventDefault()
    const userText = input.trim()
    if (!userText || !modelConfigured || !activeProfile || !deviceId) return

    setError('')
    const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const optimisticMessage: UIMessage = {
      id: tempId,
      role: 'user',
      content: userText,
      created_at: new Date().toISOString(),
      client_status: 'sending',
    }
    setMessages((prev) => [...prev, optimisticMessage])
    setInput('')
    setLoading(true)
    try {
      const res = await postChat({
        device_id: deviceId,
        locale: activeLocale,
        region_code: regionCode,
        message: userText,
        health_profile: profile,
        session_id: sessionId,
      })

      const nextSession = res.meta.session_id
      await loadMessages(nextSession)
      await refreshSessions()
    } catch (e) {
      setMessages((prev) =>
        prev.map((msg) => (msg.id === tempId ? { ...msg, client_status: 'failed' } : msg)),
      )
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function onDelete(targetSessionId: string) {
    setError('')
    try {
      await deleteSession(targetSessionId)
      if (sessionId === targetSessionId) {
        setSessionId(undefined)
        setMessages([])
      }
      await refreshSessions()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const riskColor: Record<string, string> = {
    low: 'var(--risk-low)',
    medium: 'var(--risk-medium)',
    high: 'var(--risk-high)',
    emergency: 'var(--risk-emergency)',
  }

  return (
    <div className="page">
      <div className="aurora" />
      <header className="hero">
        <h1>Health Agent</h1>
        <p>{t.heroSubtitle}</p>
      </header>

      <main className="layout">
        <aside className="panel left-panel">
          <h2>{t.userProfile}</h2>

          {activeProfile ? (
            <div className="grid">
              <label>
                {t.currentUser}
                <select
                  value={activeUsername}
                  onChange={(e) => {
                    const next = e.target.value
                    setActiveUsername(next)
                    setSessionId(undefined)
                    setMessages([])
                    setError('')
                  }}
                >
                  {profiles.map((profileItem) => (
                    <option key={profileItem.username} value={profileItem.username}>
                      {profileItem.username}
                    </option>
                  ))}
                </select>
              </label>

              <div className="user-actions">
                <button type="button" onClick={openCreateUserModal}>
                  {t.addUser}
                </button>
                <button type="button" onClick={openEditUserModal}>
                  {t.editUser}
                </button>
              </div>

              <div className="profile-summary">
                <p>
                  {t.locale}: {activeProfile.locale}
                </p>
                <p>
                  {t.region}: {activeProfile.regionCode}
                </p>
                {activeProfile.birthYear && (
                  <p>
                    {t.birthYear}: {activeProfile.birthYear}
                  </p>
                )}
                {activeProfile.sex && (
                  <p>
                    {t.sex}: {activeProfile.sex}
                  </p>
                )}
                {activeProfile.conditions.length > 0 && (
                  <p>
                    {t.conditions}: {toCsv(activeProfile.conditions)}
                  </p>
                )}
                {activeProfile.medications.length > 0 && (
                  <p>
                    {t.medications}: {toCsv(activeProfile.medications)}
                  </p>
                )}
                {activeProfile.allergies.length > 0 && (
                  <p>
                    {t.allergies}: {toCsv(activeProfile.allergies)}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <p className="placeholder">{t.noUserHint}</p>
          )}

          <section className="api-config-card">
            <div className="api-config-head">
              <h3>{t.modelApi}</h3>
              <button
                type="button"
                className="api-toggle"
                onClick={() => setShowApiConfigForm((current) => !current)}
              >
                {showApiConfigForm ? t.hide : t.edit}
              </button>
            </div>
            <p className="api-status">
              {t.statusLabel}: {modelConfigured ? t.statusConfigured : t.statusNotConfigured}
            </p>

            {showApiConfigForm && (
              <form
                className="grid api-form"
                onSubmit={async (event) => {
                  event.preventDefault()
                  await submitModelConfig()
                }}
              >
                <label>
                  {t.providerMode}
                  <select
                    value={providerMode}
                    onChange={(e) => {
                      const next = e.target.value as 'codex_cli' | 'http_api'
                      setProviderMode(next)
                      if (next === 'codex_cli') {
                        setModelBaseUrl(OPENAI_BASE_URL)
                        setModelName(OPENAI_DEFAULT_MODEL)
                      } else {
                        setModelBaseUrl(BIGMODEL_BASE_URL)
                        setModelName(BIGMODEL_DEFAULT_MODEL)
                      }
                    }}
                  >
                    <option value="codex_cli">{t.providerOAuth}</option>
                    <option value="http_api">{t.providerHttp}</option>
                  </select>
                </label>
                {providerMode === 'http_api' && (
                  <label>
                    {t.baseUrl}
                    <input
                      value={modelBaseUrl}
                      onChange={(e) => setModelBaseUrl(e.target.value)}
                      placeholder={BIGMODEL_BASE_URL}
                    />
                  </label>
                )}
                {providerMode === 'codex_cli' ? (
                  <label>
                    {t.codexModel}
                    <select value={modelName} onChange={(e) => setModelName(e.target.value)}>
                      {CODEX_MODEL_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <label>
                    {t.modelName}
                    <input
                      value={modelName}
                      onChange={(e) => setModelName(e.target.value)}
                      placeholder={BIGMODEL_DEFAULT_MODEL}
                    />
                  </label>
                )}
                {providerMode === 'http_api' && (
                  <label>
                    {t.apiKeyToken}
                    <input
                      type="password"
                      value={modelApiKey}
                      onChange={(e) => setModelApiKey(e.target.value)}
                      placeholder={t.apiKeyPlaceholder}
                    />
                  </label>
                )}
                {providerMode === 'codex_cli' && (
                  <div className="profile-summary">
                      <p>
                        {t.oauthStatus}: {oauthStatusMessage || '-'}
                      </p>
                      <p>CLI: {oauthCliAvailable ? 'available' : 'unavailable'}</p>
                      <p>
                        {t.mcpStatus}: {mcpAvailable ? 'available' : 'unavailable'}
                        {mcpStatusMessage ? ` (${mcpStatusMessage})` : ''}
                      </p>
                      {oauthAccountId && <p>Account: {oauthAccountId}</p>}
                    <div className="user-actions">
                      <button type="button" onClick={onOAuthLogin} disabled={oauthActionLoading}>
                        {t.oauthLogin}
                      </button>
                      <button type="button" onClick={onOAuthLogout} disabled={oauthActionLoading}>
                        {t.oauthLogout}
                      </button>
                    </div>
                    <button type="button" onClick={refreshOAuthStatus} disabled={oauthActionLoading}>
                      {t.oauthRefresh}
                    </button>
                  </div>
                )}

                <button type="submit" disabled={modelConfigSaving}>
                  {modelConfigSaving ? t.saving : t.saveApiConfig}
                </button>
              </form>
            )}
            {modelConfigError && <p className="error">{modelConfigError}</p>}
          </section>
        </aside>

        <section className="panel chat-panel">
          <div className="messages">
            {messages.length === 0 && <p className="placeholder">{t.startPrompt}</p>}
            {messages.map((msg) => {
              const parsed = msg.role === 'assistant' ? parseAssistant(msg.content) : null
              return (
                <article
                  key={msg.id}
                  className={`bubble ${msg.role}${msg.client_status ? ` status-${msg.client_status}` : ''}`}
                >
                  {msg.role === 'user' && (
                    <>
                      <p>{msg.content}</p>
                      {msg.client_status === 'sending' && <p className="bubble-meta">{t.sendingTag}</p>}
                      {msg.client_status === 'failed' && <p className="bubble-meta failed">{t.failedTag}</p>}
                    </>
                  )}
                  {msg.role === 'assistant' && parsed && (
                    <div className="assistant-card">
                      {parsed.stage === 'intake' ? (
                        <>
                          <div className="risk-tag intake-tag">{t.intakeTag}</div>
                          <h3>{parsed.summary}</h3>
                          <p className="intake-hint">{t.intakeHint}</p>
                          <ul>
                            {(parsed.follow_up_questions || []).map((question, i) => (
                              <li key={`${msg.id}-q-${i}`}>{question}</li>
                            ))}
                          </ul>
                        </>
                      ) : (
                        <>
                          <div className="risk-tag" style={{ background: riskColor[parsed.risk_level] || '#495057' }}>
                            {t.risk[parsed.risk_level]}
                          </div>
                          <h3>{parsed.summary}</h3>
                          <ul>
                            {parsed.next_steps.map((step, i) => (
                              <li key={`${msg.id}-${i}`}>{step}</li>
                            ))}
                          </ul>
                          {parsed.emergency_guidance && <p className="emergency">{parsed.emergency_guidance}</p>}
                        </>
                      )}
                      <p className="disclaimer">{parsed.disclaimer}</p>
                    </div>
                  )}
                  {msg.role === 'assistant' && !parsed && <p>{msg.content}</p>}
                </article>
              )
            })}
          </div>

          <form onSubmit={onSend} className="composer">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t.composerPlaceholder}
              rows={4}
              disabled={!modelConfigured || checkingModelConfig || !activeProfile}
            />
            <button type="submit" disabled={loading || !modelConfigured || checkingModelConfig || !activeProfile}>
              {loading ? t.thinking : t.send}
            </button>
          </form>
          {error && <p className="error">{error}</p>}
        </section>

        <aside className="panel session-panel">
          <h2>{t.history}</h2>
          <button
            className="new-session"
            onClick={() => {
              setSessionId(undefined)
              setMessages([])
            }}
          >
            {t.newSession}
          </button>
          <div className="session-list">
            {sessions.map((session) => (
              <div key={session.id} className={`session-item ${session.id === sessionId ? 'active' : ''}`}>
                <button onClick={() => loadMessages(session.id)}>
                  <span>{new Date(session.updated_at).toLocaleString(activeLocale)}</span>
                  <strong>{session.latest_risk.toUpperCase()}</strong>
                </button>
                <button className="delete" onClick={() => onDelete(session.id)}>
                  {t.delete}
                </button>
              </div>
            ))}
          </div>
        </aside>
      </main>

      {showUserModal && (
        <div className="modal-backdrop">
          <section className="modal">
            <h2>{isEditingUser ? t.userModalEditTitle : t.userModalTitle}</h2>
            <p>{t.userModalDesc}</p>
            <form onSubmit={onSaveUser} className="grid">
              <label>
                {t.username}
                <input
                  value={userDraft.username}
                  onChange={(e) => setUserDraft((prev) => ({ ...prev, username: e.target.value }))}
                  placeholder={t.usernamePlaceholder}
                  disabled={isEditingUser}
                />
              </label>
              <label>
                {t.locale}
                <select
                  value={userDraft.locale}
                  onChange={(e) => setUserDraft((prev) => ({ ...prev, locale: e.target.value }))}
                >
                  <option value="zh-CN">{t.localeZh}</option>
                  <option value="en-US">{t.localeEn}</option>
                </select>
              </label>
              <label>
                {t.region}
                <select
                  value={userDraft.regionCode}
                  onChange={(e) => setUserDraft((prev) => ({ ...prev, regionCode: e.target.value }))}
                >
                  <option value="HK">HK</option>
                  <option value="US">US</option>
                  <option value="CN">CN</option>
                  <option value="UK">UK</option>
                  <option value="JP">JP</option>
                </select>
              </label>
              <label>
                {t.birthYear}
                <input
                  value={userDraft.birthYear}
                  onChange={(e) => setUserDraft((prev) => ({ ...prev, birthYear: e.target.value }))}
                  placeholder={t.birthYearPlaceholder}
                />
              </label>
              <label>
                {t.sex}
                <input
                  value={userDraft.sex}
                  onChange={(e) => setUserDraft((prev) => ({ ...prev, sex: e.target.value }))}
                  placeholder={t.sexPlaceholder}
                />
              </label>
              <label>
                {t.conditions}
                <input
                  value={userDraft.conditionsText}
                  onChange={(e) => setUserDraft((prev) => ({ ...prev, conditionsText: e.target.value }))}
                  placeholder={t.conditionsPlaceholder}
                />
              </label>
              <label>
                {t.medications}
                <input
                  value={userDraft.medicationsText}
                  onChange={(e) => setUserDraft((prev) => ({ ...prev, medicationsText: e.target.value }))}
                  placeholder={t.medicationsPlaceholder}
                />
              </label>
              <label>
                {t.allergies}
                <input
                  value={userDraft.allergiesText}
                  onChange={(e) => setUserDraft((prev) => ({ ...prev, allergiesText: e.target.value }))}
                  placeholder={t.allergiesPlaceholder}
                />
              </label>
              <button type="submit">{t.saveUser}</button>
            </form>
            {userError && <p className="error">{userError}</p>}
          </section>
        </div>
      )}

      {showModelConfigModal && !showUserModal && (
        <div className="modal-backdrop">
          <section className="modal">
            <h2>{t.modalTitle}</h2>
            <p>{t.modalDesc}</p>
            <form onSubmit={onSaveModelConfig} className="grid">
                <label>
                  {t.providerMode}
                  <select
                    value={providerMode}
                    onChange={(e) => {
                      const next = e.target.value as 'codex_cli' | 'http_api'
                      setProviderMode(next)
                      if (next === 'codex_cli') {
                        setModelBaseUrl(OPENAI_BASE_URL)
                        setModelName(OPENAI_DEFAULT_MODEL)
                      } else {
                        setModelBaseUrl(BIGMODEL_BASE_URL)
                        setModelName(BIGMODEL_DEFAULT_MODEL)
                      }
                  }}
                >
                  <option value="codex_cli">{t.providerOAuth}</option>
                  <option value="http_api">{t.providerHttp}</option>
                </select>
              </label>
                {providerMode === 'http_api' && (
                  <label>
                    {t.baseUrl}
                    <input
                      value={modelBaseUrl}
                      onChange={(e) => setModelBaseUrl(e.target.value)}
                      placeholder={BIGMODEL_BASE_URL}
                    />
                  </label>
                )}
                {providerMode === 'codex_cli' ? (
                  <label>
                    {t.codexModel}
                    <select value={modelName} onChange={(e) => setModelName(e.target.value)}>
                      {CODEX_MODEL_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <label>
                    {t.modelName}
                    <input
                      value={modelName}
                      onChange={(e) => setModelName(e.target.value)}
                      placeholder={BIGMODEL_DEFAULT_MODEL}
                    />
                  </label>
                )}
              {providerMode === 'http_api' && (
                <label>
                  {t.apiKeyToken}
                  <input
                    type="password"
                    value={modelApiKey}
                    onChange={(e) => setModelApiKey(e.target.value)}
                    placeholder={t.apiKeyPlaceholder}
                  />
                </label>
              )}
              {providerMode === 'codex_cli' && (
                <div className="profile-summary">
                    <p>
                      {t.oauthStatus}: {oauthStatusMessage || '-'}
                    </p>
                    <p>CLI: {oauthCliAvailable ? 'available' : 'unavailable'}</p>
                    <p>
                      {t.mcpStatus}: {mcpAvailable ? 'available' : 'unavailable'}
                      {mcpStatusMessage ? ` (${mcpStatusMessage})` : ''}
                    </p>
                    {oauthAccountId && <p>Account: {oauthAccountId}</p>}
                  <div className="user-actions">
                    <button type="button" onClick={onOAuthLogin} disabled={oauthActionLoading}>
                      {t.oauthLogin}
                    </button>
                    <button type="button" onClick={onOAuthLogout} disabled={oauthActionLoading}>
                      {t.oauthLogout}
                    </button>
                  </div>
                </div>
              )}

              <button type="submit" disabled={modelConfigSaving}>
                {modelConfigSaving ? t.saving : t.saveAndStart}
              </button>
            </form>
            {modelConfigError && <p className="error">{modelConfigError}</p>}
          </section>
        </div>
      )}
    </div>
  )
}
