from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    TRANSCRIBE = "transcribe"
    SUMMARIZE = "summarize"
    ACTIONIZE = "actionize"
    FUNCTION_CALL = "function_call"
    ACOUSTIC_REPAIR = "acoustic_repair"
    SEMANTIC_REPAIR = "semantic_repair"
    VERIFY = "verify"
    RESPOND = "respond"
    SYNTHESIZE = "synthesize"


OPERATIONAL_ROLES = {Role.TRANSCRIBE, Role.SUMMARIZE, Role.ACTIONIZE, Role.FUNCTION_CALL}
RESERVED_ROLES = set(Role) - OPERATIONAL_ROLES


class CapabilityProvenance(str, Enum):
    DOCUMENTED = "DOCUMENTED"
    DISCOVERED = "DISCOVERED"
    VERIFIED_LOCAL = "VERIFIED_LOCAL"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class ExecutionMode(str, Enum):
    LOCAL = "LOCAL"
    DEMO_RULES = "DEMO_RULES"
    TEST_FIXTURE = "TEST_FIXTURE"
    DISABLED = "DISABLED"


class RunStatus(str, Enum):
    READY = "READY"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    BLOCKED = "BLOCKED"
    UNAVAILABLE_LOCAL_MODEL = "UNAVAILABLE_LOCAL_MODEL"
    NO_ACTION = "NO_ACTION"
    STALE = "STALE"


class LabelState(str, Enum):
    CANDIDATE = "CANDIDATE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    REJECTED = "REJECTED"


class RoleBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str
    model_id: str
    revision_or_digest: str | None = None
    role: Role
    prompt_version: str
    schema_version: str
    generation: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode
    capability_provenance: CapabilityProvenance
    capabilities: list[str] = Field(default_factory=list)
    available: bool = True
    unavailable_reason: str | None = None
    tool_mode: Literal["NATIVE", "JSON_EMULATION", "NONE"] = "NONE"


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    version: str = "1"
    bindings: dict[str, RoleBinding]
    action_mode: Literal["DIRECT", "TWO_STAGE"]
    summary_branch: bool = True
    locked_roles: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=lambda: ["summary", "proposal"])
    created_by: str = "local-user"


class SourceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int
    end: int
    text: str


class SummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RunStatus
    summary: str | None = None
    supporting_spans: list[SourceSpan] = Field(default_factory=list)
    evidence_type: str
    review_required: bool = True
    calibrated_correctness: None = None


class SemanticPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RunStatus
    intent: str
    entities: dict[str, Any] = Field(default_factory=dict)
    corrections: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    supporting_spans: list[SourceSpan] = Field(default_factory=list)
    evidence_type: str


class ToolProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: RunStatus
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    source_revision: int
    supporting_spans: list[SourceSpan] = Field(default_factory=list)
    tool_mode: Literal["NATIVE", "JSON_EMULATION", "NONE"]
    evidence_type: str
    explanation: str | None = None


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=12_000)
    recipe_id: str = "demo_direct_v1"
    recording_id: str | None = None
    manual_transcript: bool = False
    reference_timestamp: str = "2026-09-11T09:00:00+03:00"
    timezone: str = "Asia/Riyadh"


class TranscriptEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=12_000)
    expected_revision: int = Field(ge=1)


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str


class TournamentStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["Cost", "Speed", "Performance", "Manual"]
    recipe_ids: list[str] = Field(default_factory=lambda: ["demo_direct_v1", "demo_two_stage_v1"])
    dataset_id: Literal["AUTHORED_SMOKE_FIXTURE", "SEED_HUMAN_EVAL"] = "AUTHORED_SMOKE_FIXTURE"
    case_limit: int = Field(default=12, ge=1, le=30)
    total_call_cap: int = Field(default=72, ge=1, le=240)
    quality_floor: float = Field(default=0.70, ge=0, le=1)
    confirmed: bool = False


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_state: LabelState
    reviewer_type: Literal["human", "ai", "unknown"] = "unknown"
    reviewer_identity: str | None = Field(default=None, max_length=100)
    promotion_reason: str | None = Field(default=None, max_length=500)


class SeedHumanCaseCreate(BaseModel):
    """A user-reviewed reference; it is never inferred from a model output."""

    recording_id: str
    reviewed_transcript: str = Field(min_length=1, max_length=12_000)
    expected_status: RunStatus
    expected_tool_name: str | None = Field(default=None, max_length=100)
    expected_arguments: dict[str, Any] = Field(default_factory=dict)
    requires_clarification: bool = False
    critical_spans: list[dict[str, str]] = Field(default_factory=list, max_length=30)
    reviewer_identity: str | None = Field(default=None, max_length=100)
    recording_session_id: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
