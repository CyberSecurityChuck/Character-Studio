"""Provider registry: the official CLIs (D009), the manual bridge and the optional API engines.

API engines (Phase 6, D022) do nothing until the user saves a key, selects the engine
and confirms the possible charge for each run or batch.
"""

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
        description="Scene analysis and optional prompt polishing with your own Claude sign-in. "
        "Runs only when you click Analyse or Polish prompt; Analyse sends the Base Image to "
        "Anthropic, Polish sends the prompt text and the analysis.",
        analysis=True,
        sends_images_externally=True,
        pricing="Uses your Claude plan's usage allowance. No API key or per-use billing.",
    ),
    ProviderCapabilities(
        id="codex_cli",
        name="Codex CLI",
        status="available",
        description="Image generation and optional scene analysis with your own ChatGPT "
        "sign-in. Generate sends the Base Image and the approved reference photos to OpenAI; "
        "it runs only from a valid approval, once per click.",
        analysis=True,
        generation=True,
        multiple_references=True,
        sends_images_externally=True,
        formats=("png",),
        pricing="Uses your ChatGPT plan's Codex allowance; image generation uses it faster than "
        "text. No API key or per-use billing.",
    ),
    ProviderCapabilities(
        id="manual_bridge",
        name="Manual bridge",
        status="available",
        description="Copy the analysis instruction into another app and paste its reply back, "
        "or export an approved scene's package and import the image you make elsewhere.",
        analysis=True,
        generation=True,
        multiple_references=True,
        pricing="No calls from Character Studio. The other app's usage limits apply.",
    ),
    # Gemini was verified by the user's real analyses (Phase 6A + 6B review, 2026-10-12);
    # the Anthropic and OpenAI APIs stay "unverified" until a real run is observed.
    ProviderCapabilities(
        id="gemini_api",
        name="Gemini API",
        status="available",
        description="Scene analysis with your own Google AI Studio key. Analyse sends the "
        "Base Image, without location data, to Google.",
        analysis=True,
        sends_images_externally=True,
        formats=("jpeg",),
        pricing="Free-tier keys are not charged for analysis with free models; billed keys are "
        "charged per use. Each run asks for confirmation.",
    ),
    ProviderCapabilities(
        id="anthropic_api",
        name="Anthropic API",
        status="unverified",
        description="Scene analysis with your own Anthropic API key. Analyse sends the Base "
        "Image, without location data, to Anthropic.",
        analysis=True,
        sends_images_externally=True,
        formats=("jpeg",),
        pricing="Charged per use to your Anthropic API account. Each run asks for confirmation.",
    ),
    ProviderCapabilities(
        id="openai_api",
        name="OpenAI API",
        status="unverified",
        description="Scene analysis with your own OpenAI API key. Analyse sends the Base Image, "
        "without location data, to OpenAI.",
        analysis=True,
        sends_images_externally=True,
        formats=("jpeg",),
        pricing="Charged per use to your OpenAI API account. Each run asks for confirmation.",
    ),
    # Phase 6C-1 (D025): image generation with the same keys. Both stay "unverified" until
    # the user observes a real run; the assistant makes no paid calls.
    ProviderCapabilities(
        id="gemini_image",
        name="Gemini image",
        status="unverified",
        description="Image generation with your own Google AI Studio key on a billed project. "
        "Generate sends the Base Image and the approved reference photos, without location "
        "data, with the approved prompt to Google, once per confirmed run.",
        generation=True,
        editing=True,
        multiple_references=True,
        sends_images_externally=True,
        formats=("png", "jpeg"),
        resolutions=("1K", "2K", "4K"),
        max_references=14,
        pricing="Not on the free tier; charged per image. Each run asks for confirmation.",
    ),
    ProviderCapabilities(
        id="openai_images",
        name="OpenAI Images",
        status="unverified",
        description="Image generation with your own OpenAI API key (organisation verification "
        "required by OpenAI). Generate sends the Base Image and the approved reference photos, "
        "without location data, with the approved prompt to OpenAI, once per confirmed run.",
        generation=True,
        editing=True,
        multiple_references=True,
        masks=True,
        sends_images_externally=True,
        formats=("png",),
        resolutions=("1K", "2K"),
        pricing="Charged per image token to your OpenAI API account. Each run asks for "
        "confirmation.",
    ),
)
