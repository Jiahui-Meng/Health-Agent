import { Edge, Node } from 'reactflow'

import { RiskLevel, SessionItem, UserGraphResponse, UserProfile } from './api'

export type GraphNodeKind =
  | 'user'
  | 'group'
  | 'session'
  | 'summary'
  | 'risk_signal'
  | 'symptom_event'
  | 'timeline_marker'
  | 'symptom'
  | 'long_term'

export type GraphFilterState = {
  nodeTypes: {
    session: boolean
    summary: boolean
    risk_signal: boolean
    symptom_event: boolean
    timeline_marker: boolean
    symptom: boolean
    long_term: boolean
  }
  sessionMode: 'all' | 'current' | 'selected'
  selectedSessionId: string
  riskMode: 'all' | 'high-emergency' | 'hide-low'
  showInferredLinks: boolean
  showAnalysisLinks: boolean
}

export type GraphNodeData = {
  title: string
  subtitle?: string
  badge?: string
  badgeTone?: string
  kind: GraphNodeKind
  collapsible?: boolean
  expanded?: boolean
  sessionId?: string
  highlighted?: boolean
  payload?: Record<string, unknown>
  meta?: string
}

export type GraphEdgeData = {
  kind: 'tree' | 'association'
  title?: string
  edgeType?: string
  confidence?: string
  evidenceType?: string
  evidenceSummary?: string
  sourceSessionIds?: string[]
}

export type GraphViewState = {
  nodes: Array<Node<GraphNodeData>>
  edges: Array<Edge<GraphEdgeData>>
  defaultExpandedIds: string[]
}

const SESSION_GROUP_ID = 'graph-group-sessions'
const LONGTERM_GROUP_ID = 'graph-group-longterm'
const DEFAULT_SESSION_LIMIT = 5
const ASSOCIATION_EDGE_TYPES = new Set([
  'POSSIBLY_RELATED_TO',
  'POSSIBLY_EXPLAINED_BY',
  'POSSIBLY_RECURRENT_WITH',
  'POSSIBLY_CYCLE_RELATED',
  'MODEL_POSSIBLY_RELATED_TO',
  'MODEL_POSSIBLY_EXPLAINED_BY',
  'MODEL_POSSIBLY_RECURRENT_WITH',
  'MODEL_POSSIBLY_PATTERN_LINKED',
])

type TreeItem = {
  id: string
  parentId?: string
  data: GraphNodeData
}

export function buildGraphViewState(params: {
  userGraph: UserGraphResponse
  activeUser: UserProfile
  sessions: SessionItem[]
  currentSessionId?: string
  filters: GraphFilterState
  expandedIds: Set<string>
  locale: string
}): GraphViewState {
  const { userGraph, activeUser, sessions, currentSessionId, filters, expandedIds, locale } = params
  const nodesById = new Map(userGraph.nodes.map((node) => [node.id, node]))
  const root = userGraph.nodes.find((node) => node.node_type === 'user')
  const rootId = root?.id || `user:${userGraph.user_id}`
  const effectiveCurrentSessionId =
    currentSessionId ||
    userGraph.summary_bundle.recent_journey?.find((item) => item.is_current_session)?.session_id ||
    sessions[0]?.id ||
    ''

  const sessionNodes = userGraph.nodes
    .filter((node) => node.node_type === 'session')
    .sort((a, b) => sessionRank(a.label, sessions, effectiveCurrentSessionId) - sessionRank(b.label, sessions, effectiveCurrentSessionId))

  const scopedSessions = filterSessionNodes(sessionNodes, filters, effectiveCurrentSessionId).slice(0, DEFAULT_SESSION_LIMIT)

  const treeItems: TreeItem[] = [
    {
      id: rootId,
      data: {
        title: activeUser.username,
        subtitle: [activeUser.birth_year ? `${locale.startsWith('zh') ? '出生' : 'Born'} ${activeUser.birth_year}` : '', activeUser.region_code]
          .filter(Boolean)
          .join(' · '),
        kind: 'user',
        collapsible: false,
        meta: activeUser.id,
        payload: root?.payload || {},
      },
    },
    {
      id: SESSION_GROUP_ID,
      parentId: rootId,
      data: {
        title: locale.startsWith('zh') ? '问诊会话' : 'Sessions',
        subtitle: locale.startsWith('zh') ? `最近 ${scopedSessions.length} 个` : `Recent ${scopedSessions.length}`,
        kind: 'group',
        collapsible: false,
      },
    },
  ]

  const longTermNodes = userGraph.nodes.filter((node) => ['condition', 'medication', 'allergy'].includes(node.node_type))
  if (filters.nodeTypes.long_term && longTermNodes.length > 0) {
    treeItems.push({
      id: LONGTERM_GROUP_ID,
      parentId: rootId,
      data: {
        title: locale.startsWith('zh') ? '长期特征' : 'Longitudinal Features',
        subtitle: locale.startsWith('zh') ? '默认折叠' : 'Collapsed by default',
        kind: 'group',
        collapsible: true,
        expanded: expandedIds.has(LONGTERM_GROUP_ID),
      },
    })
  }

  for (const sessionNode of scopedSessions) {
    const sessionMeta = sessions.find((session) => session.id === sessionNode.label)
    const risk = normalizeRiskLevel(sessionMeta?.latest_risk || String((sessionNode.payload || {}).latest_risk || 'low'))
    treeItems.push({
      id: sessionNode.id,
      parentId: SESSION_GROUP_ID,
      data: {
        title: sessionLabel(sessionNode.label, locale),
        subtitle: sessionMeta?.updated_at ? new Date(sessionMeta.updated_at).toLocaleString(locale) : '',
        badge: riskLabel(risk, locale),
        badgeTone: risk,
        kind: 'session',
        collapsible: true,
        expanded: expandedIds.has(sessionNode.id),
        sessionId: sessionNode.label,
        payload: sessionNode.payload || {},
        meta: sessionNode.label === effectiveCurrentSessionId ? (locale.startsWith('zh') ? '当前会话' : 'Current') : undefined,
      },
    })

    if (!expandedIds.has(sessionNode.id)) continue

    treeItems.push(
      ...buildSessionChildren({
        sessionNodeId: sessionNode.id,
        sessionId: sessionNode.label,
        userGraph,
        nodesById,
        filters,
        locale,
      }),
    )
  }

  if (filters.nodeTypes.long_term && expandedIds.has(LONGTERM_GROUP_ID)) {
    for (const node of longTermNodes) {
      treeItems.push({
        id: node.id,
        parentId: LONGTERM_GROUP_ID,
        data: {
          title: node.label,
          subtitle: longTermLabel(node.node_type, locale),
          kind: 'long_term',
          payload: node.payload || {},
          meta: node.source,
        },
      })
    }
  }

  const itemById = new Map(treeItems.map((item) => [item.id, item]))
  const highlightedIds = new Set<string>()
  const visibleSelectedSessionId = filters.sessionMode === 'selected' ? filters.selectedSessionId : effectiveCurrentSessionId
  if (visibleSelectedSessionId) {
    const matchingSession = treeItems.find(
      (item) => item.data.kind === 'session' && item.data.sessionId === visibleSelectedSessionId,
    )
    let cursor = matchingSession
    while (cursor) {
      highlightedIds.add(cursor.id)
      cursor = cursor.parentId ? itemById.get(cursor.parentId) : undefined
    }
  }

  const edges: Array<Edge<GraphEdgeData>> = treeItems
    .filter((item) => item.parentId)
    .map((item) => ({
      id: `${item.parentId}-${item.id}`,
      source: item.parentId as string,
      target: item.id,
      type: 'smoothstep',
      animated: item.data.kind === 'risk_signal' && ['high', 'emergency'].includes(item.data.badgeTone || ''),
      data: { kind: 'tree' },
    }))

  const positioned = layoutTree(treeItems, edges)
  const visibleNodeIds = new Set(positioned.map((node) => node.id))
  if (filters.showInferredLinks) {
    for (const edge of userGraph.edges) {
      if (!ASSOCIATION_EDGE_TYPES.has(edge.edge_type)) continue
      if (edge.edge_type.startsWith('MODEL_')) continue
      if (!visibleNodeIds.has(edge.from_node_id) || !visibleNodeIds.has(edge.to_node_id)) continue
      const confidence = String(edge.payload?.confidence || 'low')
      edges.push({
        id: edge.id,
        source: edge.from_node_id,
        target: edge.to_node_id,
        type: 'smoothstep',
        animated: confidence === 'high',
        style: {
          strokeDasharray: confidence === 'high' ? '7 4' : '4 5',
          strokeWidth: confidence === 'high' ? 2.2 : confidence === 'medium' ? 1.8 : 1.4,
          stroke:
            confidence === 'high'
              ? 'rgba(180, 69, 32, 0.92)'
              : confidence === 'medium'
                ? 'rgba(210, 125, 52, 0.82)'
                : 'rgba(78, 99, 122, 0.72)',
        },
        data: {
          kind: 'association',
          title: associationLabel(edge.edge_type, locale),
          edgeType: edge.edge_type,
          confidence,
          evidenceType: String(edge.payload?.evidence_type || ''),
          evidenceSummary: String(edge.payload?.evidence_summary || ''),
          sourceSessionIds: Array.isArray(edge.payload?.source_session_ids)
            ? edge.payload.source_session_ids.map((item) => String(item))
            : [],
        },
      })
    }
  }
  if (filters.showAnalysisLinks) {
    for (const edge of userGraph.edges) {
      if (!edge.edge_type.startsWith('MODEL_')) continue
      if (!visibleNodeIds.has(edge.from_node_id) || !visibleNodeIds.has(edge.to_node_id)) continue
      const confidence = String(edge.payload?.confidence || 'low')
      edges.push({
        id: edge.id,
        source: edge.from_node_id,
        target: edge.to_node_id,
        type: 'smoothstep',
        animated: confidence === 'high',
        style: {
          strokeDasharray: confidence === 'high' ? '11 5' : '8 6',
          strokeWidth: confidence === 'high' ? 2.8 : confidence === 'medium' ? 2.2 : 1.8,
          stroke:
            confidence === 'high'
              ? 'rgba(118, 37, 140, 0.88)'
              : confidence === 'medium'
                ? 'rgba(108, 76, 173, 0.8)'
                : 'rgba(112, 106, 168, 0.68)',
        },
        data: {
          kind: 'association',
          title: analysisAssociationLabel(edge.edge_type, locale),
          edgeType: edge.edge_type,
          confidence,
          evidenceType: String(edge.payload?.evidence_type || ''),
          evidenceSummary: String(edge.payload?.evidence_summary || ''),
          sourceSessionIds: Array.isArray(edge.payload?.source_session_ids)
            ? edge.payload.source_session_ids.map((item) => String(item))
            : [],
        },
      })
    }
  }
  return {
    nodes: positioned.map((node) => ({
      ...node,
      data: {
        ...node.data,
        highlighted: highlightedIds.has(node.id),
      },
      draggable: false,
      deletable: false,
      selectable: true,
    })),
    edges,
    defaultExpandedIds: [SESSION_GROUP_ID, ...scopedSessions.map((node) => node.id)],
  }
}

function buildSessionChildren(params: {
  sessionNodeId: string
  sessionId: string
  userGraph: UserGraphResponse
  nodesById: Map<string, UserGraphResponse['nodes'][number]>
  filters: GraphFilterState
  locale: string
}): TreeItem[] {
  const { sessionNodeId, sessionId, userGraph, filters, locale } = params
  const sessionItems: TreeItem[] = []
  const sessionScopedNodes = userGraph.nodes.filter((node) => String((node.payload || {}).session_id || '') === sessionId)
  const directSymptomIds = new Set(
    userGraph.edges
      .filter((edge) => edge.from_node_id === sessionNodeId)
      .map((edge) => edge.to_node_id),
  )
  const directSymptoms = userGraph.nodes.filter((node) => directSymptomIds.has(node.id) && node.node_type === 'symptom')
  const typedGroups = {
    summary: sessionScopedNodes.filter((node) => node.node_type === 'summary'),
    risk_signal: sessionScopedNodes.filter((node) => node.node_type === 'risk_signal').filter((node) => allowRisk(node, filters.riskMode)),
    symptom_event: sessionScopedNodes.filter((node) => node.node_type === 'symptom_event'),
    timeline_marker: sessionScopedNodes.filter((node) => node.node_type === 'timeline_marker'),
    symptom: directSymptoms,
  }

  const orderedTypes: Array<keyof typeof typedGroups> = ['summary', 'risk_signal', 'symptom_event', 'timeline_marker', 'symptom']
  for (const type of orderedTypes) {
    if (!filters.nodeTypes[type]) continue
    for (const node of typedGroups[type]) {
      const risk =
        type === 'risk_signal'
          ? normalizeRiskLevel(String((node.payload || {}).risk_level || 'medium'))
          : undefined
      sessionItems.push({
        id: node.id,
        parentId: sessionNodeId,
        data: {
          title: node.label,
          subtitle: childSubtitle(type, locale),
          badge: risk ? riskLabel(risk, locale) : undefined,
          badgeTone: risk,
          kind: type as GraphNodeKind,
          payload: node.payload || {},
          sessionId,
          meta: node.source,
        },
      })
    }
  }
  return sessionItems
}

function allowRisk(node: UserGraphResponse['nodes'][number], riskMode: GraphFilterState['riskMode']) {
  if (node.node_type !== 'risk_signal') return true
  const risk = normalizeRiskLevel(String((node.payload || {}).risk_level || 'medium'))
  if (riskMode === 'all') return true
  if (riskMode === 'high-emergency') return ['high', 'emergency'].includes(risk)
  if (riskMode === 'hide-low') return risk !== 'low'
  return true
}

function filterSessionNodes(
  sessionNodes: UserGraphResponse['nodes'],
  filters: GraphFilterState,
  currentSessionId: string,
) {
  if (filters.sessionMode === 'current') {
    return sessionNodes.filter((node) => node.label === currentSessionId)
  }
  if (filters.sessionMode === 'selected' && filters.selectedSessionId) {
    return sessionNodes.filter((node) => node.label === filters.selectedSessionId)
  }
  return sessionNodes
}

function sessionRank(sessionId: string, sessions: SessionItem[], currentSessionId: string) {
  if (sessionId === currentSessionId) return -1000
  const index = sessions.findIndex((session) => session.id === sessionId)
  return index === -1 ? 999 : index
}

function riskLabel(risk: string, locale: string) {
  const zhMap: Record<string, string> = {
    low: '低风险',
    medium: '中风险',
    high: '高风险',
    emergency: '紧急',
  }
  const enMap: Record<string, string> = {
    low: 'LOW',
    medium: 'MEDIUM',
    high: 'HIGH',
    emergency: 'EMERGENCY',
  }
  return locale.startsWith('zh') ? zhMap[risk] || risk.toUpperCase() : enMap[risk] || risk.toUpperCase()
}

function normalizeRiskLevel(risk: string): RiskLevel | string {
  return ['low', 'medium', 'high', 'emergency'].includes(risk) ? (risk as RiskLevel) : 'medium'
}

function longTermLabel(nodeType: string, locale: string) {
  const zh: Record<string, string> = {
    condition: '既往病史',
    medication: '长期用药',
    allergy: '过敏史',
  }
  const en: Record<string, string> = {
    condition: 'Condition',
    medication: 'Medication',
    allergy: 'Allergy',
  }
  return locale.startsWith('zh') ? zh[nodeType] || nodeType : en[nodeType] || nodeType
}

function childSubtitle(type: keyof GraphFilterState['nodeTypes'], locale: string) {
  const zh: Record<string, string> = {
    session: '会话',
    summary: '结论摘要',
    risk_signal: '风险信号',
    symptom_event: '症状事件',
    timeline_marker: '时间标记',
    symptom: '症状',
    long_term: '长期特征',
  }
  const en: Record<string, string> = {
    session: 'Session',
    summary: 'Summary',
    risk_signal: 'Risk Signal',
    symptom_event: 'Symptom Event',
    timeline_marker: 'Timeline Marker',
    symptom: 'Symptom',
    long_term: 'Long-term',
  }
  return locale.startsWith('zh') ? zh[type] || type : en[type] || type
}

function sessionLabel(sessionId: string, locale: string) {
  return locale.startsWith('zh') ? `会话 ${sessionId.slice(0, 8)}` : `Session ${sessionId.slice(0, 8)}`
}

function associationLabel(edgeType: string, locale: string) {
  const zh: Record<string, string> = {
    POSSIBLY_RELATED_TO: '可能相关',
    POSSIBLY_EXPLAINED_BY: '可能由既往特征解释',
    POSSIBLY_RECURRENT_WITH: '可能为复发/持续',
    POSSIBLY_CYCLE_RELATED: '可能与周期相关',
  }
  const en: Record<string, string> = {
    POSSIBLY_RELATED_TO: 'Possible Association',
    POSSIBLY_EXPLAINED_BY: 'Possibly Explained By Trait',
    POSSIBLY_RECURRENT_WITH: 'Possible Recurrence',
    POSSIBLY_CYCLE_RELATED: 'Possible Cycle Relation',
  }
  return locale.startsWith('zh') ? zh[edgeType] || edgeType : en[edgeType] || edgeType
}

function analysisAssociationLabel(edgeType: string, locale: string) {
  const zh: Record<string, string> = {
    MODEL_POSSIBLY_RELATED_TO: '模型分析：可能相关',
    MODEL_POSSIBLY_EXPLAINED_BY: '模型分析：可能由既往特征解释',
    MODEL_POSSIBLY_RECURRENT_WITH: '模型分析：可能为复发/持续',
    MODEL_POSSIBLY_PATTERN_LINKED: '模型分析：可能存在模式关联',
  }
  const en: Record<string, string> = {
    MODEL_POSSIBLY_RELATED_TO: 'Model Analysis: Possible Association',
    MODEL_POSSIBLY_EXPLAINED_BY: 'Model Analysis: Possibly Explained By Trait',
    MODEL_POSSIBLY_RECURRENT_WITH: 'Model Analysis: Possible Recurrence',
    MODEL_POSSIBLY_PATTERN_LINKED: 'Model Analysis: Possible Pattern Link',
  }
  return locale.startsWith('zh') ? zh[edgeType] || edgeType : en[edgeType] || edgeType
}

function layoutTree(treeItems: TreeItem[], edges: Array<Edge<GraphEdgeData>>) {
  const childrenMap = new Map<string, string[]>()
  const itemMap = new Map(treeItems.map((item) => [item.id, item]))
  for (const edge of edges) {
    if (edge.data?.kind === 'association') continue
    const current = childrenMap.get(edge.source) || []
    current.push(edge.target)
    childrenMap.set(edge.source, current)
  }
  const roots = treeItems.filter((item) => !item.parentId).map((item) => item.id)
  const positions = new Map<string, { x: number; y: number }>()
  let cursorY = 0
  const xGap = 300
  const yGap = 112

  function visit(nodeId: string, depth: number): number {
    const children = childrenMap.get(nodeId) || []
    if (children.length === 0) {
      const y = cursorY
      cursorY += yGap
      positions.set(nodeId, { x: depth * xGap, y })
      return y
    }
    const childYs = children.map((childId) => visit(childId, depth + 1))
    const y = (childYs[0] + childYs[childYs.length - 1]) / 2
    positions.set(nodeId, { x: depth * xGap, y })
    return y
  }

  roots.forEach((rootId) => visit(rootId, 0))
  return treeItems.map((item) => ({
    id: item.id,
    type: 'healthTreeNode',
    position: positions.get(item.id) || { x: 0, y: 0 },
    data: item.data,
  }))
}
