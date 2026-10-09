"""Provider boundaries only. Phase 1 includes no generation or analysis execution."""

from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    OUTCOME_UNKNOWN = "outcome_unknown"


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    status: Literal["planned", "unverified", "disabled", "available"]
    description: str
    analysis: bool = False
    generation: bool = False
    editing: bool = False
    multiple_references: bool = False
    masks: bool = False
    status_lookup: bool = False
    idempotency: bool = False
    sends_images_externally: bool = False
    formats: tuple[str, ...] = ()
    resolutions: tuple[str, ...] = ()
    max_references: int | None = None
    pricing: str


class AnalysisRequest(BaseModel):
    scene_id: str
    base_asset_id: str
    schema_version: int = Field(ge=1)


class AnalysisResult(BaseModel):
    schema_version: int = Field(ge=1)
    analysis: dict
    uncertainties: list[str]


class ApprovedGenerationRequest(BaseModel):
    # The future application service must load and validate this immutable approval
    # from SQLite. Client-provided identifiers/hashes are never proof of approval.
    approval_id: str
    snapshot_hash: str
    snapshot: dict


class GenerationReceipt(BaseModel):
    status: JobStatus
    provider_request_id: str | None = None
    output_asset_ids: tuple[str, ...] = ()


class AnalysisProvider(Protocol):
    capabilities: ProviderCapabilities

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult: ...


class GenerationProvider(Protocol):
    capabilities: ProviderCapabilities

    async def generate(self, request: ApprovedGenerationRequest) -> GenerationReceipt: ...


PROVIDERS = (
    ProviderCapabilities(
        id="manual_bridge",
        name="Manual bridge",
        status="planned",
        description="Prepare approved packages for Codex or ChatGPT, then import your results.",
        pricing="No API calls from Character Studio. External service usage limits still apply.",
    ),
    ProviderCapabilities(
        id="codex_direct",
        name="Direct Codex integration",
        status="unverified",
        description="A supported application-to-Codex image generation connection is not verified.",
        pricing="Unavailable; no requests can be submitted.",
    ),
    ProviderCapabilities(
        id="openai_api",
        name="OpenAI API",
        status="disabled",
        description="Separate API billing is outside the approved scope.",
        pricing="Disabled. No API credentials are requested or used.",
    ),
)
