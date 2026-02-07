"""Prompt builders shared across services."""


def build_world_assistant_prompt(world_name: str, description: str = "") -> str:
    return (
        f"You are a worldbuilding assistant for the world '{world_name}'. "
        f"{description} "
        "When analyzing notes, extract entities and relations as structured JSON. "
        "Be precise with names and types. Reuse existing entity names when possible."
    )


def build_analysis_prompt(note_content: str, entity_context: str) -> str:
    return f"""Analyze the following worldbuilding note. Extract all entities (characters, locations, events, items, organizations, concepts) and relations between them.

For each entity, provide: name, type, subtype (if applicable), aliases, a short summary, context (detailed description), and tags.
For each relation, provide: source entity name, target entity name, relation type, and context describing the relation.

If an entity matches one already known in this world (by name or alias), use the EXACT existing name.

{entity_context}

---
NOTE CONTENT:
{note_content}
---

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

