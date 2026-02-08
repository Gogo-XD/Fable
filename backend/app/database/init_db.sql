-- Fable schema

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    assistant_id TEXT,
    entity_types TEXT NOT NULL DEFAULT '["character","location","event","item","organization","concept"]',
    relation_types TEXT NOT NULL DEFAULT '["ally_of","enemy_of","parent_of","child_of","located_in","participated_in","member_of"]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    title TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'saved', 'analyzed')),
    analysis_thread_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    subtype TEXT,
    aliases TEXT NOT NULL DEFAULT '[]',
    context TEXT,
    summary TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    image_url TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    source TEXT NOT NULL CHECK(source IN ('user', 'ai')),
    source_note_id TEXT REFERENCES notes(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    source_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    context TEXT,
    weight REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL CHECK(source IN ('user', 'ai')),
    source_note_id TEXT REFERENCES notes(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_markers (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    summary TEXT,
    marker_kind TEXT NOT NULL CHECK(marker_kind IN ('explicit', 'semantic')),
    placement_status TEXT NOT NULL CHECK(placement_status IN ('placed', 'unplaced')),
    date_label TEXT,
    date_sort_value REAL,
    sort_key REAL NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('user', 'ai')),
    source_note_id TEXT REFERENCES notes(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_operations (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    marker_id TEXT NOT NULL REFERENCES timeline_markers(id) ON DELETE CASCADE,
    op_type TEXT NOT NULL,
    target_kind TEXT NOT NULL CHECK(target_kind IN ('entity', 'relation', 'world')),
    target_id TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    order_index INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_snapshots (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    marker_id TEXT NOT NULL REFERENCES timeline_markers(id) ON DELETE CASCADE,
    state_json TEXT NOT NULL,
    state_hash TEXT,
    applied_marker_count INTEGER NOT NULL DEFAULT 0,
    entity_count INTEGER NOT NULL DEFAULT 0,
    relation_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(world_id, marker_id)
);

CREATE TABLE IF NOT EXISTS guardian_runs (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    trigger_kind TEXT NOT NULL CHECK(trigger_kind IN ('note_scan', 'manual', 'api')),
    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'failed', 'applied', 'partial')),
    request_json TEXT NOT NULL DEFAULT '{}',
    summary_json TEXT,
    error TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardian_findings (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES guardian_runs(id) ON DELETE CASCADE,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info')),
    finding_code TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    resolution_status TEXT NOT NULL DEFAULT 'open'
        CHECK(resolution_status IN ('open', 'accepted', 'dismissed', 'applied')),
    evidence_json TEXT NOT NULL DEFAULT '[]',
    suggested_action_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardian_actions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES guardian_runs(id) ON DELETE CASCADE,
    finding_id TEXT REFERENCES guardian_findings(id) ON DELETE SET NULL,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL
        CHECK(action_type IN ('timeline_operation', 'entity_patch', 'relation_patch', 'world_patch', 'noop')),
    op_type TEXT,
    target_kind TEXT CHECK(target_kind IN ('entity', 'relation', 'world')),
    target_id TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK(status IN ('proposed', 'accepted', 'applied', 'rejected', 'failed')),
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardian_mechanic_runs (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES guardian_runs(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'failed', 'partial')),
    request_json TEXT NOT NULL DEFAULT '{}',
    summary_json TEXT,
    error TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardian_mechanic_options (
    id TEXT PRIMARY KEY,
    mechanic_run_id TEXT NOT NULL REFERENCES guardian_mechanic_runs(id) ON DELETE CASCADE,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES guardian_runs(id) ON DELETE CASCADE,
    finding_id TEXT REFERENCES guardian_findings(id) ON DELETE SET NULL,
    option_index INTEGER NOT NULL DEFAULT 0,
    action_type TEXT NOT NULL
        CHECK(action_type IN ('timeline_operation', 'entity_patch', 'relation_patch', 'world_patch', 'noop')),
    op_type TEXT,
    target_kind TEXT CHECK(target_kind IN ('entity', 'relation', 'world')),
    target_id TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    rationale TEXT,
    expected_outcome TEXT,
    risk_level TEXT NOT NULL DEFAULT 'medium' CHECK(risk_level IN ('low', 'medium', 'high')),
    confidence REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK(status IN ('proposed', 'accepted', 'rejected', 'applied', 'failed')),
    mapped_action_id TEXT REFERENCES guardian_actions(id) ON DELETE SET NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_rag_documents (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    slot_key TEXT NOT NULL,
    slot_title TEXT NOT NULL,
    assistant_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_size INTEGER NOT NULL DEFAULT 0,
    record_count INTEGER NOT NULL DEFAULT 0,
    last_compiled_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(world_id, slot_key)
);

CREATE TABLE IF NOT EXISTS world_rag_state (
    world_id TEXT PRIMARY KEY REFERENCES worlds(id) ON DELETE CASCADE,
    is_dirty INTEGER NOT NULL DEFAULT 0 CHECK(is_dirty IN (0, 1)),
    data_version INTEGER NOT NULL DEFAULT 0,
    compiled_version INTEGER NOT NULL DEFAULT 0,
    pending_change_count INTEGER NOT NULL DEFAULT 0,
    last_change_reason TEXT,
    last_change_at TEXT,
    last_compile_attempt_at TEXT,
    last_compiled_at TEXT,
    last_compile_status TEXT,
    last_compile_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_entities_world ON entities(world_id);
CREATE INDEX IF NOT EXISTS idx_entities_world_type ON entities(world_id, type);
CREATE INDEX IF NOT EXISTS idx_entities_world_name ON entities(world_id, name);
CREATE INDEX IF NOT EXISTS idx_relations_world ON relations(world_id);
CREATE INDEX IF NOT EXISTS idx_relations_source_entity ON relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_target_entity ON relations(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_notes_world ON notes(world_id);
CREATE INDEX IF NOT EXISTS idx_timeline_markers_world_sort
    ON timeline_markers(world_id, sort_key, created_at, id);
CREATE INDEX IF NOT EXISTS idx_timeline_operations_marker_sort
    ON timeline_operations(marker_id, order_index, created_at, id);
CREATE INDEX IF NOT EXISTS idx_timeline_operations_world
    ON timeline_operations(world_id);
CREATE INDEX IF NOT EXISTS idx_timeline_snapshots_world
    ON timeline_snapshots(world_id);
CREATE INDEX IF NOT EXISTS idx_guardian_runs_world_created
    ON guardian_runs(world_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_guardian_findings_run_severity
    ON guardian_findings(run_id, severity, created_at);
CREATE INDEX IF NOT EXISTS idx_guardian_actions_run_status
    ON guardian_actions(run_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_guardian_mechanic_runs_world_created
    ON guardian_mechanic_runs(world_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_guardian_mechanic_runs_run
    ON guardian_mechanic_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_guardian_mechanic_options_run_status
    ON guardian_mechanic_options(mechanic_run_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_guardian_mechanic_options_finding
    ON guardian_mechanic_options(finding_id);
CREATE INDEX IF NOT EXISTS idx_world_rag_documents_world_slot
    ON world_rag_documents(world_id, slot_key);
CREATE INDEX IF NOT EXISTS idx_world_rag_state_dirty
    ON world_rag_state(is_dirty, updated_at);
