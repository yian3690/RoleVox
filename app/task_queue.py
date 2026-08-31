from __future__ import annotations

import json
import os

from google.api_core.exceptions import AlreadyExists

from .models import ProjectRequest


def enabled() -> bool:
    return bool(os.getenv("CLOUD_TASKS_QUEUE", "").strip())


def enqueue(job_id: str, request: ProjectRequest, project_id: str | None = None) -> str:
    """Queue one authenticated, deterministic production worker request."""

    from google.cloud import tasks_v2

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.getenv("CLOUD_TASKS_LOCATION", "asia-east1")
    queue = os.environ["CLOUD_TASKS_QUEUE"]
    service_account = os.environ["CLOUD_TASKS_SERVICE_ACCOUNT"]
    audience = os.environ["ROLEVOX_EVENT_AUDIENCE"].rstrip("/")
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project, location, queue)
    task_name = client.task_path(project, location, queue, f"job-{job_id}")
    body = json.dumps({
        "request": request.model_dump(mode="json"),
        "project_id": project_id,
    }, ensure_ascii=False).encode("utf-8")
    task = {
        "name": task_name,
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{audience}/api/jobs/{job_id}/execute",
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "oidc_token": {
                "service_account_email": service_account,
                "audience": audience,
            },
        },
    }
    try:
        created = client.create_task(parent=parent, task=task)
        return created.name
    except AlreadyExists:
        return task_name
