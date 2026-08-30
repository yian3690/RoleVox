import os
import json
import base64
from types import SimpleNamespace
import pytest

os.environ["DEMO_MODE"] = "true"

from fastapi.testclient import TestClient

from main import app
from app.pipeline import WorkflowEngine
import app.pipeline as pipeline_module


client = TestClient(app)


def test_health_and_voices():
    assert client.get("/api/health").json()["status"] == "ok"
    assert len(client.get("/api/voices").json()["voices"]) == 30


@pytest.mark.parametrize("target_language", ["zh", "en", "ja"])
def test_demo_job_completes_and_packages_assets(target_language):
    response = client.post("/api/jobs", json={
        "title": "Tri-Language Test",
        "scene": "Gate",
        "script": "璃央：不要回頭。\nMara: Keep moving.\nレン：任せて。",
        "target_language": target_language,
        "quality_threshold": 78,
        "max_retries": 1,
    })
    assert response.status_code == 202
    job_id = response.json()["id"]
    # TestClient completes BackgroundTasks before returning.
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "completed"
    assert len(job["result"]["lines"]) == 3
    assert job["result"]["target_language"] == target_language
    assert all(line["target_language"] == target_language for line in job["result"]["lines"])
    assert all("source_text" in line for line in job["result"]["lines"])
    package = client.get(job["result"]["package_url"])
    assert package.status_code == 200
    assert package.headers["content-type"] == "application/zip"


def test_character_image_and_brief_flow_into_casting_manifest():
    payload = {
        "title": "Reference Casting Test",
        "scene": "Ruins",
        "script": "Mara: We go now.",
        "target_language": "en",
        "character_descriptions": {"Mara": "A guarded knight who hides her fear behind calm precision."},
        "quality_threshold": 78,
        "max_retries": 0,
    }
    response = client.post(
        "/api/jobs/with-references",
        data={"payload": json.dumps(payload), "image_characters": json.dumps(["Mara"])},
        files=[("images", ("mara.png", b"\x89PNG\r\n\x1a\nrolevox-test", "image/png"))],
    )
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "completed"
    reference = job["result"]["character_references"][0]
    assert reference["character"] == "Mara"
    assert reference["has_image"] is True
    assert "guarded knight" in reference["description"]
    assert job["result"]["casting"][0]["visual_analysis"]


def test_rejects_unsupported_character_image_type():
    payload = {"title": "Bad Image", "scene": "One", "script": "Mara: Stop.",
               "target_language": "en", "character_descriptions": {}}
    response = client.post(
        "/api/jobs/with-references",
        data={"payload": json.dumps(payload), "image_characters": json.dumps(["Mara"])},
        files=[("images", ("mara.gif", b"GIF89a", "image/gif"))],
    )
    assert response.status_code == 415


def _tts_fixture_line():
    return {"id": 1, "text": "等等……門後面有東西在呼吸。", "target_language": "zh",
            "emotion": "wary", "intensity": 0.7, "pace": "slow"}


def _generate_content_audio_response(data):
    blob = SimpleNamespace(data=data, mime_type="audio/L16;rate=24000")
    part = SimpleNamespace(inline_data=blob)
    content = SimpleNamespace(parts=[part])
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


def test_tts_retries_recoverable_audio_completion_error(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("The audio stream could not be completed. Please retry your request.")
        audio = base64.b64encode(b"\x00\x00" * 120).decode()
        return _generate_content_audio_response(audio)

    monkeypatch.setattr(pipeline_module, "DEMO_MODE", False)
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _: None)
    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=create))
    cast = {"voice": "Kore", "profile": "A cautious fictional adventurer"}
    wav = WorkflowEngine()._tts(fake_client, _tts_fixture_line(), cast, {}, 0)

    assert wav.startswith(b"RIFF")
    assert len(calls) == 2
    assert "Original fictional character profile" not in calls[1]["contents"]
    assert cast["voice"] == "Kore"


def test_tts_switches_to_fallback_system_voice_after_two_failures(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            raise RuntimeError("The audio stream could not be completed. Please retry your request.")
        return _generate_content_audio_response(b"\x00\x00" * 120)

    monkeypatch.setattr(pipeline_module, "DEMO_MODE", False)
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _: None)
    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=create))
    cast = {"voice": "Kore", "profile": "A composed fictional attendant"}
    wav = WorkflowEngine()._tts(fake_client, _tts_fixture_line(), cast, {}, 0)

    assert wav.startswith(b"RIFF")
    assert len(calls) == 3
    assert cast["voice"] == "Iapetus"
    assert cast["tts_fallback"]["from_voice"] == "Kore"


def test_tts_never_switches_a_locked_voice(monkeypatch):
    voices = []

    def create(**kwargs):
        voices.append(kwargs["config"].speech_config.voice_config.prebuilt_voice_config.voice_name)
        if len(voices) < 3:
            raise RuntimeError("The audio stream could not be completed. Please retry your request.")
        return _generate_content_audio_response(b"\x00\x00" * 120)

    monkeypatch.setattr(pipeline_module, "DEMO_MODE", False)
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _: None)
    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=create))
    cast = {"voice": "Kore", "profile": "A locked fictional voice",
            "voice_locked": True, "voice_identity": {"locked": True}}
    wav = WorkflowEngine()._tts(fake_client, _tts_fixture_line(), cast, {}, 0)

    assert wav.startswith(b"RIFF")
    assert voices == ["Kore", "Kore", "Kore"]
    assert "tts_fallback" not in cast


def test_project_voice_lock_and_agentic_revision_flow():
    project_response = client.post("/api/projects", json={
        "title": "Original Worlds", "scene": "The Last Gate",
        "background": "An original veteran guardian hears an unseen creature beyond the gate.",
    })
    assert project_response.status_code == 201
    project = project_response.json()

    cast_response = client.post(
        f"/api/projects/{project['id']}/characters",
        data={"name": "Aren", "brief": "An original weathered guardian; restrained and authoritative."},
        files={"image": ("aren.png", b"\x89PNG\r\n\x1a\nrolevox-original", "image/png")},
    )
    assert cast_response.status_code == 201
    project = cast_response.json()
    character = project["characters"][0]
    assert character["voice_locked"] is False
    assert character["casting"]["perceived_archetype"]
    assert character["casting"]["confidence"] == 87
    assert character["casting"]["voice_identity"]["voice"]

    lock_response = client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/lock"
    )
    assert lock_response.status_code == 200
    locked = lock_response.json()["characters"][0]
    assert locked["voice_locked"] is True
    assert locked["casting"]["voice_identity"]["locked"] is True

    dialogue_response = client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/dialogues",
        json={"emotion": "fearful but restrained", "text": "Something is breathing beyond the gate."},
    )
    assert dialogue_response.status_code == 201

    production_response = client.post(
        f"/api/projects/{project['id']}/produce",
        json={"target_language": "en", "production_mode": "production", "revision_limit": 2},
    )
    assert production_response.status_code == 202
    job = client.get(f"/api/jobs/{production_response.json()['id']}").json()
    assert job["status"] == "completed"
    result = job["result"]
    assert result["production_mode"] == "production"
    assert result["production_target"] == 86
    assert result["casting"][0]["voice"] == locked["casting"]["voice"]
    assert result["casting"][0]["voice_identity"]["locked"] is True
    line = result["lines"][0]
    assert line["emotion"] == "fearful but restrained"
    assert len(line["takes"]) == 2
    assert line["takes"][0]["qa"]["score"] == 78
    assert line["takes"][0]["revision"]["speaking_rate"]["to"] == 0.87
    assert line["takes"][1]["qa"]["score"] == 93
    assert line["takes"][1]["approved"] is True
