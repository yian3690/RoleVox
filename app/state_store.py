from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, timezone
from typing import Any

from google.api_core.exceptions import AlreadyExists

from .models import JobRecord, ProjectRecord


_CLIENT = None
_CLIENT_LOCK = threading.Lock()


def enabled() -> bool:
    return os.getenv("FIRESTORE_ENABLED", "false").lower() in {"1", "true", "yes"}


def _firestore():
    global _CLIENT
    if not enabled():
        return None
    with _CLIENT_LOCK:
        if _CLIENT is None:
            from google.cloud import firestore

            _CLIENT = firestore.Client(
                project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
                database=os.getenv("FIRESTORE_DATABASE", "(default)"),
            )
    return _CLIENT


def save_project(project: ProjectRecord) -> None:
    client = _firestore()
    if client is None:
        return
    payload = project.model_dump(mode="json")
    payload["_archived"] = False
    client.collection("projects").document(project.id).set(payload)


def get_project(project_id: str) -> ProjectRecord | None:
    client = _firestore()
    if client is None:
        return None
    snapshot = client.collection("projects").document(project_id).get()
    if not snapshot.exists:
        return None
    payload = snapshot.to_dict() or {}
    if payload.pop("_archived", False):
        return None
    return ProjectRecord.model_validate(payload)


def load_projects() -> list[ProjectRecord]:
    client = _firestore()
    if client is None:
        return []
    projects: list[ProjectRecord] = []
    for snapshot in client.collection("projects").stream():
        payload = snapshot.to_dict() or {}
        if payload.pop("_archived", False):
            continue
        projects.append(ProjectRecord.model_validate(payload))
    return projects


def archive_project(project_id: str) -> None:
    client = _firestore()
    if client is None:
        return
    client.collection("projects").document(project_id).set(
        {
            "_archived": True,
            "_archived_at": datetime.now(timezone.utc).isoformat(),
        },
        merge=True,
    )


def save_job(job: JobRecord) -> None:
    client = _firestore()
    if client is None:
        return
    client.collection("jobs").document(job.id).set(job.model_dump(mode="json"))


def get_job(job_id: str) -> JobRecord | None:
    client = _firestore()
    if client is None:
        return None
    snapshot = client.collection("jobs").document(job_id).get()
    return JobRecord.model_validate(snapshot.to_dict()) if snapshot.exists else None


def _bucket():
    bucket_name = os.getenv("GCS_BUCKET", "").strip()
    if not enabled() or not bucket_name:
        return None
    from google.cloud import storage

    return storage.Client().bucket(bucket_name)


def save_character_image(project_id: str, character_id: str, storage_name: str,
                         data: bytes, mime_type: str) -> None:
    bucket = _bucket()
    if bucket is None:
        return
    bucket.blob(
        f"projects/{project_id}/characters/{storage_name}",
    ).upload_from_string(data, content_type=mime_type)


def load_character_image(project_id: str, storage_name: str) -> bytes | None:
    bucket = _bucket()
    if bucket is None:
        return None
    blob = bucket.blob(f"projects/{project_id}/characters/{storage_name}")
    return blob.download_as_bytes() if blob.exists() else None


def load_artifact(job_id: str, filename: str) -> bytes | None:
    bucket = _bucket()
    if bucket is None:
        return None
    blob = bucket.blob(f"rolevox/{job_id}/{filename}")
    return blob.download_as_bytes() if blob.exists() else None


def claim_inbox_event(event_key: str, job_id: str) -> tuple[bool, str | None]:
    """Atomically claim one immutable GCS object generation."""

    client = _firestore()
    if client is None:
        return True, None
    document_id = hashlib.sha256(event_key.encode("utf-8")).hexdigest()
    reference = client.collection("inbox_events").document(document_id)
    try:
        reference.create({
            "event_key": event_key,
            "job_id": job_id,
            "status": "processing",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return True, job_id
    except AlreadyExists:
        snapshot = reference.get()
        payload: dict[str, Any] = snapshot.to_dict() or {}
        return False, payload.get("job_id")


def complete_inbox_event(event_key: str, job_id: str) -> None:
    client = _firestore()
    if client is None:
        return
    document_id = hashlib.sha256(event_key.encode("utf-8")).hexdigest()
    client.collection("inbox_events").document(document_id).set({
        "job_id": job_id,
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }, merge=True)


def release_inbox_event(event_key: str) -> None:
    client = _firestore()
    if client is None:
        return
    document_id = hashlib.sha256(event_key.encode("utf-8")).hexdigest()
    client.collection("inbox_events").document(document_id).delete()
