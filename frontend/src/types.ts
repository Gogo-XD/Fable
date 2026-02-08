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
  status: string;
  exists_at_marker: boolean;
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
  status?: string;
}

export interface EntityUpdate {
  name?: string;
  type?: string;
  subtype?: string;
  aliases?: string[];
  context?: string;
  summary?: string;
  tags?: string[];
  status?: string;
}

export interface Relation {
  id: string;
  world_id: string;
  source_entity_id: string;
  target_entity_id: string;
  type: string;
  context: string | null;
  weight: number;
  exists_at_marker: boolean;
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
  timeline_markers_created: number;
}

export interface AnalyzeAllResult {
  notes_total: number;
  notes_skipped: number;
  notes_analyzed: number;
  notes_failed: number;
  entities_created: number;
  entities_updated: number;
  relations_created: number;
  timeline_markers_created: number;
  failed_note_ids: string[];
  last_analyzed_note_id?: string | null;
}

export interface HistorianMessageRequest {
  message: string;
  thread_id?: string;
}

export interface HistorianMessageResponse {
  thread_id: string;
  response: string;
  rag_refreshed: boolean;
  rag_compile_status: string | null;
  rag_compile_error: string | null;
}

export interface GuardianScanRequest {
  marker_id?: string;
  trigger_kind?: "note_scan" | "manual" | "api";
  include_soft_checks?: boolean;
  include_llm_critic?: boolean;
  max_context_tokens?: number;
  max_findings?: number;
  dry_run?: boolean;
}

export interface GuardianScanAccepted {
  run_id: string;
  world_id: string;
  status: string;
  created_at: string;
}

export interface GuardianEvidenceRef {
  kind: "note" | "entity" | "relation" | "timeline_marker" | "timeline_operation" | "world";
  id: string;
  snippet?: string | null;
}

export interface GuardianFinding {
  id: string;
  run_id: string;
  world_id: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  finding_code: string;
  title: string;
  detail: string;
  confidence: number;
  resolution_status: "open" | "accepted" | "dismissed" | "applied";
  evidence: GuardianEvidenceRef[];
  suggested_action_count: number;
  created_at: string;
  updated_at: string;
}

export interface GuardianAction {
  id: string;
  run_id: string;
  finding_id?: string | null;
  world_id: string;
  action_type:
    | "timeline_operation"
    | "entity_patch"
    | "relation_patch"
    | "entity_delete"
    | "relation_delete"
    | "world_patch"
    | "noop";
  op_type?: string | null;
  target_kind?: string | null;
  target_id?: string | null;
  payload: Record<string, unknown>;
  rationale?: string | null;
  status: "proposed" | "accepted" | "applied" | "rejected" | "failed";
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface GuardianRunDetail {
  id: string;
  world_id: string;
  trigger_kind: "note_scan" | "manual" | "api";
  status: string;
  request: Record<string, unknown>;
  summary?: Record<string, unknown> | null;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  findings: GuardianFinding[];
  actions: GuardianAction[];
}

export interface GuardianFindingStatusUpdate {
  status: string;
  run_id: string;
  world_id: string;
  finding_id: string;
  resolution_status: "open" | "accepted" | "dismissed" | "applied";
}

export interface MechanicGenerateRequest {
  finding_ids?: string[];
  include_open_findings?: boolean;
  max_options?: number;
  max_context_tokens?: number;
  confidence_threshold?: number;
}

export interface MechanicGenerateAccepted {
  status: string;
  mechanic_run_id: string;
  world_id: string;
  run_id: string;
  created_at: string;
}

export interface MechanicAcceptRequest {
  option_ids?: string[];
  accept_all?: boolean;
  create_guardian_actions?: boolean;
  apply_immediately?: boolean;
}

export interface MechanicAcceptResult {
  status: string;
  mechanic_run_id: string;
  world_id: string;
  run_id: string;
  requested_options: number;
  accepted_options: number;
  actions_created: number;
  actions_failed: number;
  applied_options: number;
  apply_failures: number;
  message?: string | null;
}

export interface MechanicOption {
  id: string;
  mechanic_run_id: string;
  world_id: string;
  run_id: string;
  finding_id?: string | null;
  option_index: number;
  action_type:
    | "timeline_operation"
    | "entity_patch"
    | "relation_patch"
    | "entity_delete"
    | "relation_delete"
    | "world_patch"
    | "noop";
  op_type?: string | null;
  target_kind?: string | null;
  target_id?: string | null;
  payload: Record<string, unknown>;
  rationale?: string | null;
  expected_outcome?: string | null;
  risk_level: "low" | "medium" | "high";
  confidence: number;
  status: "proposed" | "accepted" | "rejected" | "applied" | "failed";
  mapped_action_id?: string | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MechanicRunDetail {
  id: string;
  world_id: string;
  run_id: string;
  status: string;
  request: Record<string, unknown>;
  summary?: Record<string, unknown> | null;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  options: MechanicOption[];
}

export interface GraphData {
  entities: Entity[];
  relations: Relation[];
}

export type TimelineMarkerKind = "explicit" | "semantic";
export type TimelinePlacementStatus = "placed" | "unplaced";
export type TimelineTargetKind = "entity" | "relation" | "world";

export interface TimelineOperation {
  id: string;
  world_id: string;
  marker_id: string;
  op_type: string;
  target_kind: TimelineTargetKind;
  target_id: string | null;
  payload: Record<string, unknown>;
  order_index: number;
  created_at: string;
  updated_at: string;
}

export interface TimelineOperationCreate {
  op_type: string;
  target_kind: TimelineTargetKind;
  target_id?: string;
  payload?: Record<string, unknown>;
  order_index?: number;
}

export interface TimelineOperationUpdate {
  op_type?: string;
  target_kind?: TimelineTargetKind;
  target_id?: string;
  payload?: Record<string, unknown>;
  order_index?: number;
}

export interface TimelineMarker {
  id: string;
  world_id: string;
  title: string;
  summary: string | null;
  marker_kind: TimelineMarkerKind;
  placement_status: TimelinePlacementStatus;
  date_label: string | null;
  date_sort_value: number | null;
  sort_key: number;
  source: "user" | "ai";
  source_note_id: string | null;
  created_at: string;
  updated_at: string;
  operations: TimelineOperation[];
}

export interface TimelineMarkerCreate {
  title: string;
  summary?: string;
  marker_kind?: TimelineMarkerKind;
  placement_status?: TimelinePlacementStatus;
  date_label?: string;
  date_sort_value?: number;
  sort_key?: number;
  source?: "user" | "ai";
  source_note_id?: string;
  operations?: TimelineOperationCreate[];
}

export interface TimelineMarkerUpdate {
  title?: string;
  summary?: string;
  marker_kind?: TimelineMarkerKind;
  placement_status?: TimelinePlacementStatus;
  date_label?: string;
  date_sort_value?: number;
  sort_key?: number;
  source_note_id?: string;
}

export interface TimelineMarkerReposition {
  sort_key: number;
  placement_status?: TimelinePlacementStatus;
}

export interface TimelineSnapshot {
  id: string;
  world_id: string;
  marker_id: string;
  state_json: Record<string, unknown>;
  state_hash: string | null;
  applied_marker_count: number;
  entity_count: number;
  relation_count: number;
  created_at: string;
  updated_at: string;
}

export interface TimelineSnapshotUpsert {
  state_json: Record<string, unknown>;
  state_hash?: string;
  applied_marker_count?: number;
  entity_count?: number;
  relation_count?: number;
}

export interface TimelineWorldState {
  world_id: string;
  marker_id: string | null;
  applied_marker_count: number;
  entities: Entity[];
  relations: Relation[];
  from_snapshot_marker_id: string | null;
  note: string | null;
}

export interface TimelineRebuildResult {
  status: string;
  world_id: string;
  marker_count: number;
  snapshot_count: number;
  rebuilt_at: string;
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
