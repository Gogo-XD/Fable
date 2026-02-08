# Fable - Design Document

## Vision

**Fable** is an AI-augmented knowledge graph tool for storywriters, authors, and game developers. Users build rich, interconnected worlds by creating **entities** (characters, locations, events) and **relations** (father_of, ally_of, participated_in) that are visualized as a living, interactive graph.

The tool blends manual authoring with intelligent AI extraction: users can write freeform notes and let an LLM surface entities, relations, and context automatically -- or they can craft every node by hand. The result is a structured, queryable world bible that grows with the story.

### Hackathon Theme: "Golden Age"

Stories are how civilizations remember their golden ages. The Epic of Gilgamesh, the Mahabharata, Romance of the Three Kingdoms -- these worldbuilding acts preserved entire eras of human achievement. In an age of AI-generated slop, **Fable** is a tool that amplifies human creativity rather than replacing it. AI assists with organization and extraction, but the vision, the lore, the soul of the world -- that stays with the author. This is a tool for the next golden age of storytelling: one where human ingenuity is augmented, not automated.

---

## Architecture Overview

```
+-------------------+        WebSocket (Socket.IO)        +-------------------+
|                   | <----------------------------------> |                   |
|   React Frontend  |         REST API (FastAPI)           |  Python Backend   |
|   (Vite + React   | <----------------------------------> |  (FastAPI + async)|
|    Flow/Cytoscape) |                                     |                   |
+-------------------+                                      +--------+----------+
                                                                    |
                                                           +--------v----------+
                                                           |   SQLite (aio)    |
                                                           |   - entities      |
                                                           |   - relations     |
                                                           |   - notes         |
                                                           |   - worlds        |
                                                           +--------+----------+
                                                                    |
                                                           +--------v----------+
                                                           |  Backboard.io     |
                                                           |  - LLM threads    |
                                                           |  - RAG documents  |
                                                           |  - Assistants     |
                                                           +-------------------+
```

### Tech Stack

| Layer       | Technology                | Purpose                              |
|-------------|---------------------------|--------------------------------------|
| Frontend    | React + Vite + TypeScript | SPA, graph UI, note editor           |
| Graph Viz   | React Flow or Cytoscape   | Interactive node-edge rendering      |
| Rich Text   | TipTap or Milkdown        | Freeform note editor                 |
| Backend     | FastAPI (Python, async)   | REST API + WebSocket                 |
| Realtime    | Socket.IO                 | Live graph updates after AI analysis |
| Database    | SQLite (aiosqlite)        | Persistent storage                   |
| AI/LLM     | Backboard.io              | Threads, RAG, entity extraction      |
| Graph Logic | NetworkX                  | Server-side graph operations         |

---

## Data Model

### Core Concepts

#### Entity

An entity is any "thing" in the world: a character, a location, an event, an item, an organization, a concept. Entities are deliberately flexible -- the *type* and *subtype* are user-defined strings, not a fixed enum.

```
Entity
├── id: UUID
├── world_id: UUID
├── name: str                    # Primary display name
├── type: str                    # Broad category: "character", "location", "event", etc.
├── subtype: str | null          # User-defined refinement: "constellation", "incarnation", "dokkaebi"
├── aliases: list[str]           # Alternative names (e.g., "Kim Dokja", "Most Ancient Dream")
├── context: str | null          # Rich text blob -- extra info, fed to LLM as context
├── summary: str | null          # Short one-liner description
├── tags: list[str]              # Broad grouping labels for filtering/search
├── image_url: str | null        # Optional portrait/icon
├── source: "user" | "ai"       # Who created this node
├── source_note_id: UUID | null  # If AI-generated, which note produced it
├── created_at: datetime
├── updated_at: datetime
```

**Source rules:**
- If a user creates or edits an entity -> `source = "user"`
- If AI extracts an entity from a note -> `source = "ai"`
- If a user edits an AI entity -> `source` flips to `"user"`
- If AI updates a user entity -> `source` stays `"user"`

#### Relation

A directed edge between two entities. Like entities, relation types are user-defined strings.

```
Relation
├── id: UUID
├── world_id: UUID
├── source_entity_id: UUID       # "from" entity
├── target_entity_id: UUID       # "to" entity
├── type: str                    # e.g., "father_of", "ally_of", "incarnation_of", "participated_in"
├── context: str | null          # Explanation of this specific relation
├── weight: float                # 0.0-1.0, relevance/strength (used for graph layout)
├── source: "user" | "ai"       # Same rules as entity source
├── source_note_id: UUID | null
├── created_at: datetime
├── updated_at: datetime
```

#### Note

A freeform text entry. The primary input method for world-building.

```
Note
├── id: UUID
├── world_id: UUID
├── title: str | null
├── content: str                 # Freeform rich text / markdown
├── status: "draft" | "saved" | "analyzed"
├── analysis_thread_id: str | null   # Backboard thread used for analysis
├── created_at: datetime
├── updated_at: datetime
```

#### World

Top-level container. Each world is an independent graph.

```
World
├── id: UUID
├── name: str
├── description: str | null
├── assistant_id: str | null     # Backboard assistant for this world
├── entity_types: list[str]      # User-defined vocabulary: ["character", "location", "event", ...]
├── relation_types: list[str]    # User-defined vocabulary: ["father_of", "ally_of", ...]
├── created_at: datetime
├── updated_at: datetime
```

Storing `entity_types` and `relation_types` on the world allows the UI to offer autocomplete/suggestions while still letting users type anything they want.

---

## Backboard.io Integration Strategy

Backboard is the LLM backbone. The goal is to use it intelligently -- not just as a chat API, but leveraging threads for memory and documents for RAG.

### Per-World Assistant

Each world gets its own Backboard **assistant** with a system prompt tailored to worldbuilding extraction. The assistant knows:
- What entity types exist in this world
- What relation types exist
- The tone/genre of the world

### RAG Documents

Every entity in the world is synced as a **Backboard document**. This gives the LLM retrieval-augmented context about the world when analyzing new notes. As the world grows, the AI becomes better at:
- Recognizing existing entities by name or alias
- Understanding established relations
- Maintaining consistency with prior lore

**Document format** (one per entity):
```markdown
# {entity.name} ({entity.type}/{entity.subtype})
Aliases: {entity.aliases}
Tags: {entity.tags}

{entity.context}

## Relations
- {relation.type} -> {target.name}: {relation.context}
```

### Thread Strategy

| Operation           | Thread Policy                                             |
|---------------------|-----------------------------------------------------------|
| Note analysis       | New thread per note. Stored as `note.analysis_thread_id`. |
| Re-analysis         | Reuse the note's existing thread (conversational memory). |
| Entity enrichment   | New thread, one-shot. No need to persist.                 |
| World-level queries | Shared "world chat" thread for ongoing Q&A.               |

Reusing the note's thread on re-analysis means the LLM remembers what it already extracted and can focus on what's new or changed.

---

## API Design

### Worlds

| Method | Endpoint              | Description              |
|--------|-----------------------|--------------------------|
| POST   | `/api/worlds`         | Create a new world       |
| GET    | `/api/worlds`         | List all worlds          |
| GET    | `/api/worlds/{id}`    | Get world details        |
| PUT    | `/api/worlds/{id}`    | Update world settings    |
| DELETE | `/api/worlds/{id}`    | Delete world + all data  |

### Entities

| Method | Endpoint                          | Description                        |
|--------|-----------------------------------|------------------------------------|
| POST   | `/api/worlds/{wid}/entities`      | Create entity (manual)             |
| GET    | `/api/worlds/{wid}/entities`      | List entities (with filters)       |
| GET    | `/api/worlds/{wid}/entities/{id}` | Get entity detail                  |
| PUT    | `/api/worlds/{wid}/entities/{id}` | Update entity (flips source)       |
| DELETE | `/api/worlds/{wid}/entities/{id}` | Delete entity + its relations      |

**Query params for listing:** `?type=character&subtype=constellation&tag=villain&search=dokja`

### Relations

| Method | Endpoint                           | Description                 |
|--------|------------------------------------|-----------------------------|
| POST   | `/api/worlds/{wid}/relations`      | Create relation (manual)    |
| GET    | `/api/worlds/{wid}/relations`      | List relations (filterable) |
| PUT    | `/api/worlds/{wid}/relations/{id}` | Update relation             |
| DELETE | `/api/worlds/{wid}/relations/{id}` | Delete relation             |

### Notes

| Method | Endpoint                                  | Description                          |
|--------|-------------------------------------------|--------------------------------------|
| POST   | `/api/worlds/{wid}/notes`                 | Create note                          |
| GET    | `/api/worlds/{wid}/notes`                 | List notes                           |
| GET    | `/api/worlds/{wid}/notes/{id}`            | Get note                             |
| PUT    | `/api/worlds/{wid}/notes/{id}`            | Update note content                  |
| DELETE | `/api/worlds/{wid}/notes/{id}`            | Delete note                          |
| POST   | `/api/worlds/{wid}/notes/{id}/analyze`    | Trigger AI analysis                  |

### Graph

| Method | Endpoint                          | Description                              |
|--------|-----------------------------------|------------------------------------------|
| GET    | `/api/worlds/{wid}/graph`         | Full graph (entities + relations as JSON) |
| GET    | `/api/worlds/{wid}/graph/neighborhood/{eid}` | Subgraph around an entity       |

### WebSocket Events (Socket.IO)

| Event             | Direction      | Payload                           |
|-------------------|----------------|-----------------------------------|
| `entity:created`  | Server->Client | Entity object                     |
| `entity:updated`  | Server->Client | Entity object                     |
| `entity:deleted`  | Server->Client | `{ id }`                          |
| `relation:created`| Server->Client | Relation object                   |
| `relation:updated`| Server->Client | Relation object                   |
| `relation:deleted`| Server->Client | `{ id }`                          |
| `analysis:started`| Server->Client | `{ note_id }`                     |
| `analysis:progress`| Server->Client| `{ note_id, step, detail }`       |
| `analysis:complete`| Server->Client| `{ note_id, entities_added, relations_added }` |

---

## Frontend Design

### Pages / Views

1. **Home / World Selector** -- list of worlds, create new world
2. **World Dashboard** -- the main workspace, split into panels:
   - **Graph Canvas** (center) -- interactive node-edge visualization
   - **Side Panel** (right) -- entity/relation detail view and editor
   - **Notes Panel** (left or bottom) -- note list + freeform editor
3. **Entity Detail Modal / Panel** -- view and edit all entity fields
4. **Note Editor** -- rich text editor with "Save" and "Analyze" buttons

### Graph Visualization

- Nodes colored/shaped by `type` (characters = circles, locations = hexagons, events = diamonds, etc.)
- AI-generated nodes visually distinct (dashed border, subtle glow, or different opacity)
- Click node -> open detail panel
- Drag to rearrange, zoom/pan, minimap
- Filter/highlight by type, subtype, tag, or search
- When analysis completes, new nodes animate into the graph via WebSocket events

### Note Analysis Flow (UX)

```
User writes note -> clicks "Analyze"
    |
    v
Frontend shows loading state with progress events
    |
    v
Backend sends note to Backboard thread
    |
    v
LLM extracts entities + relations (structured JSON)
    |
    v
Backend diffs against existing graph:
  - New entities -> create with source="ai"
  - Existing entities -> update context/tags (merge, don't overwrite)
  - New relations -> create with source="ai"
  - Existing relations -> update context if richer
    |
    v
WebSocket pushes changes to frontend
    |
    v
Graph animates in new nodes. Note status -> "analyzed"
```

---

## AI Extraction Design

### Extraction Prompt (sent to Backboard)

The Backboard assistant receives the note content and returns structured JSON:

```json
{
  "entities": [
    {
      "name": "Kim Dokja",
      "type": "character",
      "subtype": "incarnation",
      "aliases": ["Demon King of Salvation", "Most Ancient Dream"],
      "summary": "The sole reader of Ways of Survival",
      "context": "Kim Dokja is the protagonist who...",
      "tags": ["protagonist", "reader"]
    }
  ],
  "relations": [
    {
      "source": "Kim Dokja",
      "target": "Yoo Joonghyuk",
      "type": "ally_of",
      "context": "Initially adversaries, they develop a complex alliance..."
    }
  ]
}
```

### Entity Resolution

When AI extracts entities, the backend must resolve them against existing entities:

1. **Exact name match** -- same `name` -> same entity
2. **Alias match** -- extracted name matches an existing entity's alias -> same entity
3. **Fuzzy match** -- similar names flagged for user review (not auto-merged)

Unresolved entities are created as new `source="ai"` nodes. Users can merge duplicates manually.

### RAG Feedback Loop

As entities accumulate, their Backboard documents give the LLM context about the world. This means:
- Later note analyses are more accurate (the LLM "knows" the world)
- Entity resolution improves (the LLM can reference existing entities by alias)
- Relation extraction improves (the LLM understands established dynamics)

---

## Database Schema (SQLite)

```sql
CREATE TABLE worlds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    assistant_id TEXT,
    entity_types TEXT DEFAULT '[]',     -- JSON array
    relation_types TEXT DEFAULT '[]',   -- JSON array
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    subtype TEXT,
    aliases TEXT DEFAULT '[]',          -- JSON array
    context TEXT,
    summary TEXT,
    tags TEXT DEFAULT '[]',             -- JSON array
    image_url TEXT,
    source TEXT NOT NULL CHECK(source IN ('user', 'ai')),
    source_note_id TEXT REFERENCES notes(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE relations (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    source_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    context TEXT,
    weight REAL DEFAULT 0.5,
    source TEXT NOT NULL CHECK(source IN ('user', 'ai')),
    source_note_id TEXT REFERENCES notes(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    title TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'saved', 'analyzed')),
    analysis_thread_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX idx_entities_world ON entities(world_id);
CREATE INDEX idx_entities_type ON entities(world_id, type);
CREATE INDEX idx_entities_name ON entities(world_id, name);
CREATE INDEX idx_relations_world ON relations(world_id);
CREATE INDEX idx_relations_source ON relations(source_entity_id);
CREATE INDEX idx_relations_target ON relations(target_entity_id);
CREATE INDEX idx_notes_world ON notes(world_id);
```

---

## Implementation Phases

### Phase 1: Foundation (Backend Core)
- [ ] Database schema + migrations (`init_db.sql`)
- [ ] CRUD endpoints for worlds, entities, relations, notes
- [ ] Pydantic models aligned with schema
- [ ] Basic tests

### Phase 2: Frontend Shell
- [ ] Vite + React + TypeScript project setup
- [ ] World selector page
- [ ] World dashboard layout (graph canvas + side panel + notes panel)
- [ ] Graph visualization with React Flow or Cytoscape
- [ ] Entity/relation CRUD forms

### Phase 3: AI Integration
- [ ] Backboard assistant creation per world
- [ ] Note analysis endpoint (extract entities + relations)
- [ ] Entity resolution logic (name + alias matching)
- [ ] RAG document sync (entity -> Backboard document)
- [ ] WebSocket events for live graph updates during analysis

### Phase 4: Polish & Hackathon-Ready
- [ ] Analysis progress indicator
- [ ] Graph filtering and search
- [ ] Entity merge UI (for duplicate resolution)
- [ ] Visual distinction for AI vs user nodes
- [ ] Landing page with "Golden Age" narrative
- [ ] Demo world pre-loaded (e.g., a mythology or historical era)

---

## Open Questions

1. **Graph library choice** -- React Flow (simpler, React-native) vs Cytoscape.js (more powerful graph algorithms, better for large graphs). Recommendation: **React Flow** for hackathon speed, migrate to Cytoscape if needed.
2. **Rich text editor** -- TipTap (full-featured, extensible) vs Milkdown (markdown-native, lighter). Recommendation: **TipTap** for richer editing UX.
3. **Entity type icons** -- Should types have default icons/shapes, or is color-coding sufficient for the MVP?
4. **Collaborative editing** -- Out of scope for hackathon, but the Socket.IO foundation supports it later.
