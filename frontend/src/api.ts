import type {
  World, WorldCreate,
  Entity, EntityCreate, EntityUpdate,
  Relation, RelationCreate, RelationUpdate,
  Note, NoteCreate, NoteUpdate,
  AnalysisResult, GraphData,
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

// ── Worlds (placeholder until world router is built) ──

export const worlds = {
  list: () => request<World[]>("/api/world/"),
  get: (id: string) => request<World>(`/api/world/${id}`),
  create: (data: WorldCreate) =>
    request<World>("/api/world/", { method: "POST", body: JSON.stringify(data) }),
  delete: (id: string) =>
    request<{ status: string }>(`/api/world/${id}`, { method: "DELETE" }),
};

// ── Entities ──

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

// ── Relations ──

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

// ── Notes ──

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
};

// ── Graph ──

export const graph = {
  get: (worldId: string) =>
    request<GraphData>(`/api/graph/${worldId}`),
};
