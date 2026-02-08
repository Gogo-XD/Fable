"""
Fable models.

Usage:
    from app.models import Entity, EntityCreate, World, Relation, Note
    from app.models import EntitySource, NoteStatus, normalize_type
    from app.models import NoteAnalysisResult, EntityExtraction, RelationExtraction
"""

# --- Enums & utilities ---
from app.models.enums import (
    EntitySource,
    NoteStatus,
    EntityResolutionStatus,
    normalize_type,
)

# --- Domain models ---
from app.models.domain import (
    World, WorldCreate, WorldUpdate,
    RagCompileRequest, RagDocumentSyncStatusResult, RagCompileResult,
    Entity, EntityCreate, EntityUpdate,
    Relation, RelationCreate, RelationUpdate,
    Note, NoteCreate, NoteUpdate,
    HistorianMessageRequest, HistorianMessageResponse,
    TimelineMarker, TimelineMarkerCreate, TimelineMarkerUpdate, TimelineMarkerReposition,
    TimelineOperation, TimelineOperationCreate, TimelineOperationUpdate,
    TimelineSnapshot, TimelineSnapshotUpsert, TimelineWorldState, TimelineRebuildResult,
    GuardianScanRequest, GuardianEvidenceRef, GuardianFinding, GuardianAction,
    GuardianRun, GuardianRunDetail, GuardianScanAccepted,
    GuardianApplyRequest, GuardianApplyResult, GuardianFindingStatusUpdate,
    MechanicGenerateRequest, MechanicRun, MechanicOption, MechanicRunDetail,
    MechanicGenerateAccepted, MechanicAcceptRequest, MechanicAcceptResult,
)

# --- Result models ---
from app.models.results import (
    BackboardResult,
    AssistantCreated, ThreadCreated, ThreadDeleted,
    DocumentCreated, DocumentUpdated, ChatResponse,
    EntityExtraction, RelationExtraction,
    TimelineMarkerChangeExtraction, TimelineMarkerExtraction,
    NoteAnalysisResult,
)

__all__ = [
    # Enums
    "EntitySource", "NoteStatus", "EntityResolutionStatus", "normalize_type",
    # Domain
    "World", "WorldCreate", "WorldUpdate",
    "RagCompileRequest", "RagDocumentSyncStatusResult", "RagCompileResult",
    "Entity", "EntityCreate", "EntityUpdate",
    "Relation", "RelationCreate", "RelationUpdate",
    "Note", "NoteCreate", "NoteUpdate",
    "HistorianMessageRequest", "HistorianMessageResponse",
    "TimelineMarker", "TimelineMarkerCreate", "TimelineMarkerUpdate", "TimelineMarkerReposition",
    "TimelineOperation", "TimelineOperationCreate", "TimelineOperationUpdate",
    "TimelineSnapshot", "TimelineSnapshotUpsert", "TimelineWorldState", "TimelineRebuildResult",
    "GuardianScanRequest", "GuardianEvidenceRef", "GuardianFinding", "GuardianAction",
    "GuardianRun", "GuardianRunDetail", "GuardianScanAccepted",
    "GuardianApplyRequest", "GuardianApplyResult", "GuardianFindingStatusUpdate",
    "MechanicGenerateRequest", "MechanicRun", "MechanicOption", "MechanicRunDetail",
    "MechanicGenerateAccepted", "MechanicAcceptRequest", "MechanicAcceptResult",
    # Results
    "BackboardResult",
    "AssistantCreated", "ThreadCreated", "ThreadDeleted",
    "DocumentCreated", "DocumentUpdated", "ChatResponse",
    "EntityExtraction", "RelationExtraction",
    "TimelineMarkerChangeExtraction", "TimelineMarkerExtraction",
    "NoteAnalysisResult",
]
