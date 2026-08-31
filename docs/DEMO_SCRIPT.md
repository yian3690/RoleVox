# RoleVox — 3-minute Taskmaster demo

## 0:00–0:25 — Problem

“Indie game teams do not need one impressive TTS line. They need hundreds of lines that preserve the same character identity. RoleVox is a game-character voice system that casts, locks, directs, critiques, and packages synthetic voices.”

## 0:25–1:05 — Visual Casting + Voice Lock

1. Open a project and show its scene/world context.
2. Add a fictional character image and brief.
3. Open the Character Card and point to the visible cues used by Visual Casting.
4. Preview the three presentation-compatible system voices, select one, and lock it.
5. Say: “This Voice Identity now remains stable across the whole project.”

## 1:05–1:40 — Human constraints

1. Choose Single Character or Dialogue production.
2. Select Chinese, Japanese, or English output.
3. Add emotion and dialogue; for dialogue mode, show context-aware addressee inference.
4. Select Draft, Production, or Cinematic and a bounded revision limit.

## 1:40–2:30 — Agentic execution

1. Start production and show the live event trace.
2. Point out Cloud Tasks dispatch, Google ADK direction, translation, locked casting, dialogue planning, TTS, and Voice Critic.
3. If Take 01 misses the target, show the exact emotion/rate/breathiness/pause changes and Take 02 regeneration.
4. Say: “RoleVox listens to its own performance and directs another take when the acting is not good enough.”

## 2:30–3:00 — Proof and delivery

1. Show the approved score and audio player.
2. Show the Autonomous Run Receipt: origin, Google ADK orchestrator, Cloud Tasks worker, and synthetic-only policy.
3. Download the package and show named WAVs, `manifest.json`, and `run_receipt.json`.
4. Close with: “Upload an inbox manifest and Eventarc can start the same idempotent production loop without a human pressing Run.”

## Verified live proof

- Cloud Run revision: `rolevox-00008-lc4`
- Durable ADK + Receipt verification job: `72158be4d09b`
- Result: completed, score 94, Google ADK orchestrator, Cloud Tasks worker,
  private GCS package, and verified WAV SHA-256
