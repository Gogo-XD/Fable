# Rules and Invariants
World: Test World 2
Generated at (UTC): 2026-02-08T08:27:29.566303+00:00
World description: N/A

This document stores explicit and derived canon constraints.

## World taxonomies
- entity_types: character, location, event, item, organization, concept
- relation_types: ally_of, enemy_of, parent_of, child_of, located_in, participated_in, member_of

## Canon system constraints
- timeline_marker_kind must be explicit or semantic
- timeline_target_kind must be entity, relation, or world
- timeline op types in this project: entity_create/entity_patch/entity_delete, relation_create/relation_patch/relation_delete, world_patch
- relation endpoints must reference valid entity ids

## Snapshot of current canonical volume
- entities: 35
- relations: 41
- timeline_markers: 14
- timeline_operations: 66

## Recommended spare slots (not compiled yet)
- aliases_disambiguation: Aliases and Disambiguation
- open_questions_retcons: Open Questions and Retcons
- recent_changes_changelog: Recent Changes Changelog
- mechanics_deep_dive: Mechanics Deep Dive
