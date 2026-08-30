from __future__ import annotations

import json
import os
import re
import threading
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

load_dotenv()

from app.models import (  # noqa: E402
    CharacterRecord, CharacterRecastCreate, CharacterUpdate, DialogueCreate, DialogueRecord, JobRecord, ProductionCreate,
    ProjectCreate, ProjectRecord, ProjectRequest, ProjectUpdate, VoicePreviewCreate,
    VoiceSelectionCreate,
)
from app.pipeline import (  # noqa: E402
    ARTIFACT_ROOT, CLOUD_LOCATION, DEMO_MODE, TEXT_MODEL, TTS_MODEL, VOICE_LIBRARY, engine,
)

app = FastAPI(title="RoleVox", version="0.2.0")
STATIC = Path(__file__).parent / "static"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
PROJECTS: dict[str, ProjectRecord] = {}
PROJECT_IMAGES: dict[tuple[str, str], dict] = {}
PROJECT_LOCK = threading.RLock()
PROJECT_ROOT = ARTIFACT_ROOT / "projects"
PRODUCTION_TARGETS = {"draft": 72, "production": 86, "cinematic": 92}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": engine.backend_name(),
            "configured": engine.is_configured(), "location": CLOUD_LOCATION,
            "text_model": TEXT_MODEL, "tts_model": TTS_MODEL,
            "gcs": bool(os.getenv("GCS_BUCKET"))}


@app.get("/api/voices")
def voices() -> dict:
    return {"voices": [{"name": key, "style": value} for key, value in VOICE_LIBRARY.items()]}


def _project_or_404(project_id: str) -> ProjectRecord:
    project = PROJECTS.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _character_or_404(project: ProjectRecord, character_id: str) -> CharacterRecord:
    character = next((item for item in project.characters if item.id == character_id), None)
    if not character:
        raise HTTPException(404, "Character not found")
    return character


def _touch(project: ProjectRecord) -> None:
    project.updated_at = datetime.now(timezone.utc).isoformat()


def _save_project(project: ProjectRecord) -> None:
    folder = PROJECT_ROOT / project.id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project.json").write_text(project.model_dump_json(indent=2), encoding="utf-8")


def _ensure_voice_candidates(character: CharacterRecord) -> None:
    casting = character.casting
    candidates = casting.get("voice_candidates")
    if isinstance(candidates, list) and len(candidates) >= 3:
        return
    current = casting.get("voice") if casting.get("voice") in VOICE_LIBRARY else next(iter(VOICE_LIBRARY))
    identity = casting.get("voice_identity") if isinstance(casting.get("voice_identity"), dict) else {}
    voices = [current] + [voice for voice in VOICE_LIBRARY if voice != current][:2]
    casting["voice_candidates"] = [{"voice": voice, "label": f"OPTION {index + 1}",
        "qualities": identity.get("qualities", VOICE_LIBRARY[voice].title()) if index == 0 else VOICE_LIBRARY[voice].title(),
        "pitch": identity.get("pitch", casting.get("suggested_register", "Medium")),
        "texture": identity.get("texture", casting.get("voice_texture", VOICE_LIBRARY[voice])),
        "speaking_style": identity.get("speaking_style", casting.get("delivery_style", "Measured")),
        "accent": identity.get("accent", "Neutral"),
        "profile": casting.get("profile", f"original {VOICE_LIBRARY[voice]} fictional voice") if index == 0 else f"original {VOICE_LIBRARY[voice]} fictional voice",
        "rationale": "Existing voice identity" if index == 0 else "Additional synthetic audition option"}
        for index, voice in enumerate(voices)]
    casting.setdefault("selected_voice", current)


def _load_projects() -> None:
    if not PROJECT_ROOT.exists():
        return
    for path in PROJECT_ROOT.glob("*/project.json"):
        try:
            project = ProjectRecord.model_validate_json(path.read_text(encoding="utf-8"))
            PROJECTS[project.id] = project
            for character in project.characters:
                _ensure_voice_candidates(character)
                image_path = path.parent / "characters" / character.image_storage_name
                if image_path.is_file():
                    PROJECT_IMAGES[(project.id, character.id)] = {
                        "data": image_path.read_bytes(), "mime_type": character.image_mime_type,
                        "filename": character.image_filename,
                    }
        except (OSError, ValueError):
            continue


_load_projects()


@app.post("/api/projects", response_model=ProjectRecord, status_code=201)
def create_project(payload: ProjectCreate) -> ProjectRecord:
    project = ProjectRecord(id=uuid.uuid4().hex[:12], **payload.model_dump())
    with PROJECT_LOCK:
        PROJECTS[project.id] = project
        _save_project(project)
    return project


@app.get("/api/projects", response_model=list[ProjectRecord])
def list_projects() -> list[ProjectRecord]:
    return sorted(PROJECTS.values(), key=lambda item: item.updated_at, reverse=True)


@app.get("/api/projects/{project_id}", response_model=ProjectRecord)
def get_project(project_id: str) -> ProjectRecord:
    return _project_or_404(project_id)


@app.patch("/api/projects/{project_id}", response_model=ProjectRecord)
def update_project(project_id: str, payload: ProjectUpdate) -> ProjectRecord:
    project = _project_or_404(project_id)
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "Provide at least one project field to update.")
    cleaned = {key: value.strip() for key, value in changes.items()}
    if any(not value for value in cleaned.values()):
        raise HTTPException(422, "Project fields cannot be blank.")
    with PROJECT_LOCK:
        for key, value in cleaned.items():
            setattr(project, key, value)
        _touch(project)
        _save_project(project)
    return project


@app.patch("/api/projects/{project_id}/characters/{character_id}", response_model=ProjectRecord)
def update_character(project_id: str, character_id: str,
                     payload: CharacterUpdate) -> ProjectRecord:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    name = payload.name.strip()
    brief = payload.brief.strip()
    if not name or not brief:
        raise HTTPException(422, "Character name and brief cannot be blank.")
    if any(item.id != character.id and item.name.casefold() == name.casefold()
           for item in project.characters):
        raise HTTPException(409, f"Character {name} already exists in this project.")
    with PROJECT_LOCK:
        character.name = name
        character.brief = brief
        character.casting["character"] = name
        _touch(project)
        _save_project(project)
    return project


@app.delete("/api/projects/{project_id}/characters/{character_id}", response_model=ProjectRecord)
def delete_character(project_id: str, character_id: str) -> ProjectRecord:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    image_root = (PROJECT_ROOT / project.id / "characters").resolve()
    image_path = (image_root / character.image_storage_name).resolve()
    if image_path.parent != image_root:
        raise HTTPException(400, "Invalid character image path")
    trash_root = (PROJECT_ROOT.parent / "project-trash" / "characters").resolve()
    destination = trash_root / (
        f"{project.id}_{character.id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    with PROJECT_LOCK:
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "character.json").write_text(
            character.model_dump_json(indent=2), encoding="utf-8"
        )
        if image_path.is_file():
            shutil.move(str(image_path), str(destination / image_path.name))
        project.characters = [item for item in project.characters if item.id != character.id]
        for remaining in project.characters:
            for dialogue in remaining.dialogues:
                if dialogue.addressee_id == character.id:
                    dialogue.addressee_id = None
        PROJECT_IMAGES.pop((project.id, character.id), None)
        _touch(project)
        _save_project(project)
    return project


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str) -> Response:
    project = _project_or_404(project_id)
    source = (PROJECT_ROOT / project.id).resolve()
    root = PROJECT_ROOT.resolve()
    trash_root = (PROJECT_ROOT.parent / "project-trash").resolve()
    if source.parent != root:
        raise HTTPException(400, "Invalid project storage path")
    with PROJECT_LOCK:
        if source.exists():
            trash_root.mkdir(parents=True, exist_ok=True)
            destination = trash_root / f"{project.id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            shutil.move(str(source), str(destination))
        PROJECTS.pop(project.id, None)
        for key in [key for key in PROJECT_IMAGES if key[0] == project.id]:
            PROJECT_IMAGES.pop(key, None)
    return Response(status_code=204)


@app.get("/api/projects/{project_id}/characters/{character_id}/image")
def get_character_image(project_id: str, character_id: str) -> Response:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    reference = PROJECT_IMAGES.get((project.id, character.id))
    if not reference:
        raise HTTPException(404, "Character image not found")
    return Response(content=reference["data"], media_type=reference["mime_type"])


@app.post("/api/projects/{project_id}/characters", response_model=ProjectRecord, status_code=201)
async def add_character(
    project_id: str,
    name: str = Form(...),
    brief: str = Form(...),
    voice_presentation: str = Form("auto"),
    image: UploadFile = File(...),
) -> ProjectRecord:
    if not engine.is_configured():
        raise HTTPException(503, "Vertex AI is not configured.")
    project = _project_or_404(project_id)
    name = name.strip()
    brief = brief.strip()
    if not name or len(name) > 80 or not brief or len(brief) > 1_000:
        raise HTTPException(422, "Character name and brief are required and must fit the field limits.")
    if voice_presentation not in {"auto", "feminine", "masculine", "neutral"}:
        raise HTTPException(422, "Voice presentation must be auto, feminine, masculine, or neutral.")
    if len(project.characters) >= 10:
        raise HTTPException(422, "A maximum of 10 characters is supported per project.")
    if any(item.name.casefold() == name.casefold() for item in project.characters):
        raise HTTPException(409, f"Character {name} already exists in this project.")
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, "Character images must be PNG, JPEG, or WebP.")
    data = await image.read(MAX_IMAGE_BYTES + 1)
    await image.close()
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Character image must be between 1 byte and 5 MB.")
    reference = {"data": data, "mime_type": image.content_type,
                 "filename": image.filename or "character-reference"}
    casting = await run_in_threadpool(
        engine.cast_character, project.title, project.scene, project.background,
        name, brief, reference, voice_presentation,
    )
    _ensure_voice_candidates(CharacterRecord(id="preview", name=name, brief=brief,
        image_filename=reference["filename"], image_mime_type=image.content_type,
        image_storage_name="preview", casting=casting, voice_presentation=voice_presentation))
    character_id = uuid.uuid4().hex[:10]
    extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[image.content_type]
    storage_name = f"{character_id}{extension}"
    character = CharacterRecord(id=character_id, name=name, brief=brief,
                                image_filename=reference["filename"], image_mime_type=image.content_type,
                                image_storage_name=storage_name, casting=casting,
                                voice_presentation=voice_presentation)
    with PROJECT_LOCK:
        project.characters.append(character)
        PROJECT_IMAGES[(project.id, character.id)] = reference
        image_folder = PROJECT_ROOT / project.id / "characters"
        image_folder.mkdir(parents=True, exist_ok=True)
        (image_folder / storage_name).write_bytes(data)
        _touch(project)
        _save_project(project)
    return project


@app.post("/api/projects/{project_id}/characters/{character_id}/recast", response_model=ProjectRecord)
async def recast_character_voice(project_id: str, character_id: str,
                                 payload: CharacterRecastCreate) -> ProjectRecord:
    if not engine.is_configured():
        raise HTTPException(503, "Vertex AI is not configured.")
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    if character.voice_locked:
        raise HTTPException(409, "Unlock this Voice Identity before generating new audition voices.")
    reference = PROJECT_IMAGES.get((project.id, character.id))
    if not reference:
        raise HTTPException(404, "Character image not found")
    casting = await run_in_threadpool(
        engine.cast_character, project.title, project.scene, project.background,
        character.name, character.brief, reference, payload.voice_presentation,
    )
    with PROJECT_LOCK:
        character.voice_presentation = payload.voice_presentation
        character.casting = casting
        character.voice_locked = False
        _touch(project)
        _save_project(project)
    return project


@app.post("/api/projects/{project_id}/characters/{character_id}/lock", response_model=ProjectRecord)
def lock_character_voice(project_id: str, character_id: str) -> ProjectRecord:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    if not character.casting.get("selected_voice"):
        raise HTTPException(422, "Select one audition voice before locking this character.")
    with PROJECT_LOCK:
        character.voice_locked = True
        character.casting["voice_locked"] = True
        character.casting.setdefault("voice_identity", {})["locked"] = True
        _touch(project)
        _save_project(project)
    return project


@app.post("/api/projects/{project_id}/characters/{character_id}/select-voice", response_model=ProjectRecord)
def select_character_voice(project_id: str, character_id: str,
                           payload: VoiceSelectionCreate) -> ProjectRecord:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    if character.voice_locked:
        raise HTTPException(409, "Unlock this Voice Identity before changing the audition selection.")
    candidate = next((item for item in character.casting.get("voice_candidates", [])
                      if item.get("voice") == payload.voice), None)
    if not candidate:
        raise HTTPException(422, "Select one of this character's three audition voices.")
    with PROJECT_LOCK:
        character.casting["selected_voice"] = candidate["voice"]
        character.casting["voice"] = candidate["voice"]
        character.casting["profile"] = candidate.get("profile", character.casting.get("profile", ""))
        character.casting["voice_identity"] = {key: candidate.get(key, "") for key in
            ("voice", "qualities", "pitch", "texture", "speaking_style", "accent")}
        character.casting["voice_identity"]["locked"] = False
        _touch(project)
        _save_project(project)
    return project


@app.post("/api/projects/{project_id}/characters/{character_id}/voice-preview")
def preview_character_voice(project_id: str, character_id: str,
                            payload: VoicePreviewCreate) -> Response:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    candidate = next((item for item in character.casting.get("voice_candidates", [])
                      if item.get("voice") == payload.voice), None)
    if not candidate:
        raise HTTPException(422, "Unknown audition voice.")
    try:
        wav = engine.preview_voice(character.name, candidate, payload.language)
    except Exception as exc:
        raise HTTPException(502, f"Voice audition could not be generated: {exc}") from exc
    return Response(content=wav, media_type="audio/wav",
                    headers={"Content-Disposition": f'inline; filename="{character.id}_{payload.voice}.wav"'})


@app.post("/api/projects/{project_id}/characters/{character_id}/unlock", response_model=ProjectRecord)
def unlock_character_voice(project_id: str, character_id: str) -> ProjectRecord:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    with PROJECT_LOCK:
        character.voice_locked = False
        character.casting["voice_locked"] = False
        character.casting.setdefault("voice_identity", {})["locked"] = False
        _touch(project)
        _save_project(project)
    return project


@app.post("/api/projects/{project_id}/characters/{character_id}/dialogues",
          response_model=ProjectRecord, status_code=201)
def add_dialogue(project_id: str, character_id: str, payload: DialogueCreate) -> ProjectRecord:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    if payload.addressee_id:
        _character_or_404(project, payload.addressee_id)
        if payload.addressee_id == character.id:
            raise HTTPException(422, "Choose another character as addressee, or let AI infer it.")
    with PROJECT_LOCK:
        next_order = max((line.order for item in project.characters for line in item.dialogues), default=0) + 1
        character.dialogues.append(DialogueRecord(id=uuid.uuid4().hex[:10], order=next_order,
                                                   **payload.model_dump()))
        _touch(project)
        _save_project(project)
    return project


@app.patch("/api/projects/{project_id}/characters/{character_id}/dialogues/{dialogue_id}",
           response_model=ProjectRecord)
def update_dialogue(project_id: str, character_id: str, dialogue_id: str,
                    payload: DialogueCreate) -> ProjectRecord:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    dialogue = next((item for item in character.dialogues if item.id == dialogue_id), None)
    if not dialogue:
        raise HTTPException(404, "Dialogue not found")
    if payload.addressee_id:
        _character_or_404(project, payload.addressee_id)
        if payload.addressee_id == character.id:
            raise HTTPException(422, "Choose another character as addressee, or let AI infer it.")
    with PROJECT_LOCK:
        dialogue.emotion = payload.emotion
        dialogue.text = payload.text
        dialogue.addressee_id = payload.addressee_id
        _touch(project)
        _save_project(project)
    return project


@app.delete("/api/projects/{project_id}/characters/{character_id}/dialogues/{dialogue_id}",
            response_model=ProjectRecord)
def delete_dialogue(project_id: str, character_id: str, dialogue_id: str) -> ProjectRecord:
    project = _project_or_404(project_id)
    character = _character_or_404(project, character_id)
    with PROJECT_LOCK:
        before = len(character.dialogues)
        character.dialogues = [item for item in character.dialogues if item.id != dialogue_id]
        if len(character.dialogues) == before:
            raise HTTPException(404, "Dialogue not found")
        _touch(project)
        _save_project(project)
    return project


@app.post("/api/projects/{project_id}/produce", response_model=JobRecord, status_code=202)
def produce_project(project_id: str, payload: ProductionCreate,
                    tasks: BackgroundTasks) -> JobRecord:
    if not engine.is_configured():
        raise HTTPException(503, "Vertex AI is not configured.")
    project = _project_or_404(project_id)
    if not project.characters:
        raise HTTPException(422, "Add at least one character before production.")
    if payload.workflow_mode == "single":
        single_character_id = payload.single_character_id or payload.character_id
        selected_characters = [item for item in project.characters if item.id == single_character_id]
        if not selected_characters:
            raise HTTPException(404, "Select a character for single-character generation.")
        single_text = (payload.single_text or "").strip()
        single_emotion = (payload.single_emotion or "").strip()
        if not single_text or not single_emotion:
            raise HTTPException(422, "Single-character generation requires emotion and dialogue text.")
    else:
        selected_characters = [item for item in project.characters if item.dialogues]
        if payload.character_id:  # Backward-compatible single-speaker script production.
            selected_characters = [item for item in selected_characters if item.id == payload.character_id]
        if not selected_characters:
            raise HTTPException(422, "Add at least one project dialogue line before dialogue production.")
    unlocked = [item.name for item in selected_characters if not item.voice_locked]
    if unlocked:
        raise HTTPException(422, f"Lock every voice before production: {', '.join(unlocked)}")
    script_lines: list[str] = []
    line_emotions: dict[int, str] = {}
    line_addressees: dict[int, str] = {}
    line_id = 0
    if payload.workflow_mode == "single":
        character = selected_characters[0]
        script_lines.append(f"{character.name}: {single_text}")
        line_emotions[1] = single_emotion
    else:
        selected_ids = {item.id for item in selected_characters}
        character_names = {item.id: item.name for item in project.characters}
        dialogue_rows = [(character, dialogue, stable_index)
                         for stable_index, (character, dialogue) in enumerate(
                             (pair for item in project.characters for pair in
                              ((item, dialogue) for dialogue in item.dialogues)))
                         if character.id in selected_ids]
        dialogue_rows.sort(key=lambda row: (row[1].order if row[1].order > 0 else 1_000_000 + row[2]))
        for character, dialogue, _ in dialogue_rows:
            line_id += 1
            script_lines.append(f"{character.name}: {dialogue.text}")
            line_emotions[line_id] = dialogue.emotion
            if dialogue.addressee_id and dialogue.addressee_id in character_names:
                line_addressees[line_id] = character_names[dialogue.addressee_id]
    request = ProjectRequest(
        title=project.title, scene=project.scene, background=project.background,
        target_language=payload.target_language, script="\n".join(script_lines),
        character_descriptions={item.name: item.brief for item in selected_characters},
        quality_threshold=PRODUCTION_TARGETS[payload.production_mode],
        max_retries=payload.revision_limit, production_mode=payload.production_mode,
        workflow_mode=payload.workflow_mode,
        line_emotions=line_emotions, line_addressees=line_addressees,
        locked_casting=[item.casting for item in selected_characters],
    )
    character_images = {
        item.name: PROJECT_IMAGES[(project.id, item.id)]
        for item in selected_characters if (project.id, item.id) in PROJECT_IMAGES
    }
    job = engine.create(uuid.uuid4().hex[:12], request)
    tasks.add_task(engine.run, job, request, character_images)
    return job


@app.post("/api/jobs", response_model=JobRecord, status_code=202)
def create_job(payload: ProjectRequest, tasks: BackgroundTasks) -> JobRecord:
    if not engine.is_configured():
        raise HTTPException(503, "Configure Vertex AI/ADC or GEMINI_API_KEY, or explicitly enable DEMO_MODE=true.")
    job = engine.create(uuid.uuid4().hex[:12], payload)
    tasks.add_task(engine.run, job, payload)
    return job


def _script_characters(script: str) -> list[str]:
    names: list[str] = []
    for raw in script.splitlines():
        parts = re.split(r"[:：]", raw.strip(), maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[0].strip() not in names:
            names.append(parts[0].strip())
    return names


@app.post("/api/jobs/with-references", response_model=JobRecord, status_code=202)
async def create_job_with_references(
    tasks: BackgroundTasks,
    payload: str = Form(...),
    image_characters: str = Form("[]"),
    images: list[UploadFile] = File(default=[]),
) -> JobRecord:
    if not engine.is_configured():
        raise HTTPException(503, "Configure Vertex AI/ADC or GEMINI_API_KEY, or explicitly enable DEMO_MODE=true.")
    try:
        request = ProjectRequest.model_validate_json(payload)
        mapped_characters = json.loads(image_characters)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"Invalid production payload: {exc}") from exc
    if not isinstance(mapped_characters, list) or len(mapped_characters) != len(images):
        raise HTTPException(422, "Each uploaded image must map to exactly one character.")
    script_characters = _script_characters(request.script)
    if len(script_characters) > 10:
        raise HTTPException(422, "A maximum of 10 characters is supported per production.")
    unknown = (set(request.character_descriptions) | set(mapped_characters)) - set(script_characters)
    if unknown:
        raise HTTPException(422, f"References do not match script characters: {', '.join(sorted(unknown))}")

    character_images: dict[str, dict] = {}
    for character, upload in zip(mapped_characters, images):
        if character in character_images:
            raise HTTPException(422, f"Only one image is allowed for {character}.")
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(415, "Character images must be PNG, JPEG, or WebP.")
        data = await upload.read(MAX_IMAGE_BYTES + 1)
        await upload.close()
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Each character image must be between 1 byte and 5 MB.")
        character_images[character] = {
            "data": data,
            "mime_type": upload.content_type,
            "filename": upload.filename or "character-reference",
        }

    job = engine.create(uuid.uuid4().hex[:12], request)
    tasks.add_task(engine.run, job, request, character_images)
    return job


@app.get("/api/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: str) -> JobRecord:
    job = engine.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


def _safe_file(job_id: str, filename: str) -> Path:
    job_dir = (ARTIFACT_ROOT / job_id).resolve()
    path = (job_dir / filename).resolve()
    if path.parent != job_dir or not path.is_file():
        raise HTTPException(404, "File not found")
    return path


@app.get("/api/jobs/{job_id}/files/{filename}")
def get_audio(job_id: str, filename: str) -> FileResponse:
    return FileResponse(_safe_file(job_id, filename), media_type="audio/wav", filename=filename)


@app.get("/api/jobs/{job_id}/package")
def get_package(job_id: str) -> FileResponse:
    job = engine.get(job_id)
    if not job or job.status != "completed" or not job.result:
        raise HTTPException(404, "Completed package not found")
    path = _safe_file(job_id, job.result["package_name"])
    return FileResponse(path, media_type="application/zip", filename=path.name)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
