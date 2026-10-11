"""Explicit local configuration; importing this module never creates application data."""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIRECTORIES = (
    "characters",
    "scenes",
    "generations",
    "thumbnails",
    "exports",
    "backups",
    "jobs",
)


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_dir: Path
    port: int = Field(default=8765, ge=1024, le=65535)
    frontend_dir: Path = PROJECT_ROOT / "frontend" / "dist"
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    max_image_pixels: int = Field(default=40_000_000, ge=1, le=100_000_000)
    # Tests only: replace the official CLIs with fakes. Never read from the environment.
    engine_commands: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    # Tests only: point API engines at a local fake server. Never read from the environment.
    api_base_urls: dict[str, str] = Field(default_factory=dict)

    @field_validator("data_dir")
    @classmethod
    def external_directory(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.is_absolute():
            raise ValueError("STUDIO_DATA_DIR must be an absolute path outside the repository.")
        resolved = value.resolve()
        if resolved.is_relative_to(PROJECT_ROOT) or PROJECT_ROOT.is_relative_to(resolved):
            raise ValueError("Application data must not overlap the source repository.")
        return resolved

    @property
    def allowed_origins(self) -> set[str]:
        return {
            f"http://{host}:{port}"
            for host in ("127.0.0.1", "localhost")
            for port in (self.port, 5173)
        }


def load_settings() -> Settings:
    return Settings(
        # A packaged Windows app can virtualize LOCALAPPDATA. The user-profile
        # directory stays consistent when launched from Codex or Explorer.
        data_dir=Path(
            os.environ.get("STUDIO_DATA_DIR", str(Path.home() / "Character-Studio-Data"))
        ),
        port=os.environ.get("STUDIO_PORT", "8765"),
        max_upload_bytes=os.environ.get("STUDIO_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)),
    )


def asset_path(settings: Settings, relative_path: str) -> Path:
    """Resolve internal asset keys, rejecting traversal, absolute paths and escaping links."""
    # Reject Windows separators/drive syntax on every platform, not only Windows.
    if not relative_path or "\\" in relative_path or ":" in relative_path:
        raise ValueError("Invalid asset path.")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Asset paths must stay inside the data directory.")
    target = (settings.data_dir / relative).resolve()
    if target == settings.data_dir or not target.is_relative_to(settings.data_dir):
        raise ValueError("Asset paths must stay inside the data directory.")
    return target


def initialize_storage(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for name in ASSET_DIRECTORIES:
        asset_path(settings, name).mkdir(exist_ok=True)
    asset_path(settings, "studio.db")
