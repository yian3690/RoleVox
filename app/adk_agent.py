"""Google ADK agents plus the Director stage used by RoleVox production."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

MODEL = "gemini-3.5-flash"

def _director(name: str) -> LlmAgent:
    return LlmAgent(
        name=name,
        model=MODEL,
        description="Builds a coherent dramatic direction from a game script.",
        instruction=(
            "Analyze the supplied game scene. Return one JSON object with genre, setting, "
            "stakes, emotional_arc, performance_notes, and pronunciation_risks. Preserve "
            "Chinese, English, and Japanese text. Never imitate or reference a real person."
        ),
        output_key="direction",
        generate_content_config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.25,
        ),
    )


director_agent = _director("DirectorAgent")
production_director_agent = _director("ProductionDirectorAgent")

translation_agent = LlmAgent(
    name="TranslationAgent",
    model=MODEL,
    description="Localizes every game line into the selected target language.",
    instruction=(
        "Translate every dialogue line into the user-selected target language. "
        "Preserve character names, line IDs, meaning, subtext and game terminology. "
        "Return both source text and localized text for traceability."
    ),
    output_key="localized_dialogue",
)

casting_agent = LlmAgent(
    name="CastingAgent",
    model=MODEL,
    description="Assigns original prebuilt Gemini voices to fictional characters.",
    instruction=(
        "Using {direction}, cast every character with a distinct prebuilt Gemini TTS "
        "voice. Use fictional vocal traits only; do not clone or name real performers."
    ),
    output_key="casting",
)

dialogue_agent = LlmAgent(
    name="DialogueAgent",
    model=MODEL,
    description="Annotates each line with emotion, intensity and pacing.",
    instruction=(
        "Using {direction}, {casting}, and {localized_dialogue}, annotate every localized "
        "dialogue line. Preserve the translated spoken text exactly and support "
        "Traditional Chinese, English and Japanese."
    ),
    output_key="dialogue_plan",
)

voice_critic_agent = LlmAgent(
    name="VoiceCriticAgent",
    model=MODEL,
    description="Listens to each take and scores acting quality against a locked voice identity.",
    instruction=(
        "Evaluate emotion match, character consistency, pronunciation and scene fit. "
        "When a take misses the production target, return explicit changes to emotion "
        "intensity, speaking rate, breathiness and pauses for the next take."
    ),
    output_key="voice_critique",
)

revision_agent = LlmAgent(
    name="AutoRevisionAgent",
    model=MODEL,
    description="Turns Voice Critic findings into a safer, stronger next-take direction.",
    instruction=(
        "Using {voice_critique}, revise performance parameters without changing the "
        "spoken text or the project's locked synthetic voice identity."
    ),
    output_key="take_revision",
)

root_agent = SequentialAgent(
    name="RoleVoxPipeline",
    description="Translates, directs, casts and prepares multilingual game dialogue for TTS.",
    sub_agents=[director_agent, translation_agent, casting_agent, dialogue_agent,
                voice_critic_agent, revision_agent],
)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError("ADK DirectorAgent must return one JSON object.")
    return payload


async def _run_director_async(prompt: str, run_id: str) -> tuple[dict[str, Any], list[str]]:
    """Execute the real ADK runtime and return the Director result plus trace authors."""

    runner = InMemoryRunner(agent=production_director_agent, app_name="rolevox-production")
    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="rolevox-system",
        session_id=run_id,
    )
    final_text = ""
    trace: list[str] = []
    async for event in runner.run_async(
        user_id="rolevox-system",
        session_id=session.id,
        new_message=types.UserContent(parts=[types.Part(text=prompt)]),
    ):
        author = str(getattr(event, "author", "") or "ADK")
        if author not in trace:
            trace.append(author)
        content = getattr(event, "content", None)
        for part in (getattr(content, "parts", None) or []):
            if getattr(part, "text", None):
                final_text = part.text
    if not final_text:
        raise RuntimeError("ADK DirectorAgent returned no final response.")
    return _extract_json(final_text), trace


def run_director(prompt: str, run_id: str | None = None) -> tuple[dict[str, Any], list[str]]:
    """Synchronous boundary used by the FastAPI background production worker."""

    return asyncio.run(_run_director_async(prompt, run_id or uuid.uuid4().hex))
