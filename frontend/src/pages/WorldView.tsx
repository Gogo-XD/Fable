import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Network, BookOpen, Plus, Link, FilterX, Shield, MessageSquare } from "lucide-react";
import {
  canonGuardian as canonGuardianApi,
  graph as graphApi,
  entities as entitiesApi,
  relations as relationsApi,
  notes as notesApi,
  timeline as timelineApi,
} from "../api.ts";
import type {
  Entity,
  Relation,
  Note,
  GraphData,
  TimelineMarker,
  EntityUpdate,
  RelationUpdate,
  NoteCreate,
  NoteUpdate,
  AnalysisResult,
  AnalyzeAllResult,
  GuardianRunDetail,
  MechanicRunDetail,
} from "../types.ts";
import WorldGraph from "../components/WorldGraph.tsx";
import SidePanel from "../components/SidePanel.tsx";
import EntityDetail from "../components/EntityDetail.tsx";
import EntityCreateForm from "../components/EntityCreateForm.tsx";
import RelationCreateForm from "../components/RelationCreateForm.tsx";
import RelationDetail from "../components/RelationDetail.tsx";
import NotePanel from "../components/NotePanel.tsx";
import GuardianPanel from "../components/GuardianPanel.tsx";
import HistorianPanel from "../components/HistorianPanel.tsx";
import TimelineStrip from "../components/TimelineStrip.tsx";
import TimelineMarkerOpsPanel from "../components/TimelineMarkerOpsPanel.tsx";

type PanelMode =
  | { kind: "none" }
  | { kind: "create-entity" }
  | { kind: "create-relation" }
  | { kind: "relation-detail"; relationId: string }
  | { kind: "notes" }
  | { kind: "historian" }
  | { kind: "guardian" }
  | { kind: "timeline-operations"; markerId: string };

type SearchMatch = {
  entity: Entity;
  score: number;
};

const DEFAULT_GUARDIAN_SCAN_REQUEST = {
  trigger_kind: "manual",
  include_soft_checks: true,
  include_llm_critic: true,
  dry_run: false,
} as const;

const DEFAULT_MECHANIC_GENERATE_REQUEST = {
  include_open_findings: true,
} as const;

function sortedPlacedMarkers(markers: TimelineMarker[]): TimelineMarker[] {
  return markers
    .filter((marker) => marker.placement_status === "placed")
    .sort(
      (a, b) =>
        a.sort_key - b.sort_key ||
        a.created_at.localeCompare(b.created_at) ||
        a.id.localeCompare(b.id),
    );
}

function fuzzyScore(value: string, query: string): number | null {
  const target = value.toLowerCase();
  const needle = query.trim().toLowerCase();
  if (!needle) return null;

  const containsIdx = target.indexOf(needle);
  if (containsIdx >= 0) {
    return 100 - containsIdx * 2 - Math.max(0, target.length - needle.length);
  }

  let queryIdx = 0;
  let firstMatch = -1;
  let lastMatch = -1;
  for (let i = 0; i < target.length && queryIdx < needle.length; i += 1) {
    if (target[i] === needle[queryIdx]) {
      if (firstMatch < 0) firstMatch = i;
      lastMatch = i;
      queryIdx += 1;
    }
  }

  if (queryIdx !== needle.length) return null;
  const span = lastMatch - firstMatch + 1;
  const gaps = span - needle.length;
  return 60 - gaps - firstMatch;
}

function rankEntity(entity: Entity, query: string): number | null {
  const scores: number[] = [];
  const nameScore = fuzzyScore(entity.name, query);
  if (nameScore !== null) scores.push(nameScore + 20);

  for (const alias of entity.aliases) {
    const aliasScore = fuzzyScore(alias, query);
    if (aliasScore !== null) scores.push(aliasScore + 10);
  }

  const typeScore = fuzzyScore(entity.type, query);
  if (typeScore !== null) scores.push(typeScore);

  for (const tag of entity.tags) {
    const tagScore = fuzzyScore(tag, query);
    if (tagScore !== null) scores.push(tagScore);
  }

  if (scores.length === 0) return null;
  return Math.max(...scores);
}

export default function WorldView() {
  const { worldId, entityId } = useParams<{
    worldId: string;
    entityId?: string;
  }>();
  const navigate = useNavigate();

  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [notesList, setNotesList] = useState<Note[] | null>(null);
  const [timelineMarkers, setTimelineMarkers] = useState<TimelineMarker[] | null>(null);
  const [activeTimelineMarkerId, setActiveTimelineMarkerId] = useState("");
  const [panel, setPanel] = useState<PanelMode>({ kind: "none" });
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [entityTypeFilter, setEntityTypeFilter] = useState("all");
  const [relationTypeFilter, setRelationTypeFilter] = useState("all");
  const [focusEntityId, setFocusEntityId] = useState("");
  const [runningGuardian, setRunningGuardian] = useState(false);
  const [guardianRun, setGuardianRun] = useState<GuardianRunDetail | null>(null);
  const [guardianError, setGuardianError] = useState<string | null>(null);
  const [expandedFindingIds, setExpandedFindingIds] = useState<Set<string>>(new Set());
  const [dismissingFindingId, setDismissingFindingId] = useState<string | null>(null);
  const [runningMechanicFindingId, setRunningMechanicFindingId] = useState<string | null>(null);
  const [runningMechanicOptionId, setRunningMechanicOptionId] = useState<string | null>(null);
  const [mechanicRunsByFinding, setMechanicRunsByFinding] = useState<Record<string, MechanicRunDetail>>({});
  const [mechanicErrorByFinding, setMechanicErrorByFinding] = useState<Record<string, string>>({});
  const suppressMarkerReloadRef = useRef(false);
  const activeMarkerIdRef = useRef("");
  const reloadRequestIdRef = useRef(0);

  useEffect(() => {
    activeMarkerIdRef.current = activeTimelineMarkerId;
  }, [activeTimelineMarkerId]);

  const reload = useCallback(async (options?: { markerId?: string; rebuildTimeline?: boolean }) => {
    if (!worldId) return;
    const requestId = ++reloadRequestIdRef.current;
    const isStale = () => requestId !== reloadRequestIdRef.current;
    const markerId = options?.markerId ?? "";
    if (options?.rebuildTimeline) {
      await timelineApi.rebuild(worldId);
      if (isStale()) return;
    }

    const [n, markers] = await Promise.all([
      notesApi.list(worldId),
      timelineApi.listMarkers(worldId),
    ]);
    if (isStale()) return;
    const placedMarkers = sortedPlacedMarkers(markers);

    let effectiveMarkerId = markerId;
    if (effectiveMarkerId && !markers.some((marker) => marker.id === effectiveMarkerId)) {
      effectiveMarkerId = "";
    }
    if (!effectiveMarkerId && placedMarkers.length > 0) {
      effectiveMarkerId = placedMarkers[0].id;
    }
    if (!isStale() && effectiveMarkerId !== activeMarkerIdRef.current) {
      setActiveTimelineMarkerId(effectiveMarkerId);
    }

    let g: GraphData;
    if (effectiveMarkerId) {
      try {
        const state = await timelineApi.getState(worldId, { marker_id: effectiveMarkerId });
        if (isStale()) return;
        g = { entities: state.entities, relations: state.relations };
      } catch {
        if (isStale()) return;
        const fallbackMarkerId = placedMarkers[0]?.id ?? "";
        if (!isStale() && fallbackMarkerId !== activeMarkerIdRef.current) {
          setActiveTimelineMarkerId(fallbackMarkerId);
        }
        g = await graphApi.get(worldId);
        if (isStale()) return;
      }
    } else {
      g = await graphApi.get(worldId);
      if (isStale()) return;
    }

    if (isStale()) return;
    setGraphData(g);
    setNotesList(n);
    setTimelineMarkers(markers);
  }, [worldId]);

  useEffect(() => {
    if (!worldId) return;
    suppressMarkerReloadRef.current = true;
    const timer = window.setTimeout(() => {
      void reload({ markerId: "", rebuildTimeline: true })
        .finally(() => {
          suppressMarkerReloadRef.current = false;
          const selectedMarkerId = activeMarkerIdRef.current;
          if (selectedMarkerId) {
            void reload({ markerId: selectedMarkerId });
          }
        });
    }, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, [worldId, reload]);

  useEffect(() => {
    if (!worldId || suppressMarkerReloadRef.current) return;
    const timer = window.setTimeout(() => {
      void reload({ markerId: activeTimelineMarkerId });
    }, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, [worldId, activeTimelineMarkerId, reload]);

  const routeEntity = useMemo(
    () =>
      entityId && graphData
        ? (graphData.entities.find((e) => e.id === entityId) ?? null)
        : null,
    [entityId, graphData],
  );
  const selectedRelation = useMemo<Relation | null>(() => {
    if (!graphData || panel.kind !== "relation-detail") return null;
    return graphData.relations.find((r) => r.id === panel.relationId) ?? null;
  }, [graphData, panel]);
  const entityById = useMemo(
    () => new Map(graphData?.entities.map((e) => [e.id, e])),
    [graphData],
  );
  const panelTimelineMarker = useMemo(
    () =>
      panel.kind === "timeline-operations"
        ? timelineMarkers?.find((marker) => marker.id === panel.markerId) ?? null
        : null,
    [panel, timelineMarkers],
  );

  const availableEntityTypes = useMemo(
    () => ["all", ...new Set(graphData?.entities.map((e) => e.type) ?? [])],
    [graphData],
  );
  const availableRelationTypes = useMemo(
    () => ["all", ...new Set(graphData?.relations.map((r) => r.type) ?? [])],
    [graphData],
  );

  const baseFilteredEntities = useMemo(() => {
    if (!graphData) return [];
    if (entityTypeFilter === "all") return graphData.entities;
    return graphData.entities.filter((e) => e.type === entityTypeFilter);
  }, [graphData, entityTypeFilter]);
  const effectiveFocusEntityId = useMemo(() => {
    if (!focusEntityId) return "";
    return baseFilteredEntities.some((e) => e.id === focusEntityId)
      ? focusEntityId
      : "";
  }, [focusEntityId, baseFilteredEntities]);

  const filteredGraph = useMemo(() => {
    if (!graphData) return { entities: [], relations: [] };

    const visibleEntityIds = new Set(baseFilteredEntities.map((e) => e.id));
    const typeFilteredRelations = graphData.relations.filter((r) => {
      if (relationTypeFilter !== "all" && r.type !== relationTypeFilter) {
        return false;
      }
      return (
        visibleEntityIds.has(r.source_entity_id) &&
        visibleEntityIds.has(r.target_entity_id)
      );
    });

    if (!effectiveFocusEntityId || !visibleEntityIds.has(effectiveFocusEntityId)) {
      return {
        entities: baseFilteredEntities,
        relations: typeFilteredRelations,
      };
    }

    const focusedRelations = typeFilteredRelations.filter(
      (r) =>
        r.source_entity_id === effectiveFocusEntityId ||
        r.target_entity_id === effectiveFocusEntityId,
    );
    const neighborhoodIds = new Set<string>([effectiveFocusEntityId]);
    for (const rel of focusedRelations) {
      neighborhoodIds.add(rel.source_entity_id);
      neighborhoodIds.add(rel.target_entity_id);
    }

    return {
      entities: baseFilteredEntities.filter((e) => neighborhoodIds.has(e.id)),
      relations: focusedRelations,
    };
  }, [graphData, baseFilteredEntities, relationTypeFilter, effectiveFocusEntityId]);

  const activeEntityIdForGraph = useMemo(() => {
    if (!routeEntity) return undefined;
    return filteredGraph.entities.some((e) => e.id === routeEntity.id)
      ? routeEntity.id
      : undefined;
  }, [routeEntity, filteredGraph.entities]);

  const searchMatches = useMemo<SearchMatch[]>(() => {
    if (!graphData) return [];
    const query = searchQuery.trim();
    if (!query) return [];

    return graphData.entities
      .map((entity) => {
        const score = rankEntity(entity, query);
        return score === null ? null : { entity, score };
      })
      .filter((item): item is SearchMatch => item !== null)
      .sort(
        (a, b) =>
          b.score - a.score || a.entity.name.localeCompare(b.entity.name),
      )
      .slice(0, 8);
  }, [graphData, searchQuery]);

  const clearEntityRoute = useCallback(() => {
    if (!worldId) return;
    navigate(`/world/${worldId}`);
  }, [navigate, worldId]);

  const openEntityRoute = useCallback(
    (id: string) => {
      if (!worldId) return;
      navigate(`/world/${worldId}/entity/${id}`);
    },
    [navigate, worldId],
  );

  const handleSelectEntity = useCallback(
    (id: string) => {
      setPanel({ kind: "none" });
      openEntityRoute(id);
    },
    [openEntityRoute],
  );

  const handleSelectRelation = useCallback(
    (id: string) => {
      if (!worldId) return;
      navigate(`/world/${worldId}`);
      setPanel({ kind: "relation-detail", relationId: id });
    },
    [navigate, worldId],
  );

  async function handleUpdateEntity(id: string, data: EntityUpdate) {
    if (!worldId) return;
    const updated = await entitiesApi.update(worldId, id, data);
    setGraphData((prev) =>
      prev
        ? {
            ...prev,
            entities: prev.entities.map((e) => (e.id === id ? updated : e)),
          }
        : prev,
    );
  }

  async function handleCreateEntity(
    data: Parameters<typeof entitiesApi.create>[1],
  ) {
    if (!worldId) return;
    const created = await entitiesApi.create(worldId, data);
    setGraphData((prev) =>
      prev
        ? {
            ...prev,
            entities: [...prev.entities, created],
          }
        : prev,
    );
    setPanel({ kind: "none" });
    openEntityRoute(created.id);
  }

  async function handleDeleteEntity(id: string) {
    if (!worldId) return;
    const ok = window.confirm(
      "Delete this entity? Connected relations will also be removed from this view.",
    );
    if (!ok) return;

    await entitiesApi.delete(worldId, id);
    setGraphData((prev) =>
      prev
        ? {
            ...prev,
            entities: prev.entities.filter((e) => e.id !== id),
            relations: prev.relations.filter(
              (r) => r.source_entity_id !== id && r.target_entity_id !== id,
            ),
          }
        : prev,
    );
    setPanel({ kind: "none" });
    clearEntityRoute();
  }

  async function handleCreateRelation(
    data: Parameters<typeof relationsApi.create>[1],
  ) {
    if (!worldId) return;
    const created = await relationsApi.create(worldId, data);
    setGraphData((prev) =>
      prev
        ? {
            ...prev,
            relations: [...prev.relations, created],
          }
        : prev,
    );
    setPanel({ kind: "none" });
  }

  async function handleUpdateRelation(id: string, data: RelationUpdate) {
    if (!worldId) return;
    const updated = await relationsApi.update(worldId, id, data);
    setGraphData((prev) =>
      prev
        ? {
            ...prev,
            relations: prev.relations.map((r) => (r.id === id ? updated : r)),
          }
        : prev,
    );
  }

  async function handleCreateNote(data: NoteCreate) {
    if (!worldId) return;
    const created = await notesApi.create(worldId, data);
    setNotesList((prev) => (prev ? [created, ...prev] : [created]));
  }

  async function handleUpdateNote(id: string, data: NoteUpdate) {
    if (!worldId) return;
    const updated = await notesApi.update(worldId, id, data);
    setNotesList((prev) =>
      prev ? prev.map((n) => (n.id === id ? updated : n)) : prev,
    );
  }

  async function handleAnalyzeNote(id: string): Promise<AnalysisResult> {
    if (!worldId) throw new Error("No world");
    const result = await notesApi.analyze(worldId, id);
    // Reload graph to pick up new entities/relations
    await reload({ markerId: activeTimelineMarkerId });
    return result;
  }

  async function handleAnalyzeAllNotes(): Promise<AnalyzeAllResult> {
    if (!worldId) throw new Error("No world");
    const result = await notesApi.analyzeAll(worldId);
    await reload({ markerId: activeTimelineMarkerId });
    return result;
  }

  async function handleRunGuardian(): Promise<void> {
    if (!worldId) throw new Error("No world");
    setRunningGuardian(true);
    setGuardianError(null);
    setRunningMechanicOptionId(null);
    setMechanicRunsByFinding({});
    setMechanicErrorByFinding({});
    try {
      const scanResult = await canonGuardianApi.scanWorld(worldId, DEFAULT_GUARDIAN_SCAN_REQUEST);
      const run = await canonGuardianApi.getRun(worldId, scanResult.run_id, { include_details: true });
      setGuardianRun(run);
      setExpandedFindingIds(new Set(run.findings.map((finding) => finding.id)));
      if (run.status === "failed") {
        setGuardianError(run.error || "Guardian run failed");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to run guardian";
      setGuardianError(message);
    } finally {
      setRunningGuardian(false);
    }
  }

  function handleToggleGuardianFindingExpanded(findingId: string): void {
    setExpandedFindingIds((prev) => {
      const next = new Set(prev);
      if (next.has(findingId)) {
        next.delete(findingId);
      } else {
        next.add(findingId);
      }
      return next;
    });
  }

  async function handleDismissGuardianFinding(findingId: string): Promise<void> {
    if (!worldId) throw new Error("No world");
    if (!guardianRun) return;
    setDismissingFindingId(findingId);
    setGuardianError(null);
    try {
      await canonGuardianApi.dismissFinding(worldId, guardianRun.id, findingId);
      setGuardianRun((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          findings: prev.findings.map((finding) =>
            finding.id === findingId
              ? { ...finding, resolution_status: "dismissed" }
              : finding,
          ),
        };
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to dismiss finding";
      setGuardianError(message);
    } finally {
      setDismissingFindingId(null);
    }
  }

  async function handleRunMechanicForFinding(findingId: string): Promise<void> {
    if (!worldId) throw new Error("No world");
    if (!guardianRun) return;
    setRunningMechanicFindingId(findingId);
    setMechanicErrorByFinding((prev) => {
      const next = { ...prev };
      delete next[findingId];
      return next;
    });
    try {
      const generated = await canonGuardianApi.generateMechanic(
        worldId,
        guardianRun.id,
        {
          ...DEFAULT_MECHANIC_GENERATE_REQUEST,
          include_open_findings: false,
          finding_ids: [findingId],
        },
      );
      const mechanicRun = await canonGuardianApi.getMechanicRun(
        worldId,
        generated.mechanic_run_id,
        { include_options: true },
      );
      setMechanicRunsByFinding((prev) => ({ ...prev, [findingId]: mechanicRun }));
      setExpandedFindingIds((prev) => new Set(prev).add(findingId));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to run mechanic";
      setMechanicErrorByFinding((prev) => ({ ...prev, [findingId]: message }));
    } finally {
      setRunningMechanicFindingId(null);
    }
  }

  async function handleRunMechanicOption(findingId: string, optionId: string): Promise<void> {
    if (!worldId) throw new Error("No world");
    if (!guardianRun) return;
    const mechanicRun = mechanicRunsByFinding[findingId];
    if (!mechanicRun) return;

    setRunningMechanicOptionId(optionId);
    setMechanicErrorByFinding((prev) => {
      const next = { ...prev };
      delete next[findingId];
      return next;
    });

    try {
      const result = await canonGuardianApi.acceptMechanic(worldId, mechanicRun.id, {
        option_ids: [optionId],
        accept_all: false,
        create_guardian_actions: true,
        apply_immediately: true,
      });
      const [updatedMechanicRun, updatedGuardianRun] = await Promise.all([
        canonGuardianApi.getMechanicRun(worldId, mechanicRun.id, { include_options: true }),
        canonGuardianApi.getRun(worldId, guardianRun.id, { include_details: true }),
      ]);
      setMechanicRunsByFinding((prev) => ({ ...prev, [findingId]: updatedMechanicRun }));
      setGuardianRun(updatedGuardianRun);
      setExpandedFindingIds((prev) => new Set(prev).add(findingId));
      await reload({ markerId: activeMarkerIdRef.current });

      if (result.apply_failures > 0 && result.message) {
        setMechanicErrorByFinding((prev) => ({ ...prev, [findingId]: result.message || "One or more options failed to apply." }));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to run mechanic option";
      setMechanicErrorByFinding((prev) => ({ ...prev, [findingId]: message }));
    } finally {
      setRunningMechanicOptionId(null);
    }
  }

  async function handleRepositionTimelineMarker(
    markerId: string,
    newSortKey: number,
    placementStatus: "placed" | "unplaced" = "placed",
  ) {
    if (!worldId) return;
    const previousMarkers = timelineMarkers;

    // Optimistically update marker ordering locally to avoid snap-back flicker.
    setTimelineMarkers((prev) =>
      prev
        ? prev.map((marker) =>
            marker.id === markerId
              ? {
                  ...marker,
                  sort_key: newSortKey,
                  placement_status: placementStatus,
                }
              : marker,
          )
        : prev,
    );
    if (placementStatus === "placed") {
      setActiveTimelineMarkerId(markerId);
    }

    try {
      await timelineApi.repositionMarker(worldId, markerId, {
        sort_key: newSortKey,
        placement_status: placementStatus,
      });
      await reload({ markerId: markerId });
    } catch (error) {
      setTimelineMarkers(previousMarkers);
      throw error;
    }
  }

  if (!graphData || !notesList || !timelineMarkers) {
    return (
      <div className="flex min-h-screen items-center justify-center text-text-muted">
        Loading world...
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-border bg-surface px-4 py-2">
        <button
          onClick={() => navigate("/")}
          className="rounded p-1 hover:bg-surface-hover"
        >
          <ArrowLeft size={18} />
        </button>
        <Network size={18} className="text-accent" />
        <span className="font-semibold">World Graph</span>
        <span className="ml-2 text-xs text-text-muted">
          {graphData.entities.length} entities &middot;{" "}
          {graphData.relations.length} relations
        </span>

        <div className="relative ml-4 w-full max-w-md">
          <input
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setSearchOpen(true);
            }}
            onFocus={() => setSearchOpen(true)}
            onBlur={() => {
              window.setTimeout(() => setSearchOpen(false), 120);
            }}
            placeholder="Search entities..."
            className="w-full rounded-lg border border-border bg-panel px-3 py-1.5 text-sm text-text outline-none focus:border-accent"
          />
          {searchOpen && searchQuery.trim() && (
            <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-20 max-h-80 overflow-y-auto rounded-lg border border-border bg-surface shadow-lg">
              {searchMatches.length > 0 ? (
                searchMatches.map((match) => (
                  <button
                    key={match.entity.id}
                    onMouseDown={() => {
                      setSearchQuery(match.entity.name);
                      setSearchOpen(false);
                      openEntityRoute(match.entity.id);
                    }}
                    className="flex w-full flex-col px-3 py-2 text-left hover:bg-surface-hover"
                  >
                    <span className="text-sm">{match.entity.name}</span>
                    <span className="text-xs text-text-muted">
                      {match.entity.type}
                      {match.entity.aliases.length > 0
                        ? ` - aka ${match.entity.aliases.slice(0, 2).join(", ")}`
                        : ""}
                    </span>
                  </button>
                ))
              ) : (
                <div className="px-3 py-2 text-sm text-text-muted">
                  No matches
                </div>
              )}
            </div>
          )}
        </div>

        <div className="ml-auto flex gap-1">
          <ToolbarBtn
            icon={<Plus size={16} />}
            label="Entity"
            active={panel.kind === "create-entity"}
            onClick={() => {
              clearEntityRoute();
              setPanel(
                panel.kind === "create-entity"
                  ? { kind: "none" }
                  : { kind: "create-entity" },
              );
            }}
          />
          <ToolbarBtn
            icon={<Link size={16} />}
            label="Relation"
            active={panel.kind === "create-relation"}
            onClick={() => {
              clearEntityRoute();
              setPanel(
                panel.kind === "create-relation"
                  ? { kind: "none" }
                  : { kind: "create-relation" },
              );
            }}
          />
          <ToolbarBtn
            icon={<BookOpen size={16} />}
            label="Notes"
            active={panel.kind === "notes"}
            onClick={() => {
              clearEntityRoute();
              setPanel(
                panel.kind === "notes" ? { kind: "none" } : { kind: "notes" },
              );
            }}
          />
          <ToolbarBtn
            icon={<MessageSquare size={16} />}
            label="Historian"
            active={panel.kind === "historian"}
            onClick={() => {
              clearEntityRoute();
              setPanel(
                panel.kind === "historian"
                  ? { kind: "none" }
                  : { kind: "historian" },
              );
            }}
          />
          <ToolbarBtn
            icon={<Shield size={16} />}
            label="Run Guardian"
            active={panel.kind === "guardian"}
            onClick={() => {
              clearEntityRoute();
              if (panel.kind === "guardian") {
                setPanel({ kind: "none" });
                return;
              }
              setPanel({ kind: "guardian" });
              if (!guardianRun && !runningGuardian) {
                void handleRunGuardian();
              }
            }}
          />
        </div>
      </div>
      <div className="flex items-center gap-2 border-b border-border bg-panel px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Filters
        </span>
        <label className="flex items-center gap-1 text-xs text-text-muted">
          Entity Type
          <select
            value={entityTypeFilter}
            onChange={(e) => setEntityTypeFilter(e.target.value)}
            className="rounded border border-border bg-surface px-2 py-1 text-xs text-text"
          >
            {availableEntityTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-xs text-text-muted">
          Relation Type
          <select
            value={relationTypeFilter}
            onChange={(e) => setRelationTypeFilter(e.target.value)}
            className="rounded border border-border bg-surface px-2 py-1 text-xs text-text"
          >
            {availableRelationTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-xs text-text-muted">
          Focus Node
          <select
            value={effectiveFocusEntityId}
            onChange={(e) => setFocusEntityId(e.target.value)}
            className="max-w-56 rounded border border-border bg-surface px-2 py-1 text-xs text-text"
          >
            <option value="">(none)</option>
            {baseFilteredEntities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.name}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={() => {
            setEntityTypeFilter("all");
            setRelationTypeFilter("all");
            setFocusEntityId("");
          }}
          className="ml-auto flex items-center gap-1 rounded border border-border px-2 py-1 text-xs text-text-muted hover:bg-surface-hover hover:text-text"
          title="Reset filters"
        >
          <FilterX size={13} /> Reset
        </button>
        <span className="text-xs text-text-muted">
          Showing {filteredGraph.entities.length}/{graphData.entities.length} entities,{" "}
          {filteredGraph.relations.length}/{graphData.relations.length} relations
        </span>
      </div>

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Graph canvas */}
        <div className="relative min-h-0 min-w-0 flex-1">
          <WorldGraph
            entities={filteredGraph.entities}
            relations={filteredGraph.relations}
            activeEntityId={activeEntityIdForGraph}
            onSelectEntity={handleSelectEntity}
            onSelectRelation={handleSelectRelation}
          />
          <div className="absolute bottom-5 left-3 right-3 z-10 sm:left-[72px] sm:right-[220px]">
            <TimelineStrip
              markers={timelineMarkers}
              activeMarkerId={activeTimelineMarkerId}
              onSelectMarker={setActiveTimelineMarkerId}
              onOpenActiveMarkerOps={(markerId) => setPanel({ kind: "timeline-operations", markerId })}
              onRepositionMarker={handleRepositionTimelineMarker}
            />
          </div>
        </div>

        {/* Side panel */}

        {routeEntity && (
          <SidePanel title={routeEntity.name} onClose={clearEntityRoute}>
            <EntityDetail
              key={routeEntity.id}
              entity={routeEntity}
              onSave={(data) => handleUpdateEntity(routeEntity.id, data)}
              onDelete={() => void handleDeleteEntity(routeEntity.id)}
            />
          </SidePanel>
        )}
        {panel.kind === "create-entity" && (
          <SidePanel
            title="New Entity"
            onClose={() => setPanel({ kind: "none" })}
          >
            <EntityCreateForm onSubmit={handleCreateEntity} />
          </SidePanel>
        )}
        {panel.kind === "create-relation" && (
          <SidePanel
            title="New Relation"
            onClose={() => setPanel({ kind: "none" })}
          >
            <RelationCreateForm
              entities={graphData.entities}
              onSubmit={handleCreateRelation}
            />
          </SidePanel>
        )}
        {panel.kind === "relation-detail" && selectedRelation && (
          <SidePanel
            title={selectedRelation.type}
            onClose={() => setPanel({ kind: "none" })}
          >
            <RelationDetail
              key={selectedRelation.id}
              relation={selectedRelation}
              sourceEntity={entityById.get(selectedRelation.source_entity_id) ?? null}
              targetEntity={entityById.get(selectedRelation.target_entity_id) ?? null}
              onSave={(data) => handleUpdateRelation(selectedRelation.id, data)}
            />
          </SidePanel>
        )}
        {panel.kind === "notes" && (
          <SidePanel title="Notes" onClose={() => setPanel({ kind: "none" })}>
            <NotePanel
              notes={notesList}
              onCreateNote={handleCreateNote}
              onUpdateNote={handleUpdateNote}
              onAnalyzeNote={handleAnalyzeNote}
              onAnalyzeAllNotes={handleAnalyzeAllNotes}
            />
          </SidePanel>
        )}
        {panel.kind === "guardian" && (
          <SidePanel title="Canon Guardian" onClose={() => setPanel({ kind: "none" })}>
            <GuardianPanel
              run={guardianRun}
              running={runningGuardian}
              error={guardianError}
              expandedFindingIds={expandedFindingIds}
              dismissingFindingId={dismissingFindingId}
              runningMechanicFindingId={runningMechanicFindingId}
              runningMechanicOptionId={runningMechanicOptionId}
              mechanicRunsByFinding={mechanicRunsByFinding}
              mechanicErrorByFinding={mechanicErrorByFinding}
              onRunGuardian={handleRunGuardian}
              onToggleFinding={handleToggleGuardianFindingExpanded}
              onDismissFinding={handleDismissGuardianFinding}
              onRunMechanic={handleRunMechanicForFinding}
              onRunMechanicOption={handleRunMechanicOption}
            />
          </SidePanel>
        )}
        {panel.kind === "historian" && worldId && (
          <SidePanel title="Historian NPC" onClose={() => setPanel({ kind: "none" })}>
            <HistorianPanel worldId={worldId} />
          </SidePanel>
        )}
        {panel.kind === "timeline-operations" && worldId && (
          <SidePanel
            title={panelTimelineMarker ? `Timeline Ops: ${panelTimelineMarker.title}` : "Timeline Operations"}
            onClose={() => setPanel({ kind: "none" })}
          >
            <TimelineMarkerOpsPanel
              worldId={worldId}
              markerId={panel.markerId}
              onChanged={async () => {
                await reload({ markerId: panel.markerId });
              }}
            />
          </SidePanel>
        )}
      </div>
    </div>
  );
}

function ToolbarBtn({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition ${
        active
          ? "bg-accent text-white"
          : "text-text-muted hover:bg-surface-hover hover:text-text"
      }`}
    >
      {icon} {label}
    </button>
  );
}

