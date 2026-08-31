import os
import io
import json
import base64
import zipfile
from types import SimpleNamespace
import pytest

os.environ["DEMO_MODE"] = "true"

from fastapi.testclient import TestClient

from main import app
import main as main_module
from app.models import InboxManifest, JobRecord, ProjectRequest
from app.pipeline import FEMININE_VOICES, MASCULINE_VOICES, WorkflowEngine
import app.pipeline as pipeline_module
import app.adk_agent as adk_agent_module


client = TestClient(app)


@pytest.fixture
def isolated_project_store(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "PROJECTS", {})
    monkeypatch.setattr(main_module, "PROJECT_IMAGES", {})
    monkeypatch.setattr(main_module, "PROJECT_ROOT", tmp_path / "projects")
    monkeypatch.setattr(main_module, "INBOX_EVENT_JOBS", {})


def test_inbox_rejects_missing_oidc_token(monkeypatch):
    monkeypatch.setenv("EVENTARC_SERVICE_ACCOUNT", "rolevox-eventarc@example.iam.gserviceaccount.com")
    monkeypatch.setenv("ROLEVOX_EVENT_AUDIENCE", "https://rolevox.example")
    response = client.post("/api/inbox/events", json={"data": {
        "bucket": "rolevox-test-bucket", "name": "inbox/scene.json", "generation": "1",
    }})
    assert response.status_code == 401


def test_inbox_accepts_only_explicit_cloud_run_audiences(monkeypatch):
    account = "rolevox-eventarc@example.iam.gserviceaccount.com"
    canonical = "https://rolevox-canonical.a.run.app"
    public = "https://rolevox-project.asia-east1.run.app"
    monkeypatch.setenv("EVENTARC_SERVICE_ACCOUNT", account)
    monkeypatch.setenv("ROLEVOX_EVENT_AUDIENCE", canonical)
    monkeypatch.setenv("ROLEVOX_PUBLIC_URL", public)
    captured = {}

    def verify(token, request, audience):
        captured["audience"] = audience
        return {"email": account, "email_verified": True}

    monkeypatch.setattr(main_module.id_token, "verify_oauth2_token", verify)
    main_module._verify_inbox_caller("Bearer signed-token")
    assert set(captured["audience"]) == {
        canonical, f"{canonical}/api/inbox/events",
        public, f"{public}/api/inbox/events",
    }


def test_generation_cards_and_transient_poll_retry_are_present():
    html = main_module.STATIC.joinpath("index.html").read_text(encoding="utf-8")
    css = main_module.STATIC.joinpath("receipt.css").read_text(encoding="utf-8")
    script = main_module.STATIC.joinpath("app.js").read_text(encoding="utf-8")
    assert 'class="mode-picker generation-mode-picker"' in html
    assert ".generation-mode-picker" in css
    assert "[429, 503].includes(err.status)" in script
    assert "Production worker is busy. Retrying automatically" in script
    assert 'value="voice_pack"' in html
    assert 'id="voiceEventCatalog"' in html
    assert "/api/projects/${project.id}/voice-pack/draft" in script
    assert "pack_lines: workflowMode === 'voice_pack'" in script
    assert "checkbox.checked = true" in script
    assert "BEST AVAILABLE · NEEDS REVIEW" in script
    assert "retry-result-line" in script


def test_character_workspace_readability_and_control_spacing_are_present():
    css = main_module.STATIC.joinpath("typography-scale.css").read_text(encoding="utf-8")
    assert "#characterDialog .dialog-header{padding-right:58px}" in css
    assert "#characterDialog .character-heading p{white-space:pre-line" in css
    assert "#characterDialog .audition-heading>.block-label{font-size:11px" in css
    assert "#characterDialog .voice-candidate p{font-size:13px" in css
    assert "#characterDialog .reasoning-callout strong{display:block;font-size:20px" in css
    assert "#characterDialog .dialog-columns>section:first-child .detail-list dd{font-size:14px" in css
    assert ".generation-mode-picker small{font-size:12px" in css
    assert "max-width:none;font-size:11px" in css
    assert "voice-pack-character{display:grid;grid-template-columns:max-content 250px" in css
    assert "voice-event-option select{box-sizing:border-box;width:92px" in css
    assert "textarea.pack-text{box-sizing:border-box;width:100%;height:68px" in css
    assert ".revision-grid div{display:grid;grid-template-columns:90px minmax(0,1fr)" in css
    assert ".take blockquote{box-sizing:border-box;height:132px" in css
    assert ".voice-pack-approved{padding:14px 15px;font-size:11px" in css
    receipt_css = main_module.STATIC.joinpath("receipt.css").read_text(encoding="utf-8")
    assert "font: 600 22px DM Mono" in receipt_css
    assert ".run-receipt dd { font: 600 12px DM Mono" in receipt_css
    assert "font: 400 11px/1.7 DM Mono" in receipt_css


def test_inbox_ignores_output_objects(monkeypatch):
    monkeypatch.setattr(main_module, "_verify_inbox_caller", lambda *_: {"email_verified": True})
    monkeypatch.setenv("GCS_BUCKET", "rolevox-test-bucket")
    response = client.post("/api/inbox/events", json={"data": {
        "bucket": "rolevox-test-bucket", "name": "rolevox/job/output.zip", "generation": "1",
    }})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_inbox_runs_once_per_storage_generation(monkeypatch):
    monkeypatch.setattr(main_module, "_verify_inbox_caller", lambda *_: {"email_verified": True})
    monkeypatch.setenv("GCS_BUCKET", "rolevox-test-bucket")
    manifest = InboxManifest(project_id="project-1", target_language="ja")
    monkeypatch.setattr(main_module, "_load_inbox_manifest", lambda *_: manifest)
    request = ProjectRequest(
        title="Inbox Test", scene="Gate", target_language="ja", script="Ari: Ready.",
    )
    job = JobRecord(id="inboxjob001", title=request.title, demo_mode=True)
    monkeypatch.setattr(
        main_module, "_prepare_project_production", lambda *_, **__: (job, request, {}),
    )

    def fake_run(target_job, *_):
        target_job.status = "completed"
        target_job.progress = 100
        target_job.stage = "Ready"
        target_job.result = {"cloud_url": "gs://rolevox-test-bucket/rolevox/inboxjob001/package.zip"}

    monkeypatch.setattr(main_module.engine, "run", fake_run)
    monkeypatch.setattr(main_module.engine, "get", lambda job_id: job if job_id == job.id else None)
    event = {"data": {"bucket": "rolevox-test-bucket", "name": "inbox/scene.json", "generation": "7"}}
    first = client.post("/api/inbox/events", json=event)
    second = client.post("/api/inbox/events", json=event)

    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert second.json() == {
        "status": "duplicate", "job_id": job.id,
        "cloud_url": "gs://rolevox-test-bucket/rolevox/inboxjob001/package.zip",
    }


def test_health_and_voices():
    assert client.get("/api/health").json()["status"] == "ok"
    assert len(client.get("/api/voices").json()["voices"]) == 30


def test_production_director_uses_real_adk_boundary(monkeypatch):
    monkeypatch.setattr(pipeline_module, "DEMO_MODE", False)
    monkeypatch.setattr(pipeline_module, "USE_ADK_ORCHESTRATION", True)
    monkeypatch.setattr(
        adk_agent_module,
        "run_director",
        lambda prompt: ({"genre": "fantasy", "setting": "gate"}, ["ProductionDirectorAgent"]),
    )
    request = ProjectRequest(
        title="ADK Test", scene="Gate", target_language="en", script="Ari: Ready.",
    )
    direction = WorkflowEngine()._director(
        None, request, [{"id": 1, "character": "Ari", "text": "Ready."}],
    )
    assert direction["_orchestrator"] == "google-adk"
    assert direction["_adk_trace"] == ["ProductionDirectorAgent"]


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
    receipt = job["result"]["run_receipt"]
    assert receipt["receipt_type"] == "RoleVox Autonomous Run Receipt"
    assert receipt["origin"] == "api"
    assert receipt["voice_policy"]["synthetic_system_voices_only"] is True
    assert len(receipt["lines"][0]["sha256"]) == 64
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert "manifest.json" in archive.namelist()
        assert "run_receipt.json" in archive.namelist()


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


def test_tts_retries_when_candidate_content_has_no_parts(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=None))])
        return _generate_content_audio_response(b"\x00\x00" * 120)

    monkeypatch.setattr(pipeline_module, "DEMO_MODE", False)
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _: None)
    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=create))
    cast = {"voice": "Kore", "profile": "An original fictional guardian", "voice_locked": True}
    wav = WorkflowEngine()._tts(fake_client, _tts_fixture_line(), cast, {}, 0)

    assert wav.startswith(b"RIFF")
    assert len(calls) == 2


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


def test_project_voice_lock_and_agentic_revision_flow(isolated_project_store):
    project_response = client.post("/api/projects", json={
        "title": "Original Worlds", "scene": "The Last Gate",
        "background": "An original veteran guardian hears an unseen creature beyond the gate.",
    })
    assert project_response.status_code == 201
    project = project_response.json()
    assert any(item["id"] == project["id"] for item in client.get("/api/projects").json())

    cast_response = client.post(
        f"/api/projects/{project['id']}/characters",
        data={"name": "Aren", "brief": "An original weathered female guardian; restrained and authoritative.",
              "voice_presentation": "feminine"},
        files={"image": ("aren.png", b"\x89PNG\r\n\x1a\nrolevox-original", "image/png")},
    )
    assert cast_response.status_code == 201
    project = cast_response.json()
    character = project["characters"][0]
    assert character["voice_locked"] is False
    assert character["casting"]["perceived_archetype"]
    assert character["casting"]["confidence"] == 87
    assert character["casting"]["voice_identity"]["voice"]
    assert len(character["casting"]["voice_candidates"]) == 3
    assert len({item["voice"] for item in character["casting"]["voice_candidates"]}) == 3
    assert all(item["voice"] in FEMININE_VOICES for item in character["casting"]["voice_candidates"])
    assert character["voice_presentation"] == "feminine"
    assert character["casting"]["selected_voice"] is None
    image_response = client.get(
        f"/api/projects/{project['id']}/characters/{character['id']}/image"
    )
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"

    lock_response = client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/lock"
    )
    assert lock_response.status_code == 422
    candidate_voice = character["casting"]["voice_candidates"][1]["voice"]
    preview_response = client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/voice-preview",
        json={"voice": candidate_voice, "language": "ja"},
    )
    assert preview_response.status_code == 200
    assert preview_response.content.startswith(b"RIFF")
    preview_text = base64.b64decode(
        preview_response.headers["x-rolevox-preview-text-b64"]
    ).decode("utf-8")
    assert "Aren" in preview_text
    assert "Gate" in preview_text
    select_response = client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/select-voice",
        json={"voice": candidate_voice},
    )
    assert select_response.status_code == 200
    assert select_response.json()["characters"][0]["casting"]["selected_voice"] == candidate_voice
    lock_response = client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/lock"
    )
    assert lock_response.status_code == 200
    locked = lock_response.json()["characters"][0]
    assert locked["voice_locked"] is True
    assert locked["casting"]["voice_identity"]["locked"] is True
    assert locked["casting"]["voice"] == candidate_voice
    assert client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/select-voice",
        json={"voice": character["casting"]["voice_candidates"][0]["voice"]},
    ).status_code == 409

    unlock_response = client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/unlock"
    )
    assert unlock_response.status_code == 200
    assert unlock_response.json()["characters"][0]["voice_locked"] is False
    relock_response = client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/lock"
    )
    locked = relock_response.json()["characters"][0]

    dialogue_response = client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/dialogues",
        json={"emotion": "fearful but restrained", "text": "Something is breathing beyond the gate."},
    )
    assert dialogue_response.status_code == 201

    second_cast = client.post(
        f"/api/projects/{project['id']}/characters",
        data={"name": "Mira", "brief": "An original young male mage with a bright, urgent delivery.",
              "voice_presentation": "masculine"},
        files={"image": ("mira.png", b"\x89PNG\r\n\x1a\nrolevox-mage", "image/png")},
    )
    assert second_cast.status_code == 201
    second = second_cast.json()["characters"][1]
    assert all(item["voice"] in MASCULINE_VOICES for item in second["casting"]["voice_candidates"])
    second_voice = second["casting"]["voice_candidates"][0]["voice"]
    assert client.post(
        f"/api/projects/{project['id']}/characters/{second['id']}/select-voice",
        json={"voice": second_voice},
    ).status_code == 200
    assert client.post(
        f"/api/projects/{project['id']}/characters/{second['id']}/lock"
    ).status_code == 200
    assert client.post(
        f"/api/projects/{project['id']}/characters/{second['id']}/dialogues",
        json={"emotion": "urgent", "text": "The barrier will not hold much longer."},
    ).status_code == 201

    production_response = client.post(
        f"/api/projects/{project['id']}/produce",
        json={"target_language": "en", "production_mode": "production", "revision_limit": 2,
              "character_id": character["id"]},
    )
    assert production_response.status_code == 202
    job = client.get(f"/api/jobs/{production_response.json()['id']}").json()
    assert job["status"] == "completed"
    result = job["result"]
    assert result["production_mode"] == "production"
    assert result["workflow_mode"] == "dialogue"
    assert result["production_target"] == 86
    assert len(result["casting"]) == 1
    assert len(result["lines"]) == 1
    assert result["casting"][0]["voice"] == locked["casting"]["voice"]
    assert result["casting"][0]["voice_identity"]["locked"] is True
    line = result["lines"][0]
    assert line["emotion"] == "fearful but restrained"
    assert len(line["takes"]) == 2
    assert line["takes"][0]["qa"]["score"] == 78
    assert line["takes"][0]["revision"]["speaking_rate"]["to"] == 0.87
    assert line["takes"][1]["qa"]["score"] == 93
    assert line["takes"][1]["approved"] is True


def test_voice_pack_draft_review_and_standardized_assets(isolated_project_store):
    catalog = client.get("/api/voice-events")
    assert catalog.status_code == 200
    assert any(item["key"] == "greeting" and item["min"] == 3 for item in catalog.json())

    project = client.post("/api/projects", json={
        "title": "Voice Pack Test", "scene": "Moonlit Gate",
        "background": "An original guardian protects a ruined city gate at night.",
    }).json()
    project = client.post(
        f"/api/projects/{project['id']}/characters",
        data={"name": "Aria", "brief": "A disciplined young guardian who hides her concern.",
              "voice_presentation": "feminine"},
        files={"image": ("aria.png", b"\x89PNG\r\n\x1a\nvoice-pack", "image/png")},
    ).json()
    character = project["characters"][0]
    voice = character["casting"]["voice_candidates"][0]["voice"]
    assert client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/select-voice",
        json={"voice": voice},
    ).status_code == 200
    assert client.post(
        f"/api/projects/{project['id']}/characters/{character['id']}/lock"
    ).status_code == 200

    draft_response = client.post(f"/api/projects/{project['id']}/voice-pack/draft", json={
        "character_id": character["id"], "language": "en",
        "events": [{"event": "greeting", "count": 3},
                   {"event": "combat_start", "count": 3}],
    })
    assert draft_response.status_code == 200
    draft = draft_response.json()["lines"]
    assert len(draft) == 6
    assert [line["variant"] for line in draft[:3]] == [1, 2, 3]
    assert all(len(line["emotion"].split(" · ")) == 3 for line in draft)
    assert pipeline_module._voice_pack_emotion("Resolute", "boss_defeated") == (
        "Resolute · exhausted · relieved"
    )
    draft[0]["text"] = "You made it. Stay close while we cross the gate."

    production = client.post(f"/api/projects/{project['id']}/produce", json={
        "target_language": "en", "production_mode": "draft", "revision_limit": 0,
        "workflow_mode": "voice_pack", "pack_character_id": character["id"],
        "pack_lines": draft,
    })
    assert production.status_code == 202
    result = client.get(f"/api/jobs/{production.json()['id']}").json()["result"]
    assert result["workflow_mode"] == "voice_pack"
    assert len(result["lines"]) == 6
    assert result["lines"][0]["file"] == "aria_greeting_01.wav"
    assert result["lines"][3]["file"] == "aria_combat_start_01.wav"
    assert result["lines"][0]["voice_event"] == "greeting"
    assert client.get(f"/api/projects/{project['id']}").json()["characters"][0]["dialogues"] == []


def test_failed_revision_preserves_best_take_and_completes(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline_module, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline_module.state_store, "save_job", lambda *_: None)
    workflow = WorkflowEngine()
    monkeypatch.setattr(workflow, "_upload_optional", lambda *_: None)
    calls = []

    def flaky_tts(client, line, cast, direction, attempt, feedback=""):
        calls.append(attempt)
        if attempt == 0:
            return workflow._demo_wav(line, cast["voice"], attempt)
        raise RuntimeError(
            "Gemini TTS could not complete line 1 after 3 recovery attempts with locked voice Charon."
        )

    monkeypatch.setattr(workflow, "_tts", flaky_tts)
    request = ProjectRequest(
        title="Recovery Test", scene="Throne Room", background="An ancient ruler retreats.",
        target_language="en", script="Odric: Fall back and regroup.",
        quality_threshold=86, max_retries=1, workflow_mode="single",
        line_emotions={1: "Resolute · urgent · heavy-hearted"},
        character_descriptions={"Odric": "An ancient, weathered ruler."},
        locked_casting=[{
            "character": "Odric", "voice": "Charon", "profile": "deep and weathered",
            "voice_locked": True, "voice_identity": {"voice": "Charon", "locked": True},
        }],
    )
    job = workflow.create("recoverjob01", request)
    workflow.run(job, request)

    assert calls == [0, 1]
    assert job.status == "completed"
    assert job.error is None
    assert job.result["needs_review_count"] == 1
    line = job.result["lines"][0]
    assert line["best_available"] is True
    assert line["needs_review"] is True
    assert line["selected_take"] == 1
    assert line["file"].endswith(".wav")
    assert (tmp_path / job.id / line["file"]).is_file()
    assert any(event.agent == "Voice Recovery Agent" for event in job.events)
    assert job.result["run_receipt"]["lines"][0]["best_available"] is True


def test_project_dialogue_order_target_edit_and_recast(isolated_project_store):
    project = client.post("/api/projects", json={
        "title": "Context Test", "scene": "Camp", "background": "Two allies discuss the next move.",
    }).json()
    for name, presentation in (("Rin", "feminine"), ("Taro", "masculine")):
        response = client.post(
            f"/api/projects/{project['id']}/characters",
            data={"name": name, "brief": f"{name} is a calm original game character.",
                  "voice_presentation": presentation},
            files={"image": (f"{name}.png", b"\x89PNG\r\n\x1a\nrolevox-context", "image/png")},
        )
        assert response.status_code == 201
        project = response.json()
    rin, taro = project["characters"]

    first = client.post(
        f"/api/projects/{project['id']}/characters/{rin['id']}/dialogues",
        json={"emotion": "quiet concern", "text": "Are you ready?", "addressee_id": taro["id"]},
    )
    assert first.status_code == 201
    first_line = first.json()["characters"][0]["dialogues"][0]
    second = client.post(
        f"/api/projects/{project['id']}/characters/{taro['id']}/dialogues",
        json={"emotion": "steady", "text": "I am.", "addressee_id": None},
    )
    assert second.status_code == 201
    project = second.json()
    assert project["characters"][0]["dialogues"][0]["order"] == 1
    assert project["characters"][1]["dialogues"][0]["order"] == 2

    edited = client.patch(
        f"/api/projects/{project['id']}/characters/{rin['id']}/dialogues/{first_line['id']}",
        json={"emotion": "guarded concern", "text": "Are you truly ready?", "addressee_id": taro["id"]},
    )
    assert edited.status_code == 200
    assert edited.json()["characters"][0]["dialogues"][0]["emotion"] == "guarded concern"

    recast = client.post(
        f"/api/projects/{project['id']}/characters/{rin['id']}/recast",
        json={"voice_presentation": "masculine"},
    )
    assert recast.status_code == 200
    recast_character = recast.json()["characters"][0]
    assert recast_character["casting"]["selected_voice"] is None
    assert all(item["voice"] in MASCULINE_VOICES
               for item in recast_character["casting"]["voice_candidates"])
    project = recast.json()
    for character in project["characters"]:
        voice = character["casting"]["voice_candidates"][0]["voice"]
        selected = client.post(
            f"/api/projects/{project['id']}/characters/{character['id']}/select-voice",
            json={"voice": voice},
        )
        assert selected.status_code == 200
        assert client.post(
            f"/api/projects/{project['id']}/characters/{character['id']}/lock"
        ).status_code == 200
    production = client.post(
        f"/api/projects/{project['id']}/produce",
        json={"target_language": "en", "production_mode": "draft", "revision_limit": 0},
    )
    assert production.status_code == 202
    result = client.get(f"/api/jobs/{production.json()['id']}").json()["result"]
    assert [line["source_text"] for line in result["lines"]] == ["Are you truly ready?", "I am."]
    assert result["lines"][0]["addressee"] == "Taro"
    assert result["lines"][1]["addressee"] == "context-inferred"

    before = sum(len(character["dialogues"]) for character in client.get(
        f"/api/projects/{project['id']}"
    ).json()["characters"])
    single = client.post(
        f"/api/projects/{project['id']}/produce",
        json={"target_language": "ja", "production_mode": "draft", "revision_limit": 0,
              "workflow_mode": "single", "single_character_id": rin["id"],
              "single_emotion": "quiet resolve", "single_text": "We move at dawn."},
    )
    assert single.status_code == 202
    single_result = client.get(f"/api/jobs/{single.json()['id']}").json()["result"]
    assert single_result["workflow_mode"] == "single"
    assert len(single_result["lines"]) == 1
    assert single_result["lines"][0]["source_text"] == "We move at dawn."
    after = sum(len(character["dialogues"]) for character in client.get(
        f"/api/projects/{project['id']}"
    ).json()["characters"])
    assert after == before


def test_project_rename_and_recoverable_delete(isolated_project_store, tmp_path):
    created = client.post("/api/projects", json={
        "title": "Old Name", "scene": "Opening", "background": "A test world.",
    }).json()
    renamed = client.patch(f"/api/projects/{created['id']}", json={
        "title": "New Name", "scene": "New Scene", "background": "An updated world background.",
    })
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "New Name"
    assert renamed.json()["scene"] == "New Scene"
    assert renamed.json()["background"] == "An updated world background."

    deleted = client.delete(f"/api/projects/{created['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{created['id']}").status_code == 404
    trash = tmp_path / "project-trash"
    assert any(path.name.startswith(created["id"]) for path in trash.iterdir())


def test_character_name_and_brief_edit_preserves_voice_lock(isolated_project_store):
    project = client.post("/api/projects", json={
        "title": "Editable Cast", "scene": "Tower", "background": "An original fantasy tower.",
    }).json()
    cast = client.post(
        f"/api/projects/{project['id']}/characters",
        data={"name": "Mira", "brief": "A calm original female mage.",
              "voice_presentation": "feminine"},
        files={"image": ("mira.png", b"\x89PNG\r\n\x1a\neditable", "image/png")},
    ).json()["characters"][0]
    voice = cast["casting"]["voice_candidates"][0]["voice"]
    assert client.post(
        f"/api/projects/{project['id']}/characters/{cast['id']}/select-voice", json={"voice": voice}
    ).status_code == 200
    locked = client.post(
        f"/api/projects/{project['id']}/characters/{cast['id']}/lock"
    ).json()["characters"][0]

    edited = client.patch(
        f"/api/projects/{project['id']}/characters/{cast['id']}",
        json={"name": "Mira Vale", "brief": "A calm original mage who now guards the tower."},
    )
    assert edited.status_code == 200
    character = edited.json()["characters"][0]
    assert character["name"] == "Mira Vale"
    assert character["brief"].endswith("guards the tower.")
    assert character["voice_locked"] is True
    assert character["casting"]["voice"] == locked["casting"]["voice"]
    assert character["casting"]["character"] == "Mira Vale"


def test_character_delete_is_recoverable_and_clears_addressee(isolated_project_store, tmp_path):
    project = client.post("/api/projects", json={
        "title": "Delete Cast", "scene": "Bridge", "background": "Two original allies on a bridge.",
    }).json()
    for name in ("Ari", "Bram"):
        response = client.post(
            f"/api/projects/{project['id']}/characters",
            data={"name": name, "brief": f"{name} is an original game character.",
                  "voice_presentation": "neutral"},
            files={"image": (f"{name}.png", b"\x89PNG\r\n\x1a\ndelete-test", "image/png")},
        )
        assert response.status_code == 201
        project = response.json()
    ari, bram = project["characters"]
    project = client.post(
        f"/api/projects/{project['id']}/characters/{ari['id']}/dialogues",
        json={"emotion": "calm", "text": "Wait here.", "addressee_id": bram["id"]},
    ).json()
    assert client.post(
        f"/api/projects/{project['id']}/characters/{bram['id']}/dialogues",
        json={"emotion": "steady", "text": "Understood.", "addressee_id": ari["id"]},
    ).status_code == 201

    deleted = client.delete(f"/api/projects/{project['id']}/characters/{bram['id']}")
    assert deleted.status_code == 200
    remaining = deleted.json()["characters"]
    assert [character["id"] for character in remaining] == [ari["id"]]
    assert remaining[0]["dialogues"][0]["addressee_id"] is None
    trash = tmp_path / "project-trash" / "characters"
    archived = next(path for path in trash.iterdir() if bram["id"] in path.name)
    assert (archived / "character.json").is_file()
    assert any(path.suffix == ".png" for path in archived.iterdir())
