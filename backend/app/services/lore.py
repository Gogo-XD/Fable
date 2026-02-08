"""Facade service preserving the original LoreService API."""

from app.models import (
    Entity,
    EntityCreate,
    EntityUpdate,
    Relation,
    RelationCreate,
    RelationUpdate,
    Note,
    NoteCreate,
    NoteUpdate,
)
from app.services.backboard import BackboardService
from app.services.lore_entities import LoreEntityService
from app.services.lore_notes import LoreNoteService
from app.services.lore_relations import LoreRelationService
from app.services.timeline import TimelineService


class LoreService:
    """Compatibility facade delegating to focused lore services."""

    def __init__(
        self,
        db_path: str,
        backboard: BackboardService,
        timeline_service: TimelineService,
    ):
        self.entities = LoreEntityService(
            db_path=db_path,
            backboard=backboard,
        )
        self.relations = LoreRelationService(db_path=db_path)
        self.notes = LoreNoteService(
            db_path=db_path,
            backboard=backboard,
            entity_service=self.entities,
            relation_service=self.relations,
            timeline_service=timeline_service,
        )

    # Entities
    async def create_entity(self, world_id: str, data: EntityCreate) -> Entity:
        return await self.entities.create_entity(world_id, data)

    async def get_entity(self, world_id: str, entity_id: str) -> Entity | None:
        return await self.entities.get_entity(world_id, entity_id)

    async def list_entities(
        self,
        world_id: str,
        type: str | None = None,
        subtype: str | None = None,
        tag: str | None = None,
        search: str | None = None,
    ) -> list[Entity]:
        return await self.entities.list_entities(
            world_id,
            type=type,
            subtype=subtype,
            tag=tag,
            search=search,
        )

    async def update_entity(
        self, world_id: str, entity_id: str, data: EntityUpdate
    ) -> Entity | None:
        return await self.entities.update_entity(world_id, entity_id, data)

    async def delete_entity(self, world_id: str, entity_id: str) -> bool:
        return await self.entities.delete_entity(world_id, entity_id)

    # Relations
    async def create_relation(self, world_id: str, data: RelationCreate) -> Relation:
        return await self.relations.create_relation(world_id, data)

    async def get_relation(self, world_id: str, relation_id: str) -> Relation | None:
        return await self.relations.get_relation(world_id, relation_id)

    async def list_relations(
        self,
        world_id: str,
        entity_id: str | None = None,
        type: str | None = None,
    ) -> list[Relation]:
        return await self.relations.list_relations(
            world_id,
            entity_id=entity_id,
            type=type,
        )

    async def update_relation(
        self, world_id: str, relation_id: str, data: RelationUpdate
    ) -> Relation | None:
        return await self.relations.update_relation(world_id, relation_id, data)

    async def delete_relation(self, world_id: str, relation_id: str) -> bool:
        return await self.relations.delete_relation(world_id, relation_id)

    # Notes
    async def create_note(self, world_id: str, data: NoteCreate) -> Note:
        return await self.notes.create_note(world_id, data)

    async def get_note(self, world_id: str, note_id: str) -> Note | None:
        return await self.notes.get_note(world_id, note_id)

    async def list_notes(self, world_id: str) -> list[Note]:
        return await self.notes.list_notes(world_id)

    async def update_note(
        self, world_id: str, note_id: str, data: NoteUpdate
    ) -> Note | None:
        return await self.notes.update_note(world_id, note_id, data)

    async def delete_note(self, world_id: str, note_id: str) -> bool:
        return await self.notes.delete_note(world_id, note_id)

    async def analyze_note(self, world_id: str, note_id: str) -> dict:
        return await self.notes.analyze_note(world_id, note_id)

    async def analyze_all_unanalyzed_notes(self, world_id: str) -> dict:
        return await self.notes.analyze_all_unanalyzed_notes(world_id)
