import { useCallback, useEffect, useMemo, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Handle,
  MiniMap,
  NodeProps,
  Position,
  ReactFlowInstance,
  ReactFlowProvider,
} from 'reactflow'

import { AssociationAnalysisRow, SessionItem, UserGraphResponse, UserProfile } from '../lib/api'
import { GraphEdgeData, GraphFilterState, GraphNodeData, buildGraphViewState } from '../lib/graphTree'

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
  inferredLinks: string
  analysisLinks: string
  runAnalysis: string
  analyzing: string
  details: string
  analysisTable: string
  analysisEmpty: string
  analysisModeDetails: string
  analysisModeTable: string
  analysisType: string
  analysisConfidence: string
  analysisEvidence: string
  analysisSessions: string
  detailTypeNode: string
  detailTypeAssociation: string
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
  analysisRows: AssociationAnalysisRow[]
  analyzingAssociations: boolean
  onRunAssociationAnalysis: () => void
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
  analysisRows,
  analyzingAssociations,
  onRunAssociationAnalysis,
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
    showInferredLinks: false,
    showAnalysisLinks: false,
  })
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [selectedEdge, setSelectedEdge] = useState<Edge<GraphEdgeData> | null>(null)
  const [panelMode, setPanelMode] = useState<'details' | 'analysis'>('details')
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

  useEffect(() => {
    if (!analyzingAssociations && analysisRows.length > 0) {
      setPanelMode('analysis')
    }
  }, [analysisRows.length, analyzingAssociations])

  const selectedNode = graphState?.nodes.find((node) => node.id === selectedNodeId) || null

  const onNodeClick = useCallback(
    (_event: unknown, node: { id: string; data: GraphNodeData }) => {
      setSelectedEdge(null)
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

  const onEdgeClick = useCallback((_event: unknown, edge: Edge<GraphEdgeData>) => {
    setSelectedNodeId('')
    setSelectedEdge(edge)
  }, [])

  const resetView = useCallback(() => {
    if (!graphState) return
    setExpandedIds(new Set(graphState.defaultExpandedIds))
    setFilters((prev) => ({
      ...prev,
      sessionMode: 'all',
      riskMode: 'all',
      showInferredLinks: false,
      showAnalysisLinks: false,
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
            <label className="graph-inline-toggle">
              <input
                type="checkbox"
                checked={filters.showInferredLinks}
                onChange={(e) => setFilters((prev) => ({ ...prev, showInferredLinks: e.target.checked }))}
              />
              <span>{copy.inferredLinks}</span>
            </label>
            <label className="graph-inline-toggle">
              <input
                type="checkbox"
                checked={filters.showAnalysisLinks}
                onChange={(e) => setFilters((prev) => ({ ...prev, showAnalysisLinks: e.target.checked }))}
              />
              <span>{copy.analysisLinks}</span>
            </label>
            <button type="button" onClick={onRunAssociationAnalysis} disabled={analyzingAssociations}>
              {analyzingAssociations ? copy.analyzing : copy.runAnalysis}
            </button>
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
              onEdgeClick={onEdgeClick}
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
          <div className="graph-detail-header">
            <h3>{panelMode === 'analysis' ? copy.analysisTable : copy.details}</h3>
            <div className="graph-detail-tabs">
              <button type="button" className={panelMode === 'details' ? 'is-active' : ''} onClick={() => setPanelMode('details')}>
                {copy.analysisModeDetails}
              </button>
              <button type="button" className={panelMode === 'analysis' ? 'is-active' : ''} onClick={() => setPanelMode('analysis')}>
                {copy.analysisModeTable}
              </button>
            </div>
          </div>
          {panelMode === 'analysis' ? (
            analysisRows.length > 0 ? (
              <div className="graph-analysis-table">
                {analysisRows.map((row, index) => (
                  <article key={`${row.from_ref}-${row.to_ref}-${index}`} className="graph-analysis-row">
                    <strong>{row.from_ref} → {row.to_ref}</strong>
                    <dl>
                      <div>
                        <dt>{copy.analysisType}</dt>
                        <dd>{row.association_type}</dd>
                      </div>
                      <div>
                        <dt>{copy.analysisConfidence}</dt>
                        <dd>{row.confidence}</dd>
                      </div>
                      <div>
                        <dt>{copy.analysisSessions}</dt>
                        <dd>{row.source_session_ids.join(', ') || '-'}</dd>
                      </div>
                    </dl>
                    <p>
                      <span>{copy.analysisEvidence}: </span>
                      {row.evidence_summary}
                    </p>
                  </article>
                ))}
              </div>
            ) : (
              <p>{copy.analysisEmpty}</p>
            )
          ) : selectedEdge?.data?.kind === 'association' ? (
            <div className="graph-detail-card">
              <strong>{selectedEdge.data.title}</strong>
              <dl>
                <div>
                  <dt>Type</dt>
                  <dd>{copy.detailTypeAssociation}</dd>
                </div>
                {selectedEdge.data.edgeType && (
                  <div>
                    <dt>Edge</dt>
                    <dd>{selectedEdge.data.edgeType}</dd>
                  </div>
                )}
                {selectedEdge.data.confidence && (
                  <div>
                    <dt>Confidence</dt>
                    <dd>{selectedEdge.data.confidence}</dd>
                  </div>
                )}
                {selectedEdge.data.evidenceType && (
                  <div>
                    <dt>Source</dt>
                    <dd>{selectedEdge.data.evidenceType}</dd>
                  </div>
                )}
                {selectedEdge.data.sourceSessionIds && selectedEdge.data.sourceSessionIds.length > 0 && (
                  <div>
                    <dt>Sessions</dt>
                    <dd>{selectedEdge.data.sourceSessionIds.join(', ')}</dd>
                  </div>
                )}
              </dl>
              <pre>{selectedEdge.data.evidenceSummary || ''}</pre>
            </div>
          ) : selectedNode ? (
            <div className="graph-detail-card">
              <strong>{selectedNode.data.title}</strong>
              {selectedNode.data.subtitle && <p>{selectedNode.data.subtitle}</p>}
              {selectedNode.data.badge && <span className={`graph-detail-badge graph-detail-badge-${selectedNode.data.badgeTone || 'muted'}`}>{selectedNode.data.badge}</span>}
              <dl>
                <div>
                  <dt>Kind</dt>
                  <dd>{copy.detailTypeNode}: {selectedNode.data.kind}</dd>
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
