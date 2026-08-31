from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProjectRequest(BaseModel):
    title: str = Field(default="Untitled Game", min_length=1, max_length=80)
    scene: str = Field(default="Scene 01", min_length=1, max_length=80)
    background: str = Field(default="", max_length=4_000)
    target_language: Literal["zh", "en", "ja"]
    script: str = Field(min_length=3, max_length=12_000)
    character_descriptions: dict[str, str] = Field(default_factory=dict)
    quality_threshold: int = Field(default=78, ge=50, le=100)
    max_retries: int = Field(default=1, ge=0, le=3)
    production_mode: Literal["draft", "production", "cinematic"] = "production"
    workflow_mode: Literal["single", "dialogue", "voice_pack"] = "dialogue"
    line_emotions: dict[int, str] = Field(default_factory=dict)
    line_addressees: dict[int, str] = Field(default_factory=dict)
    line_events: dict[int, str] = Field(default_factory=dict)
    line_variants: dict[int, int] = Field(default_factory=dict)
    locked_casting: list[dict[str, Any]] = Field(default_factory=list)
    run_origin: Literal["studio", "api", "eventarc-inbox"] = "api"

    @field_validator("script")
    @classmethod
    def script_has_dialogue(cls, value: str) -> str:
        if not any(":" in line or "：" in line for line in value.splitlines()):
            raise ValueError("Use one dialogue per line: Character: dialogue")
        return value.strip()

    @field_validator("character_descriptions")
    @classmethod
    def descriptions_are_bounded(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 10:
            raise ValueError("A maximum of 10 character references is supported.")
        cleaned: dict[str, str] = {}
        for character, description in value.items():
            name = character.strip()
            text = description.strip()
            if not name or len(name) > 80:
                raise ValueError("Character reference names must be 1-80 characters.")
            if len(text) > 1_000:
                raise ValueError(f"Description for {name} exceeds 1000 characters.")
            cleaned[name] = text
        return cleaned


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    scene: str = Field(default="Opening Scene", min_length=1, max_length=80)
    background: str = Field(min_length=3, max_length=4_000)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    scene: str | None = Field(default=None, min_length=1, max_length=80)
    background: str | None = Field(default=None, min_length=3, max_length=4_000)


class CharacterUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    brief: str = Field(min_length=1, max_length=1_000)


class VoiceSelectionCreate(BaseModel):
    voice: str = Field(min_length=1, max_length=40)


class VoicePreviewCreate(BaseModel):
    voice: str = Field(min_length=1, max_length=40)
    language: Literal["zh", "en", "ja"] = "zh"


class VoicePackEventSelection(BaseModel):
    event: str = Field(min_length=1, max_length=48)
    count: int = Field(ge=1, le=15)


class VoicePackDraftCreate(BaseModel):
    character_id: str = Field(min_length=1, max_length=40)
    language: Literal["zh", "en", "ja"] = "zh"
    events: list[VoicePackEventSelection] = Field(min_length=1, max_length=20)


class VoicePackLine(BaseModel):
    event: str = Field(min_length=1, max_length=48)
    event_label: str = Field(min_length=1, max_length=80)
    variant: int = Field(ge=1, le=15)
    emotion: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=500)


class DialogueCreate(BaseModel):
    emotion: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4_000)
    addressee_id: str | None = Field(default=None, max_length=40)


class DialogueRecord(BaseModel):
    id: str
    emotion: str
    text: str
    addressee_id: str | None = None
    order: int = 0


class CharacterRecastCreate(BaseModel):
    voice_presentation: Literal["auto", "feminine", "masculine", "neutral"] = "auto"


class CharacterRecord(BaseModel):
    id: str
    name: str
    brief: str
    image_filename: str
    image_mime_type: str
    image_storage_name: str
    casting: dict[str, Any]
    voice_presentation: Literal["auto", "feminine", "masculine", "neutral"] = "auto"
    voice_locked: bool = False
    dialogues: list[DialogueRecord] = Field(default_factory=list)


class ProjectRecord(BaseModel):
    id: str
    title: str
    scene: str
    background: str
    characters: list[CharacterRecord] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProductionCreate(BaseModel):
    target_language: Literal["zh", "en", "ja"]
    production_mode: Literal["draft", "production", "cinematic"] = "production"
    workflow_mode: Literal["single", "dialogue", "voice_pack"] = "dialogue"
    revision_limit: int = Field(default=2, ge=0, le=3)
    character_id: str | None = Field(default=None, max_length=40)
    single_character_id: str | None = Field(default=None, max_length=40)
    single_emotion: str | None = Field(default=None, max_length=80)
    single_text: str | None = Field(default=None, max_length=4_000)
    pack_character_id: str | None = Field(default=None, max_length=40)
    pack_lines: list[VoicePackLine] = Field(default_factory=list, max_length=24)


class InboxManifest(BaseModel):
    """A bounded production request uploaded to the private GCS inbox."""

    schema_version: Literal["1.0"] = "1.0"
    project_id: str = Field(min_length=1, max_length=80)
    target_language: Literal["zh", "en", "ja"]
    production_mode: Literal["draft", "production", "cinematic"] = "production"
    revision_limit: int = Field(default=2, ge=0, le=3)
    character_id: str | None = Field(default=None, max_length=40)


class JobEvent(BaseModel):
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent: str
    message: str
    status: Literal["running", "passed", "retry", "failed", "info"] = "running"


class JobRecord(BaseModel):
    id: str
    title: str
    project_id: str | None = None
    workflow_mode: Literal["single", "dialogue", "voice_pack"] | None = None
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    progress: int = 0
    stage: str = "Queued"
    demo_mode: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    events: list[JobEvent] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None


class MergeRetryCreate(BaseModel):
    replacement_job_id: str = Field(min_length=1, max_length=40)
