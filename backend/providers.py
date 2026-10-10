"""Provider registry. Analysis runs through the official CLIs (D009); generation is Phase 5."""

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
        id="claude_cli",
        name="Claude Code CLI",
        status="available",
        description="Scene analysis with your own Claude sign-in. Runs only when you click "
        "Analyse; sends the Base Image to Anthropic.",
        analysis=True,
        sends_images_externally=True,
        pricing="Uses your Claude plan's usage allowance. No API key or per-use billing.",
    ),
    ProviderCapabilities(
        id="codex_cli",
        name="Codex CLI",
        status="available",
        description="Scene analysis with your own ChatGPT sign-in; sends the Base Image to "
        "OpenAI. Image generation arrives in Phase 5.",
        analysis=True,
        sends_images_externally=True,
        pricing="Uses your ChatGPT plan's Codex allowance, which image generation shares.",
    ),
    ProviderCapabilities(
        id="manual_bridge",
        name="Manual bridge",
        status="available",
        description="Copy the analysis instruction into another app, then paste its reply back.",
        analysis=True,
        pricing="No calls from Character Studio. The other app's usage limits apply.",
    ),
    ProviderCapabilities(
        id="openai_api",
        name="OpenAI API",
        status="disabled",
        description="Separate API billing is outside the approved scope.",
        pricing="Disabled. No API credentials are requested or used.",
    ),
)
