# RoleVox — Devpost submission draft

## Tagline

The agentic game-character voice system that casts from visuals, locks voice identity, listens to every take, and autonomously directs a better performance.

## Inspiration

Independent game teams can generate a single voice line, but a real character may need 500–5,000 lines across many chapters. The hard problem is not only speech synthesis: it is preserving identity, directing context-aware acting, detecting weak performances, and delivering production-ready assets without creating voice-rights risk.

## What it does

RoleVox starts with a project world, scene, character image, and creator brief. Visual Casting explains which performance-relevant visual cues influenced its result and proposes three presentation-compatible Google synthetic voices. The creator auditions one and locks the Voice Identity for the whole project.

For production, the creator selects Chinese, Japanese, or English; Single Character or Dialogue mode; Draft, Production, or Cinematic quality; and a bounded revision limit. Google ADK directs the scene, Translation Agent localizes it, Dialogue Agent plans each delivery, and Gemini TTS performs it. Voice Critic then listens to the WAV and scores emotion match, character consistency, pronunciation, and scene fit. A weak take receives explicit emotion, rate, breathiness, and pause revisions and is regenerated automatically.

The result is a game asset package containing named WAV files, a traceable manifest, and an Autonomous Run Receipt with the agent trace, human constraints, model IDs, selected takes, scores, retry counts, synthetic-only policy, and SHA-256 hashes.

## Why it is agentic

RoleVox does more than call TTS. It observes project state, reasons over images and dialogue context, preserves a long-lived Voice Identity, evaluates its own audio output, changes performance parameters, and repeats the action within a creator-defined boundary. A private Cloud Storage Inbox can trigger the same idempotent pipeline autonomously through Eventarc.

## How we built it

- Google ADK `ProductionDirectorAgent` executed through the production runtime
- Gemini 3.5 Flash on Vertex AI for direction, translation, multimodal visual casting, dialogue planning, and audio critique
- Gemini 3.1 Flash TTS Preview with allowlisted prebuilt synthetic voices
- Cloud Run for the web application and synchronous production worker
- Cloud Tasks for durable, OIDC-authenticated, single-concurrency job execution
- Firestore for projects, Voice Locks, job traces, results, and inbox idempotency
- Eventarc for private GCS `inbox/*.json` finalized events
- Private Cloud Storage for character references, WAVs, manifests, receipts, and ZIP packages

## Challenges

Cloud Run's request-based CPU exposed an important reliability issue: a FastAPI background task can stop making progress after the HTTP response. We replaced that path with Cloud Tasks calling an authenticated synchronous worker, and persisted every agent stage in Firestore. Gemini TTS can also return recoverable incomplete-audio responses, so RoleVox uses a bounded same-voice recovery sequence and never changes a locked voice.

## Accomplishments

- A real Google ADK production path, not only an architecture diagram
- Multimodal visual casting with explainable cues and three gender/presentation-compatible auditions
- Project-wide Voice Lock for long-form game dialogue consistency
- Multimodal Voice Critic with visible take-by-take auto-revision
- Durable Cloud Tasks + Firestore execution and idempotent Eventarc Inbox
- Verifiable Autonomous Run Receipt and hashed final WAV assets
- Chinese, Japanese, and English input/localization/output
- No voice uploads, cloning, or real-person imitation

## Verified deployment

- App: https://rolevox-919890071642.asia-east1.run.app
- Final revision: `rolevox-00008-lc4`
- Verification job: `72158be4d09b`
- Result: completed; Critic score 94; Google ADK; Cloud Tasks; receipt hash verified
- Automated tests: 19 passed

## What's next

Add pronunciation dictionaries and glossary versioning, batch CSV/Ink/Yarn import, timeline-level scene direction, human approval gates for cinematic lines, team roles, usage budgets per project, and engine-specific Unity/Godot/Unreal importers.

