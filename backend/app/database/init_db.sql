-- Worldbuilding Companion schema

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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_entities_world ON entities(world_id);
CREATE INDEX IF NOT EXISTS idx_entities_world_type ON entities(world_id, type);
CREATE INDEX IF NOT EXISTS idx_entities_world_name ON entities(world_id, name);
CREATE INDEX IF NOT EXISTS idx_relations_world ON relations(world_id);
CREATE INDEX IF NOT EXISTS idx_relations_source_entity ON relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_target_entity ON relations(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_notes_world ON notes(world_id);
