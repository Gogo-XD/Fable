import type {
  World, WorldCreate,
  Entity, EntityCreate, EntityUpdate,
  Relation, RelationCreate, RelationUpdate,
  Note, NoteCreate, NoteUpdate,
  AnalysisResult, AnalyzeAllResult, GraphData,
  HistorianMessageRequest, HistorianMessageResponse,
  GuardianScanAccepted, GuardianScanRequest, GuardianRunDetail, GuardianFindingStatusUpdate,
  MechanicGenerateAccepted, MechanicGenerateRequest, MechanicRunDetail,
  TimelineMarker, TimelineMarkerCreate, TimelineMarkerUpdate, TimelineMarkerReposition,
  TimelineOperation, TimelineOperationCreate, TimelineOperationUpdate,
  TimelineRebuildResult, TimelineSnapshot, TimelineSnapshotUpsert, TimelineWorldState,
} from "./types.ts";

const BASE = "/api/lore";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// -- Worlds (placeholder until world router is built) --

export const worlds = {
  list: () => request<World[]>("/api/world/"),
  get: (id: string) => request<World>(`/api/world/${id}`),
  create: (data: WorldCreate) =>
    request<World>("/api/world/", { method: "POST", body: JSON.stringify(data) }),
  delete: (id: string) =>
    request<{ status: string }>(`/api/world/${id}`, { method: "DELETE" }),
};

// -- Entities --

export const entities = {
  list: (worldId: string, params?: { type?: string; tag?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.type) q.set("type", params.type);
    if (params?.tag) q.set("tag", params.tag);
    if (params?.search) q.set("search", params.search);
    const qs = q.toString();
    return request<Entity[]>(`${BASE}/${worldId}/entities${qs ? `?${qs}` : ""}`);
  },
  get: (worldId: string, id: string) =>
    request<Entity>(`${BASE}/${worldId}/entities/${id}`),
  create: (worldId: string, data: EntityCreate) =>
    request<Entity>(`${BASE}/${worldId}/entities`, { method: "POST", body: JSON.stringify(data) }),
  update: (worldId: string, id: string, data: EntityUpdate) =>
    request<Entity>(`${BASE}/${worldId}/entities/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (worldId: string, id: string) =>
    request<{ status: string }>(`${BASE}/${worldId}/entities/${id}`, { method: "DELETE" }),
};

// -- Relations --

export const relations = {
  list: (worldId: string, params?: { entity_id?: string; type?: string }) => {
    const q = new URLSearchParams();
    if (params?.entity_id) q.set("entity_id", params.entity_id);
    if (params?.type) q.set("type", params.type);
    const qs = q.toString();
    return request<Relation[]>(`${BASE}/${worldId}/relations${qs ? `?${qs}` : ""}`);
  },
  create: (worldId: string, data: RelationCreate) =>
    request<Relation>(`${BASE}/${worldId}/relations`, { method: "POST", body: JSON.stringify(data) }),
  update: (worldId: string, id: string, data: RelationUpdate) =>
    request<Relation>(`${BASE}/${worldId}/relations/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (worldId: string, id: string) =>
    request<{ status: string }>(`${BASE}/${worldId}/relations/${id}`, { method: "DELETE" }),
};

// -- Notes --

export const notes = {
  list: (worldId: string) =>
    request<Note[]>(`${BASE}/${worldId}/notes`),
  get: (worldId: string, id: string) =>
    request<Note>(`${BASE}/${worldId}/notes/${id}`),
  create: (worldId: string, data: NoteCreate) =>
    request<Note>(`${BASE}/${worldId}/notes`, { method: "POST", body: JSON.stringify(data) }),
  update: (worldId: string, id: string, data: NoteUpdate) =>
    request<Note>(`${BASE}/${worldId}/notes/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (worldId: string, id: string) =>
    request<{ status: string }>(`${BASE}/${worldId}/notes/${id}`, { method: "DELETE" }),
  analyze: (worldId: string, id: string) =>
    request<AnalysisResult>(`${BASE}/${worldId}/notes/${id}/analyze`, { method: "POST" }),
  analyzeAll: (worldId: string) =>
    request<AnalyzeAllResult>(`${BASE}/${worldId}/notes/analyze-all`, { method: "POST" }),
};

// -- Graph --
export const historian = {
  message: (worldId: string, data: HistorianMessageRequest) =>
    request<HistorianMessageResponse>(`/api/historian/${worldId}/message`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
export const canonGuardian = {
  scanWorld: (worldId: string, data: GuardianScanRequest) =>
    request<GuardianScanAccepted>(`/api/guardian/${worldId}/scan`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getRun: (worldId: string, runId: string, params?: { include_details?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.include_details !== undefined) {
      q.set("include_details", String(params.include_details));
    }
    const qs = q.toString();
    return request<GuardianRunDetail>(`/api/guardian/${worldId}/runs/${runId}${qs ? `?${qs}` : ""}`);
  },
  dismissFinding: (worldId: string, runId: string, findingId: string) =>
    request<GuardianFindingStatusUpdate>(
      `/api/guardian/${worldId}/runs/${runId}/findings/${findingId}/dismiss`,
      { method: "POST" },
    ),
  generateMechanic: (worldId: string, runId: string, data: MechanicGenerateRequest) =>
    request<MechanicGenerateAccepted>(`/api/guardian/${worldId}/runs/${runId}/mechanic/generate`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getMechanicRun: (worldId: string, mechanicRunId: string, params?: { include_options?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.include_options !== undefined) {
      q.set("include_options", String(params.include_options));
    }
    const qs = q.toString();
    return request<MechanicRunDetail>(
      `/api/guardian/${worldId}/mechanic/${mechanicRunId}${qs ? `?${qs}` : ""}`,
    );
  },
};

export const graph = {
  get: (worldId: string) =>
    request<GraphData>(`/api/graph/${worldId}`),
};

// -- Timeline --

export const timeline = {
  listMarkers: (worldId: string, params?: { include_operations?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.include_operations) q.set("include_operations", "true");
    const qs = q.toString();
    return request<TimelineMarker[]>(`/api/timeline/${worldId}/markers${qs ? `?${qs}` : ""}`);
  },
  getMarker: (worldId: string, markerId: string, params?: { include_operations?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.include_operations !== undefined) {
      q.set("include_operations", String(params.include_operations));
    }
    const qs = q.toString();
    return request<TimelineMarker>(
      `/api/timeline/${worldId}/markers/${markerId}${qs ? `?${qs}` : ""}`,
    );
  },
  createMarker: (worldId: string, data: TimelineMarkerCreate) =>
    request<TimelineMarker>(`/api/timeline/${worldId}/markers`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateMarker: (worldId: string, markerId: string, data: TimelineMarkerUpdate) =>
    request<TimelineMarker>(`/api/timeline/${worldId}/markers/${markerId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  repositionMarker: (worldId: string, markerId: string, data: TimelineMarkerReposition) =>
    request<TimelineMarker>(`/api/timeline/${worldId}/markers/${markerId}/reposition`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteMarker: (worldId: string, markerId: string) =>
    request<{ status: string; marker_id: string }>(`/api/timeline/${worldId}/markers/${markerId}`, {
      method: "DELETE",
    }),
  listOperations: (worldId: string, markerId: string) =>
    request<TimelineOperation[]>(`/api/timeline/${worldId}/markers/${markerId}/operations`),
  createOperation: (worldId: string, markerId: string, data: TimelineOperationCreate) =>
    request<TimelineOperation>(`/api/timeline/${worldId}/markers/${markerId}/operations`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateOperation: (
    worldId: string,
    markerId: string,
    operationId: string,
    data: TimelineOperationUpdate,
  ) =>
    request<TimelineOperation>(
      `/api/timeline/${worldId}/markers/${markerId}/operations/${operationId}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    ),
  deleteOperation: (worldId: string, markerId: string, operationId: string) =>
    request<{ status: string; operation_id: string }>(
      `/api/timeline/${worldId}/markers/${markerId}/operations/${operationId}`,
      { method: "DELETE" },
    ),
  rebuild: (worldId: string) =>
    request<TimelineRebuildResult>(`/api/timeline/${worldId}/rebuild`, {
      method: "POST",
    }),
  getState: (worldId: string, params?: { marker_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.marker_id) q.set("marker_id", params.marker_id);
    const qs = q.toString();
    return request<TimelineWorldState>(`/api/timeline/${worldId}/state${qs ? `?${qs}` : ""}`);
  },
  listSnapshots: (worldId: string) =>
    request<TimelineSnapshot[]>(`/api/timeline/${worldId}/snapshots`),
  getSnapshot: (worldId: string, markerId: string) =>
    request<TimelineSnapshot>(`/api/timeline/${worldId}/snapshots/${markerId}`),
  upsertSnapshot: (worldId: string, markerId: string, data: TimelineSnapshotUpsert) =>
    request<TimelineSnapshot>(`/api/timeline/${worldId}/snapshots/${markerId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  generateSnapshot: (worldId: string, markerId: string) =>
    request<TimelineSnapshot>(`/api/timeline/${worldId}/snapshots/${markerId}/generate`, {
      method: "POST",
    }),
};

