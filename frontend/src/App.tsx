import { FormEvent, useEffect, useMemo, useState } from 'react'
import {
  AdviceSection,
  ChatResponse,
  HealthProfile,
  MessageItem,
  SessionItem,
  UserCreateRequest,
  UserGraphResponse,
  UserProfile,
  createUser,
  deleteSession,
  exportUserReport,
  getMessages,
  getModelConfigStatus,
  getOAuthStatus,
  getUserGraph,
  getUserSessions,
  getUsers,
  importLegacyUsers,
  logoutOAuth,
  postChat,
  saveModelConfig,
  startOAuthLogin,
  updateUser,
} from './lib/api'
import UserGraphPage from './components/UserGraphPage'

type ParsedAssistant = ChatResponse['answer']
type ClientStatus = 'sending' | 'failed'
type UIMessage = Omit<MessageItem, 'id'> & { id: number | string; client_status?: ClientStatus }
type GraphJourneyCard = {
  title: string
  detail: string
  session_id: string
  is_current_session: boolean
  sort_time: string
  severity_hint: string
}
type GraphRiskCard = {
  label: string
  risk_level: string
  session_id: string
  is_current_session: boolean
  is_active: boolean
  sort_time: string
}

type AdviceSectionEntry = {
  key:
    | 'visit_guidance'
    | 'medication_guidance'
    | 'rest_guidance'
    | 'diet_guidance'
    | 'exercise_guidance'
    | 'monitoring_guidance'
  section: AdviceSection
}

type UserDraft = {
  username: string
  locale: string
  regionCode: string
  birthYear: string
  sex: 'male' | 'female' | ''
  conditionsText: string
  medicationsText: string
  allergiesText: string
}

type LegacyLocalUserProfile = {
  username: string
  locale: string
  regionCode: string
  birthYear: string
  sex: string
  conditions: string[]
  medications: string[]
  allergies: string[]
}

type NormalizedSex = 'male' | 'female' | ''

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
const LEGACY_USER_PROFILES_KEY = 'health_agent_user_profiles'
const LEGACY_ACTIVE_USER_KEY = 'health_agent_active_user'

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
    sexPlaceholder: '请选择',
    sexMale: '男 / Male',
    sexFemale: '女 / Female',
    sexRequired: '性别为必填项，未填写不能开始问诊。',
    sexMissingBeforeChat: '请先完善当前用户的性别信息，再开始问诊。',
    conditions: '既往病史（逗号分隔）',
    conditionsPlaceholder: '哮喘, 糖尿病',
    medications: '当前用药（逗号分隔）',
    medicationsPlaceholder: '二甲双胍',
    allergies: '过敏史（逗号分隔）',
    allergiesPlaceholder: '青霉素',
    username: '用户名',
    usernamePlaceholder: '例如 张三',
    modelApi: '模型 API',
    openSettings: '打开模型配置',
    exportReport: '导出报告',
    viewGraph: '查看图谱',
    exporting: '导出中...',
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
    userModalDesc: '用户与历史会话保存在本地后端数据库中，不需要登录，可创建多个本地用户并切换。',
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
    graphSummary: '健康图谱摘要',
    graphLongTerm: '长期特征',
    graphTimeline: '近期症状时间线',
    graphRisk: '风险信号',
    graphCurrent: '当前会话',
    graphHistory: '近期历史',
    graphActiveRisk: '当前重点',
    graphHistoricalRisk: '历史记录',
    graphNoLongTerm: '暂无长期健康特征',
    graphNoJourney: '暂无可展示的病程演化',
    graphNoRisk: '暂无重点风险信号',
    graphProfileHighlights: '档案概览',
    graphPageTitle: '用户健康图谱',
    graphPageSubtitle: '树状演示视图',
    graphBack: '返回聊天',
    graphFitView: '适配视图',
    graphReset: '重置',
    graphFilters: '筛选器',
    graphNodeTypes: '节点类型',
    graphSessionScope: '会话范围',
    graphRiskScope: '风险范围',
    graphSessionAll: '全部会话',
    graphSessionCurrent: '当前会话',
    graphSessionSelected: '指定会话',
    graphRiskAll: '全部风险',
    graphRiskHigh: '仅高风险/紧急',
    graphRiskHideLow: '隐藏低风险',
    graphDetails: '节点详情',
    graphNoSelection: '点击节点以查看详情',
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
    sexPlaceholder: 'Select',
    sexMale: 'Male',
    sexFemale: 'Female',
    sexRequired: 'Sex is required before chat.',
    sexMissingBeforeChat: 'Please complete the current user sex field before starting chat.',
    conditions: 'Conditions (comma)',
    conditionsPlaceholder: 'asthma, diabetes',
    medications: 'Medications (comma)',
    medicationsPlaceholder: 'metformin',
    allergies: 'Allergies (comma)',
    allergiesPlaceholder: 'penicillin',
    username: 'Username',
    usernamePlaceholder: 'e.g. Alice',
    modelApi: 'Model API',
    openSettings: 'Open model settings',
    exportReport: 'Export report',
    viewGraph: 'View Graph',
    exporting: 'Exporting...',
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
    userModalDesc: 'Users and session history are stored in the local backend database. No login required.',
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
    graphSummary: 'Health Graph Summary',
    graphLongTerm: 'Longitudinal Features',
    graphTimeline: 'Recent Symptom Timeline',
    graphRisk: 'Risk Signals',
    graphCurrent: 'Current Session',
    graphHistory: 'Recent History',
    graphActiveRisk: 'Active Focus',
    graphHistoricalRisk: 'History',
    graphNoLongTerm: 'No longitudinal features yet.',
    graphNoJourney: 'No symptom journey available yet.',
    graphNoRisk: 'No notable risk signals yet.',
    graphProfileHighlights: 'Profile Highlights',
    graphPageTitle: 'User Health Graph',
    graphPageSubtitle: 'Tree Demo View',
    graphBack: 'Back to Chat',
    graphFitView: 'Fit View',
    graphReset: 'Reset',
    graphFilters: 'Filters',
    graphNodeTypes: 'Node Types',
    graphSessionScope: 'Session Scope',
    graphRiskScope: 'Risk Scope',
    graphSessionAll: 'All Sessions',
    graphSessionCurrent: 'Current Session',
    graphSessionSelected: 'Selected Session',
    graphRiskAll: 'All Risk',
    graphRiskHigh: 'Only High / Emergency',
    graphRiskHideLow: 'Hide Low',
    graphDetails: 'Node Details',
    graphNoSelection: 'Select a node to inspect details',
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

function normalizeSexValue(value: string): NormalizedSex {
  const raw = String(value || '')
    .trim()
    .toLowerCase()
  if (raw === 'male' || raw === 'man' || raw === 'm' || raw === '男') return 'male'
  if (raw === 'female' || raw === 'woman' || raw === 'f' || raw === '女') return 'female'
  return ''
}

function formatSexLabel(value: string, locale: string, t: (typeof UI_TEXT)['zh'] | (typeof UI_TEXT)['en']) {
  const normalized = normalizeSexValue(value)
  if (normalized === 'male') return t.sexMale
  if (normalized === 'female') return t.sexFemale
  return locale.startsWith('zh') ? '未填写' : 'Not set'
}

function isRiskObject(
  item: UserGraphResponse['summary_bundle']['risk_signals'][number],
): item is Exclude<UserGraphResponse['summary_bundle']['risk_signals'][number], string> {
  return typeof item === 'object' && item !== null && 'label' in item
}

function normalizeJourney(userGraph: UserGraphResponse | null): GraphJourneyCard[] {
  const journey = userGraph?.summary_bundle.recent_journey
  if (journey && journey.length > 0) {
    return journey.map((item) => ({
      title: item.title,
      detail: item.detail,
      session_id: item.session_id,
      is_current_session: item.is_current_session,
      sort_time: item.sort_time,
      severity_hint: String(item.severity_hint || 'low'),
    }))
  }
  return (userGraph?.summary_bundle.recent_timeline || []).slice(0, 5).map((item, index) => ({
    title: item.label,
    detail: String(item.payload?.message || ''),
    session_id: String(item.payload?.session_id || ''),
    is_current_session: index === 0,
    sort_time: '',
    severity_hint: 'low',
  }))
}

function normalizeRiskSignals(userGraph: UserGraphResponse | null): GraphRiskCard[] {
  return (userGraph?.summary_bundle.risk_signals || []).map((item, index) => {
    if (isRiskObject(item)) {
      return {
        label: item.label,
        risk_level: String(item.risk_level || 'medium'),
        session_id: item.session_id,
        is_current_session: item.is_current_session,
        is_active: item.is_active,
        sort_time: item.sort_time,
      }
    }
    return {
      label: String(item),
      risk_level: 'medium',
      session_id: '',
      is_current_session: index === 0,
      is_active: index === 0,
      sort_time: '',
    }
  })
}

function getOrderedAdviceSections(parsed: ParsedAssistant): AdviceSectionEntry[] {
  const sections = parsed.advice_sections
  if (!sections) return []
  const orderedKeys = [
    'visit_guidance',
    'medication_guidance',
    'rest_guidance',
    'diet_guidance',
    'exercise_guidance',
    'monitoring_guidance',
  ] as const
  const entries = orderedKeys
    .map((key) => ({ key, section: sections[key] }))
    .filter((item) => Boolean(item.section && item.section.items?.length))
  return entries as AdviceSectionEntry[]
}

function loadLegacyProfilesFromStorage(): { profiles: LegacyLocalUserProfile[]; activeUsername: string } {
  try {
    const rawProfiles = localStorage.getItem(LEGACY_USER_PROFILES_KEY)
    const rawActive = localStorage.getItem(LEGACY_ACTIVE_USER_KEY) || ''
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
            } satisfies LegacyLocalUserProfile
          })
          .filter((item): item is LegacyLocalUserProfile => item !== null)
      : []
    return { profiles, activeUsername: rawActive }
  } catch {
    return { profiles: [], activeUsername: '' }
  }
}

function clearLegacyProfilesFromStorage() {
  localStorage.removeItem(LEGACY_USER_PROFILES_KEY)
  localStorage.removeItem(LEGACY_ACTIVE_USER_KEY)
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

function userToDraft(user: UserProfile): UserDraft {
  return {
    username: user.username,
    locale: user.locale,
    regionCode: user.region_code,
    birthYear: user.birth_year,
    sex: normalizeSexValue(user.sex),
    conditionsText: toCsv(user.conditions),
    medicationsText: toCsv(user.medications),
    allergiesText: toCsv(user.allergies),
  }
}

function draftToPayload(draft: UserDraft): UserCreateRequest {
  return {
    username: normalizeUsername(draft.username),
    locale: draft.locale,
    region_code: draft.regionCode,
    birth_year: draft.birthYear.trim(),
    sex: normalizeSexValue(draft.sex) as UserCreateRequest['sex'],
    conditions: toList(draft.conditionsText),
    medications: toList(draft.medicationsText),
    allergies: toList(draft.allergiesText),
  }
}

export default function App() {
  const [pageMode, setPageMode] = useState<'chat' | 'graph'>('chat')
  const [sessionId, setSessionId] = useState<string | undefined>(undefined)
  const [users, setUsers] = useState<UserProfile[]>([])
  const [activeUserId, setActiveUserId] = useState('')
  const [userGraph, setUserGraph] = useState<UserGraphResponse | null>(null)

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
  const [exportingReport, setExportingReport] = useState(false)

  const activeUser = useMemo(() => users.find((user) => user.id === activeUserId) || null, [users, activeUserId])
  const activeLocale = activeUser?.locale || 'zh-CN'
  const displayLocale = showUserModal ? userDraft.locale || activeLocale : activeLocale
  const regionCode = activeUser?.region_code || 'HK'
  const isZh = displayLocale.startsWith('zh')
  const t = isZh ? UI_TEXT.zh : UI_TEXT.en
  const deviceId = useMemo(() => (activeUser ? buildDeviceId(activeUser.username) : ''), [activeUser])

  const healthProfile = useMemo<HealthProfile>(
    () => ({
      age_range: activeUser?.birth_year
        ? `${activeLocale.startsWith('zh') ? '出生年份' : 'Birth year'}: ${activeUser.birth_year}`
        : undefined,
      sex: activeUser?.sex || undefined,
      conditions: activeUser?.conditions || [],
      medications: activeUser?.medications || [],
      allergies: activeUser?.allergies || [],
    }),
    [activeLocale, activeUser],
  )

  useEffect(() => {
    async function bootstrap() {
      setCheckingModelConfig(true)
      try {
        const modelStatus = await getModelConfigStatus()
        const nextProvider = modelStatus.provider_mode === 'http_api' ? 'http_api' : 'codex_cli'
        setProviderMode(nextProvider)
        setModelBaseUrl(modelStatus.base_url || OPENAI_BASE_URL)
        setModelName(modelStatus.model_name || OPENAI_DEFAULT_MODEL)
        setModelConfigured(modelStatus.configured)
        setOauthCliAvailable(modelStatus.oauth_cli_available)
        setOauthLoggedIn(modelStatus.oauth_logged_in)
        setOauthStatusMessage(modelStatus.oauth_status_message || '')
        setOauthAccountId(modelStatus.oauth_account_id || null)
        setMcpAvailable(modelStatus.mcp_available)
        setMcpStatusMessage(modelStatus.mcp_status_message || '')
        setShowModelConfigModal(!modelStatus.configured)

        let fetchedUsers = (await getUsers()).users
        let importedActiveUsername = ''
        if (fetchedUsers.length === 0) {
          const legacy = loadLegacyProfilesFromStorage()
          if (legacy.profiles.length > 0) {
            importedActiveUsername = legacy.activeUsername || ''
            fetchedUsers = (
              await importLegacyUsers({
                profiles: legacy.profiles.map((profile) => ({
                  username: profile.username,
                  locale: profile.locale,
                  region_code: profile.regionCode,
                  birth_year: profile.birthYear,
                  sex: normalizeSexValue(profile.sex) as UserCreateRequest['sex'],
                  conditions: profile.conditions,
                  medications: profile.medications,
                  allergies: profile.allergies,
                })),
                active_username: legacy.activeUsername || undefined,
              })
            ).users
            clearLegacyProfilesFromStorage()
          }
        }

        setUsers(fetchedUsers)
        if (fetchedUsers.length > 0) {
          const preferredUser =
            fetchedUsers.find((user) => user.username === importedActiveUsername) || fetchedUsers[0]
          setActiveUserId(preferredUser.id)
          setShowUserModal(false)
        } else {
          setShowUserModal(true)
          setIsEditingUser(false)
          setUserDraft(blankDraft())
        }
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setCheckingModelConfig(false)
      }
    }

    bootstrap().catch((e) => setError((e as Error).message))
  }, [])

  useEffect(() => {
    async function syncSessions() {
      if (!activeUserId) {
        setSessions([])
        setMessages([])
        setSessionId(undefined)
        return
      }
      try {
        const data = await getUserSessions(activeUserId)
        setSessions(data.sessions)
      } catch (e) {
        setError((e as Error).message)
      }
    }

    syncSessions().catch((e) => setError((e as Error).message))
  }, [activeUserId])

  useEffect(() => {
    async function syncGraph() {
      if (!activeUserId) {
        setUserGraph(null)
        return
      }
      try {
        const graph = await getUserGraph(activeUserId)
        setUserGraph(graph)
      } catch (e) {
        setError((e as Error).message)
      }
    }

    syncGraph().catch((e) => setError((e as Error).message))
  }, [activeUserId, sessionId])

  useEffect(() => {
    if (!activeUser || showUserModal) return
    if (!normalizeSexValue(activeUser.sex)) {
      setIsEditingUser(true)
      setUserError(t.sexRequired)
      setUserDraft(userToDraft(activeUser))
      setShowUserModal(true)
    }
  }, [activeUser, showUserModal, t.sexRequired])

  async function refreshUsers() {
    const data = await getUsers()
    setUsers(data.users)
    return data.users
  }

  async function refreshSessions() {
    if (!activeUserId) {
      setSessions([])
      return
    }
    const data = await getUserSessions(activeUserId)
    setSessions(data.sessions)
  }

  async function refreshGraph() {
    if (!activeUserId) {
      setUserGraph(null)
      return
    }
    const graph = await getUserGraph(activeUserId)
    setUserGraph(graph)
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
    if (!activeUser) return
    setIsEditingUser(true)
    setUserError('')
    setUserDraft(userToDraft(activeUser))
    setShowUserModal(true)
  }

  async function switchActiveUser(nextUserId: string) {
    setActiveUserId(nextUserId)
    setSessionId(undefined)
    setMessages([])
    setError('')
    try {
      await updateUser(nextUserId, { mark_active: true })
      await refreshUsers()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function onSaveUser(event: FormEvent) {
    event.preventDefault()
    const payload = draftToPayload(userDraft)
    if (!payload.username) {
      setUserError(t.usernameRequired)
      return
    }
    if (!payload.sex) {
      setUserError(t.sexRequired)
      return
    }
    try {
      let saved: UserProfile
      if (isEditingUser && activeUser) {
        saved = await updateUser(activeUser.id, {
          locale: payload.locale,
          region_code: payload.region_code,
          birth_year: payload.birth_year,
          sex: payload.sex,
          conditions: payload.conditions,
          medications: payload.medications,
          allergies: payload.allergies,
          mark_active: true,
        })
      } else {
        saved = await createUser(payload)
      }
      const latestUsers = await refreshUsers()
      const nextUser = latestUsers.find((user) => user.id === saved.id) || saved
      setActiveUserId(nextUser.id)
      setShowUserModal(false)
      setUserError('')
      setMessages([])
      setSessionId(undefined)
      setError('')
      const [nextSessions, nextGraph] = await Promise.all([getUserSessions(nextUser.id), getUserGraph(nextUser.id)])
      setSessions(nextSessions.sessions)
      setUserGraph(nextGraph)
    } catch (e) {
      const message = (e as Error).message
      setUserError(message.includes('409') ? t.usernameDuplicated : message)
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
        setShowModelConfigModal(false)
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
    if (!userText || !modelConfigured || !activeUser) return
    if (!normalizeSexValue(activeUser.sex)) {
      setError(t.sexMissingBeforeChat)
      setIsEditingUser(true)
      setUserError(t.sexRequired)
      setUserDraft(userToDraft(activeUser))
      setShowUserModal(true)
      return
    }

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
        user_id: activeUser.id,
        device_id: deviceId,
        locale: activeUser.locale,
        region_code: activeUser.region_code,
        message: userText,
        health_profile: healthProfile,
        session_id: sessionId,
      })
      const nextSession = res.meta.session_id
      await loadMessages(nextSession)
      await refreshSessions()
      await refreshGraph()
      await refreshUsers()
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
      await refreshGraph()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function onExportReport() {
    if (!activeUser) return
    setError('')
    setExportingReport(true)
    try {
      const blob = await exportUserReport(activeUser.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      const safeName = activeUser.username.trim().replace(/\s+/g, '_') || 'user'
      const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
      link.href = url
      link.download = `health-agent-${safeName}-${date}.md`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setExportingReport(false)
    }
  }

  const riskColor: Record<string, string> = {
    low: 'var(--risk-low)',
    medium: 'var(--risk-medium)',
    high: 'var(--risk-high)',
    emergency: 'var(--risk-emergency)',
  }

  const graphJourney = normalizeJourney(userGraph)
  const graphRiskSignals = normalizeRiskSignals(userGraph)
  const graphActiveSignals = graphRiskSignals.filter((item) => item.is_active || item.is_current_session).slice(0, 2)
  const graphHistoricalSignals = graphRiskSignals
    .filter((item) => !graphActiveSignals.some((active) => active.label === item.label && active.session_id === item.session_id))
    .slice(0, 3)

  return (
    <div className="page">
      <div className="aurora" />
      <button
        type="button"
        className="floating-settings"
        onClick={() => setShowModelConfigModal(true)}
        aria-label={t.openSettings}
        title={t.openSettings}
      >
        {'\u2699'}
      </button>
      <header className="hero">
        <h1>Health Agent</h1>
        <p>{t.heroSubtitle}</p>
      </header>

      <main className={pageMode === 'graph' && activeUser ? 'graph-main' : 'layout'}>
        {pageMode === 'graph' && activeUser ? (
          <UserGraphPage
            activeUser={activeUser}
            userGraph={userGraph}
            sessions={sessions}
            currentSessionId={sessionId}
            locale={activeLocale}
            onBack={() => setPageMode('chat')}
            copy={{
              title: t.graphPageTitle,
              back: t.graphBack,
              subtitle: t.graphPageSubtitle,
              fitView: t.graphFitView,
              reset: t.graphReset,
              filters: t.graphFilters,
              nodeTypes: t.graphNodeTypes,
              sessionScope: t.graphSessionScope,
              riskScope: t.graphRiskScope,
              sessionAll: t.graphSessionAll,
              sessionCurrent: t.graphSessionCurrent,
              sessionSelected: t.graphSessionSelected,
              riskAll: t.graphRiskAll,
              riskHigh: t.graphRiskHigh,
              riskHideLow: t.graphRiskHideLow,
              details: t.graphDetails,
              noSelection: t.graphNoSelection,
              longTerm: t.graphLongTerm,
              sessions: t.history,
              viewGraph: t.viewGraph,
            }}
          />
        ) : (
          <>
        <aside className="panel left-panel">
          <h2>{t.userProfile}</h2>

          {activeUser ? (
            <div className="grid">
              <label>
                {t.currentUser}
                <select value={activeUserId} onChange={(e) => void switchActiveUser(e.target.value)}>
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.username}
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
                <button type="button" onClick={() => setPageMode('graph')} disabled={!userGraph}>
                  {t.viewGraph}
                </button>
                <button type="button" onClick={() => void onExportReport()} disabled={exportingReport}>
                  {exportingReport ? t.exporting : t.exportReport}
                </button>
              </div>

              <div className="profile-summary">
                <p>
                  {t.locale}: {activeUser.locale}
                </p>
                <p>
                  {t.region}: {activeUser.region_code}
                </p>
                {activeUser.birth_year && (
                  <p>
                    {t.birthYear}: {activeUser.birth_year}
                  </p>
                )}
                {activeUser.sex && (
                  <p>
                    {t.sex}: {formatSexLabel(activeUser.sex, activeLocale, t)}
                  </p>
                )}
              </div>

              <div className="profile-summary">
                <h3>{t.graphTimeline}</h3>
                {graphJourney.length > 0 ? (
                  <div className="journey-list">
                    {graphJourney.slice(0, 5).map((item, index) => (
                      <article key={`${item.session_id}-${item.title}-${index}`} className="journey-card">
                        <div className="journey-head">
                          <span className={`summary-chip summary-chip-${item.severity_hint === 'medium' ? 'warn' : 'muted'}`}>
                            {item.is_current_session ? t.graphCurrent : t.graphHistory}
                          </span>
                        </div>
                        <strong>{item.title}</strong>
                        {item.detail && <p>{item.detail}</p>}
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="placeholder">{t.graphNoJourney}</p>
                )}
              </div>

              <div className="profile-summary">
                <h3>{t.graphRisk}</h3>
                {graphActiveSignals.length > 0 || graphHistoricalSignals.length > 0 ? (
                  <div className="risk-summary-list">
                    {graphActiveSignals.length > 0 && (
                      <div className="summary-group">
                        <span className="summary-label">{t.graphActiveRisk}</span>
                        {graphActiveSignals.map((signal, index) => (
                          <div key={`${signal.label}-${signal.session_id}-${index}`} className="risk-summary-item">
                            <span
                              className="risk-tag"
                              style={{ background: riskColor[signal.risk_level] || '#495057', marginBottom: 0 }}
                            >
                              {t.risk[signal.risk_level as keyof typeof t.risk] || signal.risk_level.toUpperCase()}
                            </span>
                            <p>{signal.label}</p>
                          </div>
                        ))}
                      </div>
                    )}
                    {graphHistoricalSignals.length > 0 && (
                      <div className="summary-group">
                        <span className="summary-label">{t.graphHistoricalRisk}</span>
                        {graphHistoricalSignals.map((signal, index) => (
                          <div key={`${signal.label}-${signal.session_id}-${index}`} className="risk-summary-item risk-summary-item-muted">
                            <span className="summary-chip summary-chip-muted">
                              {t.risk[signal.risk_level as keyof typeof t.risk] || signal.risk_level.toUpperCase()}
                            </span>
                            <p>{signal.label}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="placeholder">{t.graphNoRisk}</p>
                )}
              </div>
            </div>
          ) : (
            <p className="placeholder">{t.noUserHint}</p>
          )}

        </aside>

        <section className="panel chat-panel">
          <div className="messages">
            {messages.length === 0 && <p className="placeholder">{t.startPrompt}</p>}
            {messages.map((msg) => {
              const parsed = msg.role === 'assistant' ? parseAssistant(msg.content) : null
              const adviceSections = parsed ? getOrderedAdviceSections(parsed) : []
              const primaryAdvice = adviceSections.filter((item) => item.section.priority === 'primary')
              const secondaryAdvice = adviceSections.filter((item) => item.section.priority !== 'primary')
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
                        <div className="doctor-dialogue">
                          <p>{parsed.summary}</p>
                          {(parsed.follow_up_questions || []).map((question, i) => (
                            <p key={`${msg.id}-q-${i}`} className="doctor-question">
                              {question}
                            </p>
                          ))}
                        </div>
                      ) : (
                        <>
                          {primaryAdvice.length > 0 && (
                            <div className="advice-section-list">
                              {primaryAdvice.map(({ key, section }) => (
                                <section key={`${msg.id}-${key}`} className="advice-section advice-section-primary">
                                  <h3>{section.title}</h3>
                                  <ul>
                                    {section.items.map((item, i) => (
                                      <li key={`${msg.id}-${key}-${i}`}>{item}</li>
                                    ))}
                                  </ul>
                                </section>
                              ))}
                            </div>
                          )}
                          {secondaryAdvice.length > 0 && (
                            <div className="advice-section-list advice-section-list-secondary">
                              {secondaryAdvice.map(({ key, section }) => (
                                <section key={`${msg.id}-${key}`} className="advice-section advice-section-secondary">
                                  <h3>{section.title}</h3>
                                  <ul>
                                    {section.items.map((item, i) => (
                                      <li key={`${msg.id}-${key}-${i}`}>{item}</li>
                                    ))}
                                  </ul>
                                </section>
                              ))}
                            </div>
                          )}
                          {adviceSections.length === 0 && (
                            <ul>
                              {parsed.next_steps.map((step, i) => (
                                <li key={`${msg.id}-${i}`}>{step}</li>
                              ))}
                            </ul>
                          )}
                          {parsed.emergency_guidance && <p className="emergency">{parsed.emergency_guidance}</p>}
                          <h3>{parsed.summary}</h3>
                          <div className="risk-tag" style={{ background: riskColor[parsed.risk_level] || '#495057' }}>
                            {t.risk[parsed.risk_level]}
                          </div>
                          <p className="disclaimer">{parsed.disclaimer}</p>
                        </>
                      )}
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
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  const form = e.currentTarget.form
                  if (form) {
                    form.requestSubmit()
                  }
                }
              }}
              placeholder={t.composerPlaceholder}
              rows={4}
              disabled={!modelConfigured || checkingModelConfig || !activeUser}
            />
            <button type="submit" disabled={loading || !modelConfigured || checkingModelConfig || !activeUser}>
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
          </>
        )}
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
                <select
                  value={userDraft.sex}
                  onChange={(e) =>
                    setUserDraft((prev) => ({ ...prev, sex: normalizeSexValue(e.target.value) }))
                  }
                >
                  <option value="">{t.sexPlaceholder}</option>
                  <option value="male">{t.sexMale}</option>
                  <option value="female">{t.sexFemale}</option>
                </select>
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
            {modelConfigured && (
              <button type="button" onClick={() => setShowModelConfigModal(false)}>
                {t.hide}
              </button>
            )}
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
                  <button type="button" onClick={refreshOAuthStatus} disabled={oauthActionLoading}>
                    {t.oauthRefresh}
                  </button>
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
