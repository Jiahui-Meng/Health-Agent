# Health Graph Architecture

This document describes the current health graph model used by Health Agent. It is based on the implementation in:

- `backend/app/models.py`
- `backend/app/services/graph_service.py`
- `backend/app/schemas.py`

The graph is not stored in a dedicated graph database. It is stored in the same relational database as the rest of the application using node and edge tables.

## 1. Storage Model

The graph lives in two tables:

- `user_graph_nodes`
- `user_graph_edges`

The tables are defined in `backend/app/models.py`.

### `user_graph_nodes`

Each row represents one graph node.

Core fields:

- `id`
- `user_id`
- `node_type`
- `label`
- `payload` (JSON)
- `source`
- `created_at`
- `updated_at`

### `user_graph_edges`

Each row represents one directed graph edge.

Core fields:

- `id`
- `user_id`
- `from_node_id`
- `to_node_id`
- `edge_type`
- `payload` (JSON)
- `created_at`

## 2. Root Shape

The graph is user-centered.

At a high level, the structure is:

```text
user
  -> condition / medication / allergy
  -> session
       -> symptom
       -> symptom_event
       -> timeline_marker
       -> risk_signal
       -> summary
```

Important distinction:

- Long-term data is attached close to the `user` root
- Visit-specific data is attached under `session`

## 3. Node Types

The current implementation uses these node types.

### Long-term nodes

- `user`
  The root node for one local user
- `condition`
  Long-term condition / chronic disease
- `medication`
  Long-term or current medication
- `allergy`
  Allergy history

### Session-scoped nodes

- `session`
  One visit / one conversation thread
- `symptom`
  Canonical symptom label extracted from user text, such as `发烧` or `咳嗽`
- `symptom_event`
  A session-specific symptom occurrence, built from the current message
- `timeline_marker`
  A time/evolution marker such as `今天`, `今早`, `加重`, `持续`
- `risk_signal`
  Final risk markers for a session; only written at `conclusion` stage or emergency direct output
- `summary`
  Session-level summary text saved from the assistant output

## 4. Edge Types

The current implementation uses these edge types.

- `HAS_CONDITION`
- `USES_MEDICATION`
- `HAS_ALLERGY`
- `HAS_SESSION`
- `REPORTED_SYMPTOM`
- `EVOLVED_TO`
- `OCCURRED_AT`
- `HAS_RISK_SIGNAL`
- `SUMMARIZED_AS`

## 5. How Graph Writes Work

Graph writes are handled in `backend/app/services/graph_service.py`, mainly by `upsert_session_graph(...)`.

### User creation / update

When a user is created or edited:

- ensure one `user` root node exists
- upsert long-term feature nodes:
  - `condition`
  - `medication`
  - `allergy`
- reconnect those nodes to the root with:
  - `HAS_CONDITION`
  - `USES_MEDICATION`
  - `HAS_ALLERGY`

Long-term feature updates are replacement-based:

- old profile-sourced nodes of the same type are removed
- the new normalized values are inserted again

### Chat write path

For each chat round:

1. ensure a `session` node exists
2. connect `user -> session` via `HAS_SESSION`
3. extract symptom labels from the user message and write:
   - `symptom`
   - `symptom_event`
4. extract time/evolution markers and write:
   - `timeline_marker`
5. write a `summary` node if assistant summary exists
6. write `risk_signal` only if the round is final:
   - `answer.stage == "conclusion"`

This means the graph keeps raw event history, but does not pollute risk history with intermediate intake rounds.

## 6. How Symptoms and Time Markers Are Extracted

Extraction is rule-based today.

Implemented pattern groups:

- `SYMPTOM_PATTERNS`
- `TIMELINE_PATTERNS`

Examples:

- symptoms:
  - `发烧`
  - `咳嗽`
  - `喉咙痛`
  - `胸痛`
  - `呼吸困难`
- timeline/evolution markers:
  - `今天`
  - `昨天`
  - `今早`
  - `今晚`
  - `持续`
  - `加重`

These patterns are currently heuristic and not yet model-driven.

## 7. Derived Graph Summary

The API does not expose raw nodes only. It also exposes a derived summary bundle via:

- `get_graph_bundle(...)`
- `get_graph_payload(...)`

Returned shape:

- `persistent_features`
- `profile_highlights`
- `recent_timeline`
- `recent_journey`
- `risk_signals`
- `summary_labels`

### Meaning of each derived field

- `persistent_features`
  Long-term features grouped into:
  - `conditions`
  - `medications`
  - `allergies`
- `profile_highlights`
  Lightweight user-level highlights such as birth year, sex, region
- `recent_timeline`
  Raw timeline-like nodes for near-term use
- `recent_journey`
  Human-readable symptom progression cards derived from session events
- `risk_signals`
  Final risk markers, prioritized by current session and severity
- `summary_labels`
  Latest summary node labels

## 8. Session Deletion and Graph Cleanup

Session deletion is not limited to `sessions` and `messages`.

Current behavior:

- deleting a session also removes its graph subtree
- the cleanup removes:
  - the `session` node
  - any node with `payload.session_id == target_session_id`
  - related edges
- orphan `symptom` nodes are pruned after cleanup

This prevents deleted sessions from leaking back into:

- graph API responses
- derived graph summaries
- export reports

## 9. Orphan Filtering

Graph reads explicitly filter out stale session-scoped nodes.

If a node references a session that no longer exists:

- it is excluded from `get_graph_bundle(...)`
- it is excluded from `get_graph_payload(...)`
- its edges are also filtered out of the returned graph payload

This is how the current graph stays iteratively correct after session deletion.

## 10. Iterative Update Strategy

The graph follows this model:

- keep raw event nodes
- rebuild derived meaning from currently valid data

In practice:

- raw symptom and timeline events are appended per session
- long-term profile nodes are replaced/upserted
- summary views are derived on read
- deleted sessions are physically removed from the session subtree

## 11. Graph and Prompt Guardrails

The graph is not only used for UI summaries. User-level profile fields also feed prompt guardrails.

Current prompt guardrail inputs include:

- `sex`
- `birth_year`
- `region_code`

These are normalized in:

- `backend/app/services/profile_guardrails.py`

And then injected into prompt construction through:

- `backend/app/services/prompt_builder.py`

This is how the runtime keeps the model aligned with:

- sex-specific question constraints
- age-group caution rules
- region-aware emergency wording

This is not full graph versioning. It is closer to:

- event retention for valid sessions
- derivation rebuild for current truth

## 11. What the Graph Is Not

The current graph is not:

- a Neo4j-style dedicated graph database
- a full medical ontology
- a fully normalized symptom taxonomy
- a versioned audit graph with immutable historical snapshots

It is a pragmatic session-aware health graph implemented on top of relational tables.

## 12. Current Limits

Important current limitations:

- symptom extraction is rule-based, not ontology-based
- symptom nodes are shared labels, not globally standardized concepts
- session deletion cleans session-scoped nodes, but long-term feature semantics are still relatively simple
- derived summaries are rebuilt from current valid nodes, not from a dedicated materialized projection layer

## 13. Related API Surface

The graph currently surfaces through:

- `GET /api/v1/users/{user_id}/graph`
- `GET /api/v1/users/{user_id}/export?format=markdown`

The graph also affects:

- chat context building
- risk summary display
- export report generation

## 14. Recommended Next Documentation

If this graph model will keep evolving, the next useful docs would be:

1. `docs/graph-lifecycle.md`
   Covers create/update/delete flows for graph writes
2. `docs/export-report.md`
   Covers how graph + sessions become the exported report
3. `docs/triage-runtime.md`
   Covers how graph context is injected into multi-round triage
