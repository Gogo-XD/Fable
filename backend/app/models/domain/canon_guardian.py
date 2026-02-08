"""Canon Guardian domain models."""

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


GuardianRunTriggerKind = Literal["note_scan", "manual", "api"]
GuardianRunStatus = Literal["queued", "running", "completed", "failed", "applied", "partial"]
GuardianFindingSeverity = Literal["critical", "high", "medium", "low", "info"]
GuardianFindingStatus = Literal["open", "accepted", "dismissed", "applied"]
GuardianActionStatus = Literal["proposed", "accepted", "applied", "rejected", "failed"]
GuardianActionType = Literal[
    "timeline_operation",
    "entity_patch",
    "relation_patch",
    "entity_delete",
    "relation_delete",
    "world_patch",
    "noop",
]
GuardianEvidenceKind = Literal["note", "entity", "relation", "timeline_marker", "timeline_operation", "world"]
MechanicRunStatus = Literal["queued", "running", "completed", "failed", "partial"]
MechanicOptionStatus = Literal["proposed", "accepted", "rejected", "applied", "failed"]
MechanicRiskLevel = Literal["low", "medium", "high"]


class GuardianScanRequest(BaseModel):
    """Request payload for starting a Canon Guardian scan."""

    marker_id: Optional[str] = None
    trigger_kind: GuardianRunTriggerKind = "manual"
    include_soft_checks: bool = True
    include_llm_critic: bool = False
    max_context_tokens: int = Field(default=1200, ge=200, le=12000)
    max_findings: int = Field(default=25, ge=1, le=200)
    dry_run: bool = True


class GuardianEvidenceRef(BaseModel):
    """Reference to an object that supports a finding."""

    kind: GuardianEvidenceKind
    id: str
    snippet: Optional[str] = None


class GuardianFinding(BaseModel):
    """A single Canon Guardian finding."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    world_id: str
    severity: GuardianFindingSeverity
    finding_code: str
    title: str
    detail: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    resolution_status: GuardianFindingStatus = "open"
    evidence: list[GuardianEvidenceRef] = Field(default_factory=list)
    suggested_action_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GuardianAction(BaseModel):
    """A proposed or applied remediation action for a finding."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    finding_id: Optional[str] = None
    world_id: str
    action_type: GuardianActionType = "noop"
    op_type: Optional[str] = None
    target_kind: Optional[str] = None
    target_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: Optional[str] = None
    status: GuardianActionStatus = "proposed"
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GuardianRun(BaseModel):
    """Metadata for a Canon Guardian run."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    world_id: str
    trigger_kind: GuardianRunTriggerKind = "manual"
    status: GuardianRunStatus = "queued"
    request: dict[str, Any] = Field(default_factory=dict)
    summary: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GuardianRunDetail(GuardianRun):
    """Detailed run payload including findings and actions."""

    findings: list[GuardianFinding] = Field(default_factory=list)
    actions: list[GuardianAction] = Field(default_factory=list)


class GuardianScanAccepted(BaseModel):
    """Response returned when a Canon Guardian scan is accepted."""

    status: str = "queued"
    run_id: str
    world_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GuardianApplyRequest(BaseModel):
    """Request payload for applying actions from a run."""

    action_ids: list[str] = Field(default_factory=list)
    apply_all: bool = False
    dry_run: bool = False


class GuardianApplyResult(BaseModel):
    """Result of attempting to apply Canon Guardian actions."""

    status: str
    run_id: str
    world_id: str
    requested_actions: int = 0
    accepted_actions: int = 0
    applied_actions: int = 0
    failed_actions: int = 0
    message: Optional[str] = None


class GuardianFindingStatusUpdate(BaseModel):
    """Result of updating a finding resolution status."""

    status: str
    run_id: str
    world_id: str
    finding_id: str
    resolution_status: GuardianFindingStatus


class MechanicGenerateRequest(BaseModel):
    """Request payload for generating mechanic options from guardian findings."""

    finding_ids: list[str] = Field(default_factory=list)
    include_open_findings: bool = True
    max_options: int = Field(default=25, ge=1, le=200)
    max_context_tokens: int = Field(default=1200, ge=200, le=12000)
    confidence_threshold: float = Field(default=0.55, ge=0.0, le=1.0)


class MechanicRun(BaseModel):
    """Metadata for a mechanic generation run."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    world_id: str
    run_id: str
    status: MechanicRunStatus = "queued"
    request: dict[str, Any] = Field(default_factory=dict)
    summary: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MechanicOption(BaseModel):
    """A single mechanic-proposed remediation option."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    mechanic_run_id: str
    world_id: str
    run_id: str
    finding_id: Optional[str] = None
    option_index: int = 0
    action_type: GuardianActionType = "noop"
    op_type: Optional[str] = None
    target_kind: Optional[str] = None
    target_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: Optional[str] = None
    expected_outcome: Optional[str] = None
    risk_level: MechanicRiskLevel = "medium"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: MechanicOptionStatus = "proposed"
    mapped_action_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MechanicRunDetail(MechanicRun):
    """Mechanic run details including generated options."""

    options: list[MechanicOption] = Field(default_factory=list)


class MechanicGenerateAccepted(BaseModel):
    """Response returned when a mechanic generation request is processed."""

    status: str
    mechanic_run_id: str
    world_id: str
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MechanicAcceptRequest(BaseModel):
    """Request payload for accepting generated mechanic options."""

    option_ids: list[str] = Field(default_factory=list)
    accept_all: bool = False
    create_guardian_actions: bool = True
    apply_immediately: bool = False


class MechanicAcceptResult(BaseModel):
    """Result of accepting mechanic options."""

    status: str
    mechanic_run_id: str
    world_id: str
    run_id: str
    requested_options: int = 0
    accepted_options: int = 0
    actions_created: int = 0
    actions_failed: int = 0
    applied_options: int = 0
    apply_failures: int = 0
    message: Optional[str] = None
