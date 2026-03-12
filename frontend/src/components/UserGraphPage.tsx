import { useCallback, useEffect, useMemo, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MiniMap,
  NodeProps,
  Position,
  ReactFlowInstance,
  ReactFlowProvider,
} from 'reactflow'

import { SessionItem, UserGraphResponse, UserProfile } from '../lib/api'
import { GraphFilterState, GraphNodeData, buildGraphViewState } from '../lib/graphTree'

type CopyText = {
  title: string
  back: string
  subtitle: string
  fitView: string
  reset: string
  filters: string
  nodeTypes: string
  sessionScope: string
  riskScope: string
  sessionAll: string
  sessionCurrent: string
  sessionSelected: string
  riskAll: string
  riskHigh: string
  riskHideLow: string
  details: string
  noSelection: string
  longTerm: string
  sessions: string
  viewGraph: string
}

type Props = {
  activeUser: UserProfile
  userGraph: UserGraphResponse | null
  sessions: SessionItem[]
  currentSessionId?: string
  locale: string
  copy: CopyText
  onBack: () => void
}

function HealthTreeNode({ data }: NodeProps<GraphNodeData>) {
  return (
    <div
      className={[
        'graph-node',
        `graph-node-${data.kind}`,
        data.highlighted ? 'graph-node-highlighted' : '',
        data.badgeTone ? `graph-node-risk-${data.badgeTone}` : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <Handle type="target" position={Position.Left} className="graph-handle" />
      {data.subtitle && <div className="graph-node-subtitle">{data.subtitle}</div>}
      <div className="graph-node-title-row">
        <strong>{data.title}</strong>
        {data.badge && <span className={`graph-node-badge graph-node-badge-${data.badgeTone || 'muted'}`}>{data.badge}</span>}
      </div>
      {data.meta && <div className="graph-node-meta">{data.meta}</div>}
      {data.collapsible && (
        <div className="graph-node-toggle">{data.expanded ? '−' : '+'}</div>
      )}
      <Handle type="source" position={Position.Right} className="graph-handle" />
    </div>
  )
}

export default function UserGraphPage({
  activeUser,
  userGraph,
  sessions,
  currentSessionId,
  locale,
  copy,
  onBack,
}: Props) {
  const [filters, setFilters] = useState<GraphFilterState>({
    nodeTypes: {
      session: true,
      summary: true,
      risk_signal: true,
      symptom_event: true,
      timeline_marker: true,
      symptom: true,
      long_term: true,
    },
    sessionMode: 'all',
    selectedSessionId: currentSessionId || sessions[0]?.id || '',
    riskMode: 'all',
  })
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [flow, setFlow] = useState<ReactFlowInstance | null>(null)

  useEffect(() => {
    setFilters((prev) => ({
      ...prev,
      selectedSessionId: prev.selectedSessionId || currentSessionId || sessions[0]?.id || '',
    }))
  }, [currentSessionId, sessions])

  const graphState = useMemo(() => {
    if (!userGraph) return null
    return buildGraphViewState({
      userGraph,
      activeUser,
      sessions,
      currentSessionId,
      filters,
      expandedIds,
      locale,
    })
  }, [activeUser, currentSessionId, expandedIds, filters, locale, sessions, userGraph])

  useEffect(() => {
    if (!graphState) return
    if (expandedIds.size === 0) {
      setExpandedIds(new Set(graphState.defaultExpandedIds))
    }
    if (!selectedNodeId && graphState.nodes[0]) {
      setSelectedNodeId(graphState.nodes[0].id)
    }
  }, [expandedIds.size, graphState, selectedNodeId])

  useEffect(() => {
    if (!flow || !graphState) return
    const timer = window.setTimeout(() => flow.fitView({ padding: 0.18, duration: 320 }), 40)
    return () => window.clearTimeout(timer)
  }, [flow, graphState])

  const selectedNode = graphState?.nodes.find((node) => node.id === selectedNodeId) || null

  const onNodeClick = useCallback(
    (_event: unknown, node: { id: string; data: GraphNodeData }) => {
      setSelectedNodeId(node.id)
      if (node.data.collapsible) {
        setExpandedIds((prev) => {
          const next = new Set(prev)
          if (next.has(node.id)) next.delete(node.id)
          else next.add(node.id)
          return next
        })
      }
    },
    [],
  )

  const resetView = useCallback(() => {
    if (!graphState) return
    setExpandedIds(new Set(graphState.defaultExpandedIds))
    setFilters((prev) => ({
      ...prev,
      sessionMode: 'all',
      riskMode: 'all',
      selectedSessionId: currentSessionId || sessions[0]?.id || '',
      nodeTypes: {
        session: true,
        summary: true,
        risk_signal: true,
        symptom_event: true,
        timeline_marker: true,
        symptom: true,
        long_term: true,
      },
    }))
    window.setTimeout(() => flow?.fitView({ padding: 0.18, duration: 260 }), 40)
  }, [currentSessionId, flow, graphState, sessions])

  if (!userGraph) {
    return (
      <section className="graph-page-empty">
        <button type="button" onClick={onBack}>
          {copy.back}
        </button>
        <p>{copy.noSelection}</p>
      </section>
    )
  }

  return (
    <section className="graph-page">
      <header className="graph-toolbar">
        <div className="graph-toolbar-main">
          <button type="button" className="graph-back" onClick={onBack}>
            {copy.back}
          </button>
          <div>
            <h2>{copy.title}</h2>
            <p>{activeUser.username} · {copy.subtitle}</p>
          </div>
        </div>
        <div className="graph-toolbar-actions">
          <button type="button" onClick={() => flow?.fitView({ padding: 0.18, duration: 260 })}>
            {copy.fitView}
          </button>
          <button type="button" onClick={resetView}>
            {copy.reset}
          </button>
        </div>
      </header>

      <div className="graph-shell">
        <aside className="graph-sidebar">
          <section className="graph-filter-card">
            <h3>{copy.filters}</h3>
            <label>
              {copy.sessionScope}
              <select
                value={filters.sessionMode}
                onChange={(e) =>
                  setFilters((prev) => ({
                    ...prev,
                    sessionMode: e.target.value as GraphFilterState['sessionMode'],
                  }))
                }
              >
                <option value="all">{copy.sessionAll}</option>
                <option value="current">{copy.sessionCurrent}</option>
                <option value="selected">{copy.sessionSelected}</option>
              </select>
            </label>
            {filters.sessionMode === 'selected' && (
              <label>
                {copy.sessions}
                <select
                  value={filters.selectedSessionId}
                  onChange={(e) => setFilters((prev) => ({ ...prev, selectedSessionId: e.target.value }))}
                >
                  {sessions.map((session) => (
                    <option key={session.id} value={session.id}>
                      {session.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              {copy.riskScope}
              <select
                value={filters.riskMode}
                onChange={(e) =>
                  setFilters((prev) => ({
                    ...prev,
                    riskMode: e.target.value as GraphFilterState['riskMode'],
                  }))
                }
              >
                <option value="all">{copy.riskAll}</option>
                <option value="high-emergency">{copy.riskHigh}</option>
                <option value="hide-low">{copy.riskHideLow}</option>
              </select>
            </label>
          </section>

          <section className="graph-filter-card">
            <h3>{copy.nodeTypes}</h3>
            <div className="graph-filter-toggles">
              {Object.entries(filters.nodeTypes).map(([key, enabled]) => (
                <label key={key} className="graph-toggle-chip">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(e) =>
                      setFilters((prev) => ({
                        ...prev,
                        nodeTypes: { ...prev.nodeTypes, [key]: e.target.checked },
                      }))
                    }
                  />
                  <span>{key}</span>
                </label>
              ))}
            </div>
          </section>
        </aside>

        <div className="graph-canvas-panel">
          <ReactFlowProvider>
            <ReactFlow
              nodes={graphState?.nodes || []}
              edges={graphState?.edges || []}
              onNodeClick={onNodeClick}
              onInit={setFlow}
              nodeTypes={{ healthTreeNode: HealthTreeNode }}
              fitView
              minZoom={0.35}
              maxZoom={1.4}
              nodesDraggable={false}
              elementsSelectable
            >
              <Background gap={18} size={1} color="rgba(18, 38, 32, 0.08)" />
              <MiniMap pannable zoomable />
              <Controls showInteractive={false} />
            </ReactFlow>
          </ReactFlowProvider>
        </div>

        <aside className="graph-detail-panel">
          <h3>{copy.details}</h3>
          {selectedNode ? (
            <div className="graph-detail-card">
              <strong>{selectedNode.data.title}</strong>
              {selectedNode.data.subtitle && <p>{selectedNode.data.subtitle}</p>}
              {selectedNode.data.badge && <span className={`graph-detail-badge graph-detail-badge-${selectedNode.data.badgeTone || 'muted'}`}>{selectedNode.data.badge}</span>}
              <dl>
                <div>
                  <dt>Kind</dt>
                  <dd>{selectedNode.data.kind}</dd>
                </div>
                {selectedNode.data.sessionId && (
                  <div>
                    <dt>Session</dt>
                    <dd>{selectedNode.data.sessionId}</dd>
                  </div>
                )}
                {selectedNode.data.meta && (
                  <div>
                    <dt>Meta</dt>
                    <dd>{selectedNode.data.meta}</dd>
                  </div>
                )}
              </dl>
              <pre>{JSON.stringify(selectedNode.data.payload || {}, null, 2)}</pre>
            </div>
          ) : (
            <p>{copy.noSelection}</p>
          )}
        </aside>
      </div>
    </section>
  )
}
