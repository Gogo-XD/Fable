"""Intent-aware context pack compiler for Historian QA turns."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Literal

import aiosqlite

from app.config import settings
from app.logging import get_logger
from app.services.timeline import TimelineService

logger = get_logger("services.historian_context")

HistorianIntent = Literal[
    "entity_fact",
    "entity_attribute",
    "relation_exists",
    "relation_explain",
    "location_of_entity",
    "event_date",
    "event_details",
    "chronology_order",
    "timeline_slice_summary",
    "state_at_time",
    "change_over_time",
    "list_filter",
    "compare",
    "graph_path",
    "causal_why",
    "counterfactual_remove_event",
    "counterfactual_change_decision",
    "projection_plausible_future",
    "rules_mechanics",
    "canon_consistency_check",
    "retcon_impact",
    "provenance_citation",
    "ambiguity_disambiguation",
    "unknown_gap",
    "creative_constrained",
    "meta_system",
]

ContextPackName = Literal[
    "EntityPack",
    "RelationPack",
    "TimelinePack",
    "RulePack",
    "EvidencePack",
    "SnapshotDeltaPack",
]

MAX_CONTEXT_CHARS = 12_000
MAX_SECTION_CHARS = 3_600

_YEAR_PATTERN = re.compile(r"\b(?:year\s+)?(-?\d{1,5})\b", re.IGNORECASE)
_QUOTED_PHRASE_PATTERN = re.compile(r"[\"']([^\"']{2,120})[\"']")
_TOKEN_PATTERN = re.compile(r"[a-z0-9_'-]+", re.IGNORECASE)
_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "from",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "did",
    "does",
    "do",
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "could",
    "would",
    "should",
    "if",
    "all",
    "with",
    "without",
    "this",
    "that",
    "it",
    "its",
    "their",
    "his",
    "her",
}


@dataclass(frozen=True)
class IntentProfile:
    strategy: str
    packs: tuple[ContextPackName, ...]


@dataclass(frozen=True)
class IntentDecision:
    intent: HistorianIntent
    confidence: float
    reason: str


@dataclass(frozen=True)
class ContextPackBuildResult:
    intent: HistorianIntent
    confidence: float
    reason: str
    strategy: str
    packs_used: tuple[ContextPackName, ...]
    context_pack: str
    evidence_refs: tuple[str, ...]


INTENT_CATALOG: dict[HistorianIntent, IntentProfile] = {
    "entity_fact": IntentProfile(
        strategy="Entity pack: exact/alias match, summary/context, tags, source notes",
        packs=("EntityPack", "EvidencePack"),
    ),
    "entity_attribute": IntentProfile(
        strategy="Entity row + latest timeline ops touching that field",
        packs=("EntityPack", "TimelinePack", "EvidencePack"),
    ),
    "relation_exists": IntentProfile(
        strategy="Direct relation lookup + relation type normalization",
        packs=("RelationPack", "EvidencePack"),
    ),
    "relation_explain": IntentProfile(
        strategy="1-hop/2-hop graph path + relation contexts + key events",
        packs=("EntityPack", "RelationPack", "TimelinePack", "EvidencePack"),
    ),
    "location_of_entity": IntentProfile(
        strategy="Spatial relations + latest timeline state",
        packs=("EntityPack", "RelationPack", "TimelinePack", "EvidencePack"),
    ),
    "event_date": IntentProfile(
        strategy="Timeline marker lookup + date label/sort value",
        packs=("TimelinePack", "EvidencePack"),
    ),
    "event_details": IntentProfile(
        strategy="Marker summary + operations + linked entities/relations",
        packs=("EntityPack", "RelationPack", "TimelinePack", "EvidencePack"),
    ),
    "chronology_order": IntentProfile(
        strategy="Marker sort_key/date_sort_value comparison",
        packs=("TimelinePack", "EvidencePack"),
    ),
    "timeline_slice_summary": IntentProfile(
        strategy="Time-window marker set + compressed event summaries",
        packs=("TimelinePack", "EvidencePack"),
    ),
    "state_at_time": IntentProfile(
        strategy="Timeline world-state projection near marker/date",
        packs=("TimelinePack", "EvidencePack"),
    ),
    "change_over_time": IntentProfile(
        strategy="Timeline ops filtered by target entity + ordered diffs",
        packs=("EntityPack", "TimelinePack", "EvidencePack"),
    ),
    "list_filter": IntentProfile(
        strategy="Typed entity query + relation filter + optional ranking",
        packs=("EntityPack", "RelationPack", "EvidencePack"),
    ),
    "compare": IntentProfile(
        strategy="Side-by-side entity + relation neighborhood contrast",
        packs=("EntityPack", "RelationPack", "TimelinePack", "EvidencePack"),
    ),
    "graph_path": IntentProfile(
        strategy="Multi-hop relation path search with max depth and scoring",
        packs=("EntityPack", "RelationPack", "EvidencePack"),
    ),
    "causal_why": IntentProfile(
        strategy="Prior markers + related entities/relations + evidence notes",
        packs=("RelationPack", "TimelinePack", "EvidencePack"),
    ),
    "counterfactual_remove_event": IntentProfile(
        strategy="Before/after snapshot delta + affected entities + branch assumptions",
        packs=("EntityPack", "RelationPack", "TimelinePack", "SnapshotDeltaPack", "RulePack", "EvidencePack"),
    ),
    "counterfactual_change_decision": IntentProfile(
        strategy="Decision-anchor snapshot delta + plausible branch assumptions",
        packs=("EntityPack", "RelationPack", "TimelinePack", "SnapshotDeltaPack", "RulePack", "EvidencePack"),
    ),
    "projection_plausible_future": IntentProfile(
        strategy="Recent timeline trends + active conflicts + rules constraints",
        packs=("EntityPack", "RelationPack", "TimelinePack", "RulePack", "EvidencePack"),
    ),
    "rules_mechanics": IntentProfile(
        strategy="Rules/invariants first, then edge-case precedent events",
        packs=("RulePack", "TimelinePack", "EvidencePack"),
    ),
    "canon_consistency_check": IntentProfile(
        strategy="Hard constraints + soft critic style context review",
        packs=("EntityPack", "RelationPack", "TimelinePack", "RulePack", "EvidencePack"),
    ),
    "retcon_impact": IntentProfile(
        strategy="Dependency scan: affected entities, relations, markers, notes",
        packs=("EntityPack", "RelationPack", "TimelinePack", "SnapshotDeltaPack", "EvidencePack"),
    ),
    "provenance_citation": IntentProfile(
        strategy="Return note IDs, marker IDs, relation/entity IDs used",
        packs=("EvidencePack", "EntityPack", "RelationPack", "TimelinePack"),
    ),
    "ambiguity_disambiguation": IntentProfile(
        strategy="Alias set + confidence + clarifying options",
        packs=("EntityPack", "EvidencePack"),
    ),
    "unknown_gap": IntentProfile(
        strategy="Explicit unknown + closest known canon neighbors",
        packs=("EntityPack", "EvidencePack"),
    ),
    "creative_constrained": IntentProfile(
        strategy="Canon-grounded generation with strict non-contradiction checks",
        packs=("EntityPack", "RelationPack", "TimelinePack", "RulePack", "EvidencePack"),
    ),
    "meta_system": IntentProfile(
        strategy="Evidence count, source freshness, contradiction risk flags",
        packs=("EvidencePack", "RulePack"),
    ),
}


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _truncate_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 15)] + "...<truncated>"


def _load_json_list(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text.lower()) if token.lower() not in _STOPWORDS]


def _normalize_relation_type(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _extract_year(message: str) -> int | None:
    match = _YEAR_PATTERN.search(message or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


class HistorianContextCompiler:
    """Build targeted context packs based on classified QA intent."""

    def __init__(self, db_path: str, timeline_service: TimelineService):
        self.db_path = db_path
        self.timeline_service = timeline_service

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def _list_entities(self, db: aiosqlite.Connection, world_id: str) -> list[dict[str, Any]]:
        cursor = await db.execute(
            """SELECT id, name, type, subtype, aliases, summary, context, tags, status, source_note_id, created_at, updated_at
               FROM entities
               WHERE world_id = ?
               ORDER BY LOWER(name) ASC, created_at ASC, id ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        entities: list[dict[str, Any]] = []
        for row in rows:
            entity = dict(row)
            entity["aliases"] = _load_json_list(entity.get("aliases"))
            entity["tags"] = _load_json_list(entity.get("tags"))
            entity["name_norm"] = _normalize_text(entity.get("name")).lower()
            alias_map = []
            for alias in entity["aliases"]:
                alias_norm = _normalize_text(alias).lower()
                if alias_norm:
                    alias_map.append(alias_norm)
            entity["aliases_norm"] = alias_map
            entity["type"] = _normalize_text(entity.get("type"))
            entity["subtype"] = _normalize_text(entity.get("subtype")) or None
            entities.append(entity)
        return entities

    async def _list_relations(self, db: aiosqlite.Connection, world_id: str) -> list[dict[str, Any]]:
        cursor = await db.execute(
            """SELECT
                   r.id,
                   r.source_entity_id,
                   r.target_entity_id,
                   r.type,
                   r.context,
                   r.weight,
                   r.source_note_id,
                   r.created_at,
                   r.updated_at,
                   se.name AS source_name,
                   te.name AS target_name
               FROM relations r
               JOIN entities se ON se.id = r.source_entity_id
               JOIN entities te ON te.id = r.target_entity_id
               WHERE r.world_id = ?
               ORDER BY r.created_at ASC, r.id ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        relations: list[dict[str, Any]] = []
        for row in rows:
            relation = dict(row)
            relation["type_norm"] = _normalize_relation_type(_normalize_text(relation.get("type")))
            relations.append(relation)
        return relations

    async def _list_notes(self, db: aiosqlite.Connection, world_id: str, limit: int = 200) -> list[dict[str, Any]]:
        cursor = await db.execute(
            """SELECT id, title, content, created_at, updated_at
               FROM notes
               WHERE world_id = ?
               ORDER BY updated_at DESC, created_at DESC, id DESC
               LIMIT ?""",
            (world_id, int(limit)),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _get_rules_doc_meta(self, db: aiosqlite.Connection, world_id: str) -> dict[str, Any] | None:
        cursor = await db.execute(
            """SELECT assistant_id, document_id, updated_at, last_compiled_at
               FROM world_rag_documents
               WHERE world_id = ? AND slot_key = 'rules_invariants'
               LIMIT 1""",
            (world_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    def _match_entities(self, question: str, entities: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
        query = _normalize_text(question).lower()
        tokens = _tokenize(question)
        if not query:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for entity in entities:
            score = 0.0
            name_norm = entity.get("name_norm") or ""
            aliases_norm = entity.get("aliases_norm") or []

            if name_norm and name_norm == query:
                score += 1.0
            if name_norm and name_norm in query:
                score += 0.75
            for alias_norm in aliases_norm:
                if alias_norm and alias_norm == query:
                    score += 0.95
                elif alias_norm and alias_norm in query:
                    score += 0.6

            if tokens and name_norm:
                name_tokens = set(_tokenize(name_norm))
                overlap = len(name_tokens.intersection(tokens))
                if overlap > 0:
                    score += min(0.5, overlap / max(len(name_tokens), 1))

            if score > 0:
                scored.append((score, entity))

        scored.sort(key=lambda item: (-item[0], (item[1].get("name") or "").lower()))
        return [entry for _, entry in scored[:limit]]

    def _classify_intent(self, question: str, matched_entities: list[dict[str, Any]]) -> IntentDecision:
        q = _normalize_text(question).lower()
        entity_count = len(matched_entities)
        is_counterfactual = (
            "what if" in q
            or "what would have happened if" in q
            or "would have happened if" in q
            or q.startswith("if ")
        )

        if any(token in q for token in ("source for", "cite", "citation", "where did you get", "evidence")):
            return IntentDecision(intent="provenance_citation", confidence=0.95, reason="citation keyword")
        if any(token in q for token in ("how confident", "confidence", "certainty")):
            return IntentDecision(intent="meta_system", confidence=0.88, reason="confidence keyword")
        if "retcon" in q:
            return IntentDecision(intent="retcon_impact", confidence=0.94, reason="retcon keyword")
        if any(token in q for token in ("break canon", "canon consistency", "canon-consistent")):
            return IntentDecision(intent="canon_consistency_check", confidence=0.92, reason="canon keyword")
        if is_counterfactual and any(token in q for token in ("chose", "instead", "had chosen", "decision")):
            return IntentDecision(intent="counterfactual_change_decision", confidence=0.9, reason="counterfactual decision pattern")
        if is_counterfactual and any(
            token in q
            for token in (
                "never happened",
                "didn't happen",
                "did not happen",
                "didn't occur",
                "did not occur",
                "hadn't occurred",
                "had not occurred",
                "without event",
                "without the",
                "never occurred",
            )
        ):
            return IntentDecision(intent="counterfactual_remove_event", confidence=0.93, reason="counterfactual remove event pattern")
        if any(token in q for token in ("might happen next", "what happens next", "future", "next outcome")):
            return IntentDecision(intent="projection_plausible_future", confidence=0.78, reason="future projection wording")
        if any(token in q for token in ("rumor", "rumour", "draft a", "write a plausible")):
            return IntentDecision(intent="creative_constrained", confidence=0.8, reason="creative constrained wording")
        if any(token in q for token in ("can magic", "rules", "invariant", "mechanic", "allowed to")):
            return IntentDecision(intent="rules_mechanics", confidence=0.9, reason="rules/mechanics wording")
        if any(token in q for token in ("did you mean", "which one", "or prince", "or king")):
            return IntentDecision(intent="ambiguity_disambiguation", confidence=0.88, reason="disambiguation wording")
        if any(token in q for token in ("before", "after")) and entity_count >= 2:
            return IntentDecision(intent="chronology_order", confidence=0.75, reason="before/after wording")
        if any(token in q for token in ("in year", "at year", "world like in", "state in")):
            return IntentDecision(intent="state_at_time", confidence=0.9, reason="state at time wording")
        if "change over time" in q or "evolve over time" in q:
            return IntentDecision(intent="change_over_time", confidence=0.9, reason="change-over-time wording")
        if any(token in q for token in ("ancient era", "past era", "present era", "era summary")):
            return IntentDecision(intent="timeline_slice_summary", confidence=0.82, reason="era summary wording")
        if q.startswith("when ") or "what year" in q:
            return IntentDecision(intent="event_date", confidence=0.78, reason="date query wording")
        if "what happened" in q:
            return IntentDecision(intent="event_details", confidence=0.76, reason="event details wording")
        if "why " in q:
            return IntentDecision(intent="causal_why", confidence=0.73, reason="causal why wording")
        if "where is" in q or "where was" in q or "based in" in q:
            return IntentDecision(intent="location_of_entity", confidence=0.82, reason="location wording")
        if q.startswith("list ") or "list all" in q:
            return IntentDecision(intent="list_filter", confidence=0.8, reason="list/filter wording")
        if any(token in q for token in ("compare", "difference between", "versus", "vs ")):
            return IntentDecision(intent="compare", confidence=0.88, reason="compare wording")
        if any(token in q for token in ("what links", "path between", "connected to", "link between")):
            return IntentDecision(intent="graph_path", confidence=0.86, reason="path wording")
        if any(token in q for token in ("is ", "are ")) and any(token in q for token in ("allied", "enemy", "related", "relation between")):
            return IntentDecision(intent="relation_exists", confidence=0.74, reason="relation exists wording")
        if "how are" in q and "connected" in q:
            return IntentDecision(intent="relation_explain", confidence=0.8, reason="relation explain wording")
        if any(token in q for token in ("status", "title", "rank", "role")) and entity_count >= 1:
            return IntentDecision(intent="entity_attribute", confidence=0.76, reason="entity attribute wording")
        if q.startswith("who is") or q.startswith("who was") or q.startswith("tell me about"):
            if entity_count == 0:
                return IntentDecision(intent="unknown_gap", confidence=0.7, reason="entity query with no confident match")
            return IntentDecision(intent="entity_fact", confidence=0.84, reason="entity fact wording")

        if entity_count == 0 and any(token in q for token in ("who", "where", "when", "found", "founded")):
            return IntentDecision(intent="unknown_gap", confidence=0.62, reason="factoid query with no matches")
        return IntentDecision(intent="entity_fact", confidence=0.5, reason="fallback intent")

    def _section(self, title: str, body_lines: list[str]) -> str:
        lines = [line for line in body_lines if _normalize_text(line)]
        if not lines:
            return ""
        content = f"## {title}\n" + "\n".join(lines)
        return _truncate_text(content, MAX_SECTION_CHARS)

    def _build_entity_pack(self, matched_entities: list[dict[str, Any]]) -> tuple[str, list[str]]:
        if not matched_entities:
            return self._section("EntityPack", ["No high-confidence entity matches from question text."]), []

        lines: list[str] = []
        refs: list[str] = []
        for entity in matched_entities[:6]:
            entity_id = str(entity.get("id") or "")
            refs.append(f"entity:{entity_id}")
            lines.append(f"- id={entity_id} | name={entity.get('name')} | type={entity.get('type')} | status={entity.get('status')}")
            aliases = entity.get("aliases") or []
            tags = entity.get("tags") or []
            if aliases:
                lines.append(f"  aliases: {', '.join(_truncate_text(alias, 60) for alias in aliases[:8])}")
            if tags:
                lines.append(f"  tags: {', '.join(_truncate_text(tag, 32) for tag in tags[:10])}")
            summary = _truncate_text(str(entity.get("summary") or "-"), 240)
            context = _truncate_text(str(entity.get("context") or "-"), 320)
            lines.append(f"  summary: {summary}")
            lines.append(f"  context: {context}")
            source_note_id = _normalize_text(entity.get("source_note_id"))
            if source_note_id:
                refs.append(f"note:{source_note_id}")
                lines.append(f"  source_note_id: {source_note_id}")
        return self._section("EntityPack", lines), refs

    def _find_paths(
        self,
        relations: list[dict[str, Any]],
        start_id: str,
        end_id: str,
        max_depth: int = 2,
        max_paths: int = 3,
    ) -> list[list[dict[str, Any]]]:
        if start_id == end_id:
            return []

        adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for relation in relations:
            source = str(relation.get("source_entity_id") or "")
            target = str(relation.get("target_entity_id") or "")
            if not source or not target:
                continue
            adjacency.setdefault(source, []).append((target, relation))
            adjacency.setdefault(target, []).append((source, relation))

        paths: list[list[dict[str, Any]]] = []
        queue: list[tuple[str, list[str], list[dict[str, Any]]]] = [(start_id, [start_id], [])]
        while queue and len(paths) < max_paths:
            node, visited_nodes, edge_path = queue.pop(0)
            if len(edge_path) >= max_depth:
                continue
            for next_node, edge in adjacency.get(node, []):
                if next_node in visited_nodes:
                    continue
                next_edges = [*edge_path, edge]
                if next_node == end_id:
                    paths.append(next_edges)
                    if len(paths) >= max_paths:
                        break
                    continue
                queue.append((next_node, [*visited_nodes, next_node], next_edges))
        return paths

    def _build_relation_pack(
        self,
        matched_entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        intent: HistorianIntent,
    ) -> tuple[str, list[str]]:
        if not relations:
            return self._section("RelationPack", ["No relations available in this world."]), []

        focus_ids = [str(entity.get("id") or "") for entity in matched_entities if entity.get("id")]
        focus_id_set = set(focus_ids)
        scoped_relations = [
            relation
            for relation in relations
            if relation.get("source_entity_id") in focus_id_set or relation.get("target_entity_id") in focus_id_set
        ] if focus_id_set else relations[:20]

        lines: list[str] = []
        refs: list[str] = []
        for relation in scoped_relations[:24]:
            relation_id = str(relation.get("id") or "")
            refs.append(f"relation:{relation_id}")
            source_name = relation.get("source_name") or relation.get("source_entity_id")
            target_name = relation.get("target_name") or relation.get("target_entity_id")
            lines.append(
                f"- id={relation_id} | {source_name} -> {target_name} | type={relation.get('type')} (norm={relation.get('type_norm')})"
            )
            context = _truncate_text(str(relation.get("context") or "-"), 220)
            lines.append(f"  context: {context}")
            source_note_id = _normalize_text(relation.get("source_note_id"))
            if source_note_id:
                refs.append(f"note:{source_note_id}")
                lines.append(f"  source_note_id: {source_note_id}")

        if len(focus_ids) >= 2 and intent in {"relation_explain", "graph_path", "compare"}:
            start_id = focus_ids[0]
            end_id = focus_ids[1]
            paths = self._find_paths(relations, start_id=start_id, end_id=end_id, max_depth=3, max_paths=3)
            if paths:
                lines.append("- candidate_paths:")
                for path in paths:
                    path_nodes: list[str] = []
                    for relation in path:
                        source_name = str(relation.get("source_name") or relation.get("source_entity_id"))
                        target_name = str(relation.get("target_name") or relation.get("target_entity_id"))
                        relation_type = str(relation.get("type") or relation.get("type_norm"))
                        path_nodes.append(f"{source_name}-[{relation_type}]-{target_name}")
                    lines.append(f"  * {' => '.join(path_nodes)}")
            else:
                lines.append("- candidate_paths: none found within depth<=3")

        if not lines:
            lines.append("No relation matches were found for current focus entities.")
        return self._section("RelationPack", lines), refs

    def _match_markers(
        self,
        question: str,
        markers: list[Any],
        matched_entity_names: list[str],
        limit: int = 8,
    ) -> list[Any]:
        query = _normalize_text(question).lower()
        tokens = set(_tokenize(question))
        quoted_phrases = [phrase.lower() for phrase in _QUOTED_PHRASE_PATTERN.findall(question)]
        entity_tokens = set()
        for name in matched_entity_names:
            entity_tokens.update(_tokenize(name))

        scored: list[tuple[float, Any]] = []
        for marker in markers:
            title = _normalize_text(getattr(marker, "title", "")).lower()
            summary = _normalize_text(getattr(marker, "summary", "")).lower()
            score = 0.0
            if title and title in query:
                score += 0.95
            if summary and summary in query:
                score += 0.5
            for phrase in quoted_phrases:
                if phrase in title:
                    score += 0.8
                if phrase in summary:
                    score += 0.4
            title_tokens = set(_tokenize(title))
            summary_tokens = set(_tokenize(summary))
            overlap = len(tokens.intersection(title_tokens.union(summary_tokens)))
            if overlap:
                score += min(0.5, overlap / max(len(tokens), 1))
            if entity_tokens and len(entity_tokens.intersection(summary_tokens.union(title_tokens))) > 0:
                score += 0.2
            if score > 0:
                scored.append((score, marker))

        scored.sort(key=lambda item: (-item[0], getattr(item[1], "sort_key", 0.0)))
        matched = [marker for _, marker in scored[:limit]]
        if matched:
            return matched
        return markers[: min(limit, len(markers))]

    async def _build_timeline_pack(
        self,
        world_id: str,
        question: str,
        intent: HistorianIntent,
        matched_entities: list[dict[str, Any]],
        markers: list[Any],
    ) -> tuple[str, list[str]]:
        if not markers:
            return self._section("TimelinePack", ["No timeline markers found."]), []

        refs: list[str] = []
        lines: list[str] = []
        matched_marker_candidates = self._match_markers(
            question=question,
            markers=markers,
            matched_entity_names=[str(entity.get("name") or "") for entity in matched_entities],
        )

        focus_markers = matched_marker_candidates[:6]
        if intent == "timeline_slice_summary":
            q = _normalize_text(question).lower()
            if "ancient" in q:
                focus_markers = [marker for marker in markers if "ancient" in _normalize_text(marker.title).lower()][:6]
            elif "present" in q:
                focus_markers = markers[-6:]
            elif "past" in q:
                middle = max(len(markers) // 2, 1)
                start = max(0, middle - 3)
                focus_markers = markers[start : start + 6]

        for marker in focus_markers:
            marker_id = str(getattr(marker, "id", ""))
            refs.append(f"marker:{marker_id}")
            lines.append(
                f"- id={marker_id} | title={marker.title} | date_label={marker.date_label or '-'} | "
                f"date_sort={marker.date_sort_value if marker.date_sort_value is not None else '-'} | sort_key={marker.sort_key}"
            )
            summary = _truncate_text(_normalize_text(marker.summary or "-"), 200)
            lines.append(f"  summary: {summary}")
            if getattr(marker, "source_note_id", None):
                refs.append(f"note:{marker.source_note_id}")
                lines.append(f"  source_note_id: {marker.source_note_id}")
            op_count = len(getattr(marker, "operations", []) or [])
            if op_count > 0:
                lines.append(f"  operations: {op_count}")

        if intent in {"change_over_time", "entity_attribute"} and matched_entities:
            focus_ids = {str(entity.get("id")) for entity in matched_entities if entity.get("id")}
            lines.append("- timeline_ops_for_focus_entities:")
            found = 0
            for marker in markers:
                for operation in getattr(marker, "operations", []) or []:
                    if operation.target_id in focus_ids:
                        found += 1
                        refs.append(f"operation:{operation.id}")
                        lines.append(
                            f"  * marker={marker.title} ({marker.id}) | op={operation.op_type} | target_id={operation.target_id} | order={operation.order_index}"
                        )
                        payload_preview = _truncate_text(json.dumps(operation.payload or {}, ensure_ascii=True), 220)
                        lines.append(f"    payload: {payload_preview}")
                    if found >= 24:
                        break
                if found >= 24:
                    break
            if found == 0:
                lines.append("  * none found")

        if intent == "chronology_order" and len(focus_markers) >= 2:
            first = focus_markers[0]
            second = focus_markers[1]
            if first.sort_key < second.sort_key:
                relation = "before"
            elif first.sort_key > second.sort_key:
                relation = "after"
            else:
                relation = "same-order"
            lines.append(
                f"- chronology_hint: '{first.title}' is {relation} '{second.title}' based on sort_key ({first.sort_key} vs {second.sort_key})"
            )

        if intent == "state_at_time":
            year = _extract_year(question)
            explicit_markers = [marker for marker in markers if marker.date_sort_value is not None]
            nearest = None
            if year is not None and explicit_markers:
                nearest = min(explicit_markers, key=lambda marker: abs(float(marker.date_sort_value) - float(year)))
                lines.append(
                    f"- nearest_explicit_marker_for_year_{year}: id={nearest.id} | title={nearest.title} | date_sort={nearest.date_sort_value}"
                )
            if nearest:
                try:
                    state = await self.timeline_service.get_world_state(world_id=world_id, marker_id=nearest.id)
                    lines.append(
                        f"- projected_state_at_marker: entities={len(state.entities)} relations={len(state.relations)} applied_markers={state.applied_marker_count}"
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("Failed state_at_time projection world_id=%s marker_id=%s error=%s", world_id, nearest.id, exc)

        return self._section("TimelinePack", lines), refs

    def _build_rule_pack(self, rules_doc_meta: dict[str, Any] | None) -> tuple[str, list[str]]:
        lines: list[str] = []
        refs: list[str] = []
        if not rules_doc_meta:
            lines.append("No compiled rules/invariants RAG document metadata found.")
            return self._section("RulePack", lines), refs

        assistant_id = _normalize_text(rules_doc_meta.get("assistant_id"))
        document_id = _normalize_text(rules_doc_meta.get("document_id"))
        updated_at = _normalize_text(rules_doc_meta.get("updated_at"))
        compiled_at = _normalize_text(rules_doc_meta.get("last_compiled_at"))
        refs.append("rag_slot:rules_invariants")
        if document_id:
            refs.append(f"rag_document:{document_id}")

        lines.append(f"- assistant_id: {assistant_id or '-'}")
        lines.append(f"- document_id: {document_id or '-'}")
        lines.append(f"- updated_at: {updated_at or '-'}")
        lines.append(f"- last_compiled_at: {compiled_at or '-'}")

        if assistant_id:
            local_path = os.path.join(settings.DOCUMENTS_PATH, f"{assistant_id}_rag_rules_invariants.md")
            if os.path.exists(local_path):
                try:
                    with open(local_path, "r", encoding="utf-8") as handle:
                        content = handle.read()
                    refs.append(f"local_doc:{os.path.basename(local_path)}")
                    lines.append("- local_excerpt:")
                    excerpt = _truncate_text(content, 2200)
                    lines.append(f"  {excerpt}")
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("Failed reading rules local doc path=%s error=%s", local_path, exc)
                    lines.append("- local_excerpt: unavailable (read error)")
            else:
                lines.append(f"- local_excerpt: unavailable (file missing: {os.path.basename(local_path)})")
        return self._section("RulePack", lines), refs

    def _rank_notes_for_query(self, question: str, notes: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
        tokens = set(_tokenize(question))
        if not tokens:
            return notes[:limit]
        scored: list[tuple[float, dict[str, Any]]] = []
        for note in notes:
            title = _normalize_text(note.get("title"))
            content = _normalize_text(note.get("content"))
            haystack_tokens = set(_tokenize(f"{title} {content[:1500]}"))
            overlap = len(tokens.intersection(haystack_tokens))
            if overlap <= 0:
                continue
            score = float(overlap) / max(len(tokens), 1)
            if title:
                title_tokens = set(_tokenize(title))
                title_overlap = len(tokens.intersection(title_tokens))
                score += min(0.5, float(title_overlap) / max(len(tokens), 1))
            scored.append((score, note))
        scored.sort(key=lambda item: -item[0])
        return [note for _, note in scored[:limit]] or notes[:limit]

    def _build_evidence_pack(
        self,
        question: str,
        notes: list[dict[str, Any]],
        matched_entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        markers: list[Any],
    ) -> tuple[str, list[str]]:
        note_ids: set[str] = set()
        for entity in matched_entities:
            source_note = _normalize_text(entity.get("source_note_id"))
            if source_note:
                note_ids.add(source_note)
        focus_entity_ids = {str(entity.get("id")) for entity in matched_entities if entity.get("id")}
        for relation in relations:
            if (
                relation.get("source_entity_id") in focus_entity_ids
                or relation.get("target_entity_id") in focus_entity_ids
            ):
                source_note = _normalize_text(relation.get("source_note_id"))
                if source_note:
                    note_ids.add(source_note)
        for marker in markers[:20]:
            source_note = _normalize_text(getattr(marker, "source_note_id", ""))
            if source_note:
                note_ids.add(source_note)

        notes_by_id = {str(note.get("id")): note for note in notes}
        chosen_notes = [notes_by_id[note_id] for note_id in note_ids if note_id in notes_by_id]
        if len(chosen_notes) < 4:
            ranked = self._rank_notes_for_query(question, notes)
            for note in ranked:
                if note not in chosen_notes:
                    chosen_notes.append(note)
                if len(chosen_notes) >= 6:
                    break

        lines: list[str] = []
        refs: list[str] = []
        if not chosen_notes:
            lines.append("No note evidence candidates found.")
            return self._section("EvidencePack", lines), refs

        for note in chosen_notes[:6]:
            note_id = str(note.get("id") or "")
            title = _truncate_text(str(note.get("title") or "(untitled)"), 90)
            snippet = _truncate_text(str(note.get("content") or ""), 280)
            refs.append(f"note:{note_id}")
            lines.append(f"- note_id={note_id} | title={title}")
            lines.append(f"  snippet: {snippet}")
            lines.append(f"  updated_at: {_normalize_text(note.get('updated_at')) or '-'}")

        return self._section("EvidencePack", lines), refs

    async def _build_snapshot_delta_pack(
        self,
        world_id: str,
        question: str,
        markers: list[Any],
        matched_entities: list[dict[str, Any]],
    ) -> tuple[str, list[str]]:
        lines: list[str] = []
        refs: list[str] = []
        if not markers:
            return self._section("SnapshotDeltaPack", ["No timeline markers available for delta analysis."]), refs

        marker_candidates = self._match_markers(
            question=question,
            markers=markers,
            matched_entity_names=[str(entity.get("name") or "") for entity in matched_entities],
            limit=1,
        )
        anchor = marker_candidates[0] if marker_candidates else markers[-1]
        placed = [marker for marker in markers if getattr(marker, "placement_status", "") == "placed"]
        ordered = placed if placed else markers
        ordered_by_id = {marker.id: idx for idx, marker in enumerate(ordered)}
        anchor_index = ordered_by_id.get(anchor.id, len(ordered) - 1)
        previous_marker = ordered[anchor_index - 1] if anchor_index > 0 else None

        refs.append(f"marker:{anchor.id}")
        lines.append(f"- anchor_marker: {anchor.title} ({anchor.id}) sort_key={anchor.sort_key}")
        if previous_marker:
            refs.append(f"marker:{previous_marker.id}")
            lines.append(f"- previous_marker: {previous_marker.title} ({previous_marker.id}) sort_key={previous_marker.sort_key}")
        else:
            lines.append("- previous_marker: baseline world state (no prior marker)")

        try:
            before_state = await self.timeline_service.get_world_state(
                world_id=world_id,
                marker_id=previous_marker.id if previous_marker else None,
            )
            after_state = await self.timeline_service.get_world_state(world_id=world_id, marker_id=anchor.id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed snapshot delta build world_id=%s marker_id=%s error=%s", world_id, anchor.id, exc)
            lines.append("- delta: unavailable (world-state projection failed)")
            return self._section("SnapshotDeltaPack", lines), refs

        before_entities = {entity.id for entity in before_state.entities if entity.exists_at_marker}
        after_entities = {entity.id for entity in after_state.entities if entity.exists_at_marker}
        before_relations = {relation.id for relation in before_state.relations if relation.exists_at_marker}
        after_relations = {relation.id for relation in after_state.relations if relation.exists_at_marker}

        added_entities = sorted(after_entities - before_entities)
        removed_entities = sorted(before_entities - after_entities)
        added_relations = sorted(after_relations - before_relations)
        removed_relations = sorted(before_relations - after_relations)

        lines.append(
            f"- entity_delta: +{len(added_entities)} / -{len(removed_entities)} | relation_delta: +{len(added_relations)} / -{len(removed_relations)}"
        )
        if added_entities:
            lines.append(f"  added_entities: {', '.join(added_entities[:8])}")
        if removed_entities:
            lines.append(f"  removed_entities: {', '.join(removed_entities[:8])}")
        if added_relations:
            lines.append(f"  added_relations: {', '.join(added_relations[:8])}")
        if removed_relations:
            lines.append(f"  removed_relations: {', '.join(removed_relations[:8])}")

        focus_entity_ids = {str(entity.get("id")) for entity in matched_entities if entity.get("id")}
        if focus_entity_ids:
            impacted = [
                entity_id
                for entity_id in focus_entity_ids
                if (entity_id in added_entities or entity_id in removed_entities or entity_id in after_entities)
            ]
            lines.append(f"- focus_entity_impact_ids: {', '.join(impacted[:8]) if impacted else 'none'}")

        lines.append(
            "- assumptions: use this delta as branch context only; preserve rules/invariants unless user explicitly overrides them."
        )
        return self._section("SnapshotDeltaPack", lines), refs

    async def build_context(self, world_id: str, question: str) -> ContextPackBuildResult:
        db = await self._get_db()
        try:
            entities = await self._list_entities(db, world_id)
            relations = await self._list_relations(db, world_id)
            notes = await self._list_notes(db, world_id)
            rules_doc_meta = await self._get_rules_doc_meta(db, world_id)
        finally:
            await db.close()

        matched_entities = self._match_entities(question=question, entities=entities)
        intent_decision = self._classify_intent(question=question, matched_entities=matched_entities)
        profile = INTENT_CATALOG[intent_decision.intent]

        needs_timeline = "TimelinePack" in profile.packs or "SnapshotDeltaPack" in profile.packs
        markers: list[Any] = []
        if needs_timeline:
            try:
                markers = await self.timeline_service.list_markers(world_id, include_operations=True)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed loading markers for historian context world_id=%s error=%s", world_id, exc)

        sections: list[str] = []
        refs: list[str] = []
        for pack in profile.packs:
            if pack == "EntityPack":
                section, pack_refs = self._build_entity_pack(matched_entities)
            elif pack == "RelationPack":
                section, pack_refs = self._build_relation_pack(matched_entities, relations, intent_decision.intent)
            elif pack == "TimelinePack":
                section, pack_refs = await self._build_timeline_pack(
                    world_id=world_id,
                    question=question,
                    intent=intent_decision.intent,
                    matched_entities=matched_entities,
                    markers=markers,
                )
            elif pack == "RulePack":
                section, pack_refs = self._build_rule_pack(rules_doc_meta)
            elif pack == "EvidencePack":
                section, pack_refs = self._build_evidence_pack(
                    question=question,
                    notes=notes,
                    matched_entities=matched_entities,
                    relations=relations,
                    markers=markers,
                )
            elif pack == "SnapshotDeltaPack":
                section, pack_refs = await self._build_snapshot_delta_pack(
                    world_id=world_id,
                    question=question,
                    markers=markers,
                    matched_entities=matched_entities,
                )
            else:  # pragma: no cover - defensive
                section, pack_refs = "", []

            if section:
                sections.append(section)
            refs.extend(pack_refs)

        deduped_refs = tuple(dict.fromkeys(ref for ref in refs if ref))
        context_pack = "\n\n".join(sections).strip()
        context_pack = _truncate_text(context_pack, MAX_CONTEXT_CHARS)

        return ContextPackBuildResult(
            intent=intent_decision.intent,
            confidence=intent_decision.confidence,
            reason=intent_decision.reason,
            strategy=profile.strategy,
            packs_used=profile.packs,
            context_pack=context_pack,
            evidence_refs=deduped_refs,
        )
