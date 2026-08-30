"""Google ADK declaration used by the production workflow and `adk web`.

The FastAPI service performs the same stages programmatically so it can expose
job progress, audio files, and retries. This root agent keeps the workflow
inspectable with standard ADK tooling.
"""

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent

MODEL = "gemini-3.5-flash"

director_agent = LlmAgent(
    name="DirectorAgent",
    model=MODEL,
    description="Builds a coherent dramatic direction from a game script.",
    instruction=(
        "Analyze the supplied game scene. Identify genre, stakes, emotional arc, "
        "setting and safe performance direction. Never imitate a real person."
    ),
    output_key="direction",
)

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
