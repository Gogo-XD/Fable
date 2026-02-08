"""Prompt builders shared across services."""


def build_world_assistant_prompt(world_name: str, description: str = "") -> str:
    return (
        f"You are a worldbuilding assistant for the world '{world_name}'. "
        f"{description} "
        "When analyzing notes, extract entities, relations, and timeline markers as structured JSON. "
        "Be precise with names and types. Reuse existing entity names when possible. "
        "For timeline changes, use only: entity_create/entity_patch/entity_delete, relation_create/relation_patch/relation_delete, world_patch."
    )


def build_historian_turn_prompt(
    user_message: str,
    allow_history_reference: bool,
    primary_target: str | None = None,
    intent: str | None = None,
    intent_confidence: float | None = None,
    intent_strategy: str | None = None,
    packs_used: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    context_pack: str | None = None,
) -> str:
    speculative_intents = {
        "counterfactual_remove_event",
        "counterfactual_change_decision",
        "projection_plausible_future",
        "creative_constrained",
    }
    is_speculative = intent in speculative_intents

    history_rule = (
        "The user may be referring to prior turns. You may use prior thread messages only to resolve references,"
        " but keep the answer focused on the current question."
        if allow_history_reference
        else "Treat this as a standalone question. Do not include facts about earlier turns unless required"
        " to answer this exact question."
    )

    target_rule = (
        f"- Primary target for this question: {primary_target}. Keep the answer centered on this target.\n"
        "- Mention other entities only when directly required."
        if primary_target
        else ""
    )
    intent_line = f"- intent: {intent}" if intent else "- intent: unknown"
    confidence_line = f"- intent_confidence: {intent_confidence:.2f}" if intent_confidence is not None else "- intent_confidence: n/a"
    strategy_line = f"- strategy: {intent_strategy}" if intent_strategy else "- strategy: n/a"
    packs_line = f"- packs_used: {', '.join(packs_used)}" if packs_used else "- packs_used: none"
    evidence_text = "\n".join(f"- {ref}" for ref in (evidence_refs or [])[:20]) or "- (none provided)"
    context_text = context_pack or "(no targeted context pack available)"
    mode_rules = (
        "This is a hypothetical/alternative-history task.\n"
        "Do not refuse because it is hypothetical.\n"
        "Infer plausible outcomes from known records, timeline dynamics, relations, and rules.\n"
        "Present 2-4 assumptions, then likely ripple effects, then the most likely outcome."
        if is_speculative
        else "This is primarily factual QA. Separate confirmed record from inference when needed."
    )
    mode_rules_block = "\n".join(f"- {line}" for line in mode_rules.splitlines() if line.strip())
    unknown_rule = (
        "If records are sparse, speak in-world: say the chronicles are unclear, then give the closest plausible reading."
        if intent == "unknown_gap"
        else "If uncertain, state uncertainty in-world and provide the best-supported answer."
    )

    return f"""You are the Historian NPC.

Answering rules:
- Answer only the user's current question.
- {history_rule}
- If the question is about one person/place/event, keep the response centered on that target.
- Do not add unsolicited sections about other entities.
- If ambiguity remains, ask one short clarifying question instead of guessing.
- Stay in character as an in-world historian.
- Never mention being an AI, model, assistant thread, system prompt, context pack, or "outside canon."
- Ground answers in known world records and relationships.
- {unknown_rule}
{mode_rules_block}
- Prefer the context packs below over thread memory for factual grounding.
- Only include explicit id-style provenance markers if the user asks for sources/citations.
{target_rule}

Intent routing:
{intent_line}
{confidence_line}
{strategy_line}
{packs_line}

Output style:
- Write in natural spoken prose, as if speaking directly to the user.
- Do not use markdown headings, bullet lists, numbered lists, tables, or code blocks.
- Prefer 1-3 short paragraphs with smooth transitions.
- Keep wording clear and conversational.

Evidence IDs:
{evidence_text}

Context packs:
{context_text}

Current user question:
{user_message}
"""


def build_analysis_prompt(
    note_title: str | None,
    note_content: str,
    entity_context: str,
    chunk_index: int | None = None,
    chunk_total: int | None = None,
) -> str:
    chunk_scope = ""
    if chunk_index is not None and chunk_total is not None and chunk_total > 1:
        chunk_scope = (
            f"\nCHUNK SCOPE:\n"
            f"- You are analyzing chunk {chunk_index}/{chunk_total} of one larger note.\n"
            f"- Extract only facts present in this chunk.\n"
            f"- Do not invent cross-chunk details.\n"
            f"- Keep output compact for this chunk: max 25 entities, 35 relations, 6 timeline markers, 12 changes per marker.\n"
        )

    return f"""Analyze the following worldbuilding note. Extract all entities (characters, locations, events, items, organizations, concepts), relations between them, and timeline markers.

For each entity, provide: name, type, subtype (if applicable), aliases, a short summary, context (detailed description), and tags.
For each relation, provide: source entity name, target entity name, relation type, and context describing the relation.
For each timeline marker, provide: title, summary, marker_kind ("explicit" or "semantic"), date_label (if known), date_sort_value (number if explicit and known), and a list of changes.
For each change, provide: op_type, target_kind ("entity", "relation", or "world"), and payload.
For entity changes include target_name.
For relation changes include source_name, target_name, relation_type.

Allowed op_type values only:
- entity_create, entity_patch, entity_delete
- relation_create, relation_patch, relation_delete
- world_patch
Do not use generic forms like "operation_patch", "update", "remove", etc.
If the note indicates a character/entity dies or is permanently removed, use entity_delete (not entity_patch) and include payload.status when known (e.g., "deceased").
Use entity_patch for attribute/context/status updates.

If an entity matches one already known in this world (by name or alias), use the EXACT existing name.
If timeline ordering is unclear (semantic marker), still include the marker with marker_kind = "semantic".

{entity_context}

---
NOTE TITLE:
{note_title or "(untitled)"}

---
NOTE CONTENT:
{note_content}
---
{chunk_scope}

Respond with ONLY valid JSON in this exact format:
{{
  "entities": [
    {{
      "name": "...",
      "type": "...",
      "subtype": null,
      "aliases": [],
      "summary": "...",
      "context": "...",
      "tags": []
    }}
  ],
  "relations": [
    {{
      "source_name": "...",
      "target_name": "...",
      "type": "...",
      "context": "..."
    }}
  ],
  "timeline_markers": [
    {{
      "title": "...",
      "summary": "...",
      "marker_kind": "explicit",
      "date_label": "1205",
      "date_sort_value": 1205,
      "changes": [
        {{
          "op_type": "entity_patch",
          "target_kind": "entity",
          "target_name": "Character A",
          "source_name": null,
          "relation_type": null,
          "payload": {{
            "context": "Character A perished in battle.",
            "summary": "Deceased.",
            "status": "deceased"
          }}
        }}
      ]
    }}
  ]
}}"""


def build_context_merge_prompt(
    entity_name: str,
    entity_type: str,
    existing_context: str | None,
    incoming_context: str | None,
) -> str:
    return f"""Merge and enrich two context snippets for the same worldbuilding entity.

Entity:
- name: {entity_name}
- type: {entity_type}

Existing context:
{existing_context or "(none)"}

Incoming context:
{incoming_context or "(none)"}

Instructions:
- Produce one merged context paragraph(s) that is coherent, deduplicated, and fact-preserving.
- Keep concrete details (names, places, dates, roles, artifacts, organizations, events).
- Do not invent new facts.
- If one context is empty, return a polished version of the non-empty one.
- Return only the merged context text, no JSON, no markdown."""


def build_canon_guardian_soft_critic_prompt(
    note_title: str | None,
    note_content: str,
    context_pack: str,
) -> str:
    return f"""You are the Canon Guardian soft-contradiction critic for a worldbuilding knowledge base.

Task:
- Review the note against the provided context.
- Find only SOFT contradictions/tensions (ambiguity, subtle inconsistency, missing bridge, tonal mismatch, implied timeline tension).
- Do NOT return hard schema errors (invalid IDs, malformed op types, etc.) unless they are required to explain a soft contradiction.
- Do NOT invent facts not grounded in the note/context.

Output rules:
- Return JSON only.
- Keep findings concise and evidence-based.
- confidence must be between 0 and 1.
- finding_code must start with "soft_".
- severity must be one of: critical, high, medium, low, info.
- evidence ids must reference only ids present in the context pack.

NOTE TITLE:
{note_title or "(untitled)"}

NOTE CONTENT:
{note_content}

CONTEXT PACK:
{context_pack}

Respond in this exact JSON shape:
{{
  "soft_findings": [
    {{
      "finding_code": "soft_temporal_tension",
      "severity": "low",
      "title": "Short finding title",
      "detail": "Clear explanation of the soft contradiction.",
      "confidence": 0.72,
      "evidence": [
        {{"kind": "note", "id": "note-id", "snippet": "optional snippet"}},
        {{"kind": "entity", "id": "entity-id", "snippet": "optional snippet"}}
      ],
      "suggested_action": {{
        "action_type": "noop",
        "op_type": null,
        "target_kind": null,
        "target_id": null,
        "payload": {{}},
        "rationale": "Short rationale"
      }}
    }}
  ]
}}"""


def build_canon_guardian_mechanic_prompt(
    world_id: str,
    run_id: str,
    findings_context: str,
) -> str:
    return f"""You are the Canon Guardian Mechanic.

Task:
- Convert unresolved guardian findings into actionable remediation options.
- Prioritize safe, minimal, high-confidence changes.
- If uncertain, return action_type "noop" with clear rationale.
- Do not invent IDs that are not present in the context.

Allowed action_type values:
- timeline_operation
- entity_patch
- relation_patch
- entity_delete
- relation_delete
- world_patch
- noop

Allowed target_kind values:
- entity
- relation
- world

Output rules:
- Return JSON only.
- confidence must be between 0 and 1.
- risk_level must be one of: low, medium, high.
- finding_id must reference a provided finding.

WORLD ID: {world_id}
RUN ID: {run_id}

FINDINGS CONTEXT:
{findings_context}

Return JSON in this exact shape:
{{
  "options": [
    {{
      "finding_id": "finding-id",
      "action_type": "relation_patch",
      "op_type": null,
      "target_kind": "relation",
      "target_id": "relation-id",
      "payload": {{
        "context": "Updated relation context"
      }},
      "rationale": "Why this fixes the issue",
      "expected_outcome": "What should improve",
      "risk_level": "low",
      "confidence": 0.82
    }}
  ]
}}"""

