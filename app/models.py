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
    line_emotions: dict[int, str] = Field(default_factory=dict)
    locked_casting: list[dict[str, Any]] = Field(default_factory=list)

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


class DialogueCreate(BaseModel):
    emotion: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4_000)


class DialogueRecord(BaseModel):
    id: str
    emotion: str
    text: str


class CharacterRecord(BaseModel):
    id: str
    name: str
    brief: str
    image_filename: str
    image_mime_type: str
    image_storage_name: str
    casting: dict[str, Any]
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
    revision_limit: int = Field(default=2, ge=0, le=3)


class JobEvent(BaseModel):
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent: str
    message: str
    status: Literal["running", "passed", "retry", "failed", "info"] = "running"


class JobRecord(BaseModel):
    id: str
    title: str
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    progress: int = 0
    stage: str = "Queued"
    demo_mode: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    events: list[JobEvent] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
