export interface World {
  id: string;
  name: string;
  description: string | null;
  assistant_id: string | null;
  entity_types: string[];
  relation_types: string[];
  created_at: string;
  updated_at: string;
}

export interface WorldCreate {
  name: string;
  description?: string;
}

export interface Entity {
  id: string;
  world_id: string;
  name: string;
  type: string;
  subtype: string | null;
  aliases: string[];
  context: string | null;
  summary: string | null;
  tags: string[];
  image_url: string | null;
  source: "user" | "ai";
  source_note_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface EntityCreate {
  name: string;
  type: string;
  subtype?: string;
  aliases?: string[];
  context?: string;
  summary?: string;
  tags?: string[];
}

export interface EntityUpdate {
  name?: string;
  type?: string;
  subtype?: string;
  aliases?: string[];
  context?: string;
  summary?: string;
  tags?: string[];
}

export interface Relation {
  id: string;
  world_id: string;
  source_entity_id: string;
  target_entity_id: string;
  type: string;
  context: string | null;
  weight: number;
  source: "user" | "ai";
  source_note_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RelationCreate {
  source_entity_id: string;
  target_entity_id: string;
  type: string;
  context?: string;
  weight?: number;
}

export interface RelationUpdate {
  type?: string;
  context?: string;
  weight?: number;
}

export interface Note {
  id: string;
  world_id: string;
  title: string | null;
  content: string;
  status: "draft" | "saved" | "analyzed";
  analysis_thread_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface NoteCreate {
  title?: string;
  content: string;
}

export interface NoteUpdate {
  title?: string;
  content?: string;
}

export interface AnalysisResult {
  entities_created: number;
  entities_updated: number;
  relations_created: number;
}

export interface GraphData {
  entities: Entity[];
  relations: Relation[];
}

/** Maps entity type -> color for graph nodes */
export const NODE_COLORS: Record<string, string> = {
  character: "var(--color-node-character)",
  location: "var(--color-node-location)",
  event: "var(--color-node-event)",
  item: "var(--color-node-item)",
  organization: "var(--color-node-organization)",
  concept: "var(--color-node-concept)",
};

export function getNodeColor(type: string): string {
  return NODE_COLORS[type] ?? "var(--color-node-default)";
}
