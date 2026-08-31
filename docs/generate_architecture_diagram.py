from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


W, H = 2400, 1350
BG = "#F3EFE6"
INK = "#111312"
PANEL = "#FAF8F1"
MUTED = "#625F58"
LINE = "#C9C4B8"
LIME = "#CBFF2E"
CORAL = "#FF5A43"
GREEN = "#4C9B43"


def font(size, bold=False, mono=False):
    if mono:
        path = r"C:\Windows\Fonts\consola.ttf"
    elif bold:
        path = r"C:\Windows\Fonts\arialbd.ttf"
    else:
        path = r"C:\Windows\Fonts\arial.ttf"
    return ImageFont.truetype(path, size)


F_TITLE = font(58, bold=True)
F_SUB = font(24)
F_ZONE = font(20, mono=True)
F_CARD_TITLE = font(29, bold=True)
F_CARD_BODY = font(18)
F_SMALL = font(17, mono=True)
F_TAG = font(18, bold=True, mono=True)
F_ENGINE = font(23, bold=True)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def text_width(text, f):
    return d.textbbox((0, 0), text, font=f)[2]


def wrap(text, f, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = word if not current else current + " " + word
        if text_width(trial, f) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def rounded_box(box, fill=PANEL, outline=LINE, width=2, radius=12):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def tag(x, y, label, fill=INK, fg=LIME):
    tw = text_width(label, F_TAG)
    rounded_box((x, y, x + tw + 30, y + 40), fill=fill, outline=fill, radius=4)
    d.text((x + 15, y + 9), label, font=F_TAG, fill=fg)
    return x + tw + 44


def card(x, y, w, h, eyebrow, title, body, accent=LIME, dark=False):
    fill = INK if dark else PANEL
    fg = "#FFFFFF" if dark else INK
    secondary = "#D6D3CB" if dark else MUTED
    rounded_box((x, y, x + w, y + h), fill=fill, outline=INK if dark else LINE, width=2)
    d.rectangle((x, y, x + 9, y + h), fill=accent)
    d.text((x + 28, y + 20), eyebrow.upper(), font=F_SMALL, fill=accent if dark else CORAL)
    d.text((x + 28, y + 52), title, font=F_CARD_TITLE, fill=fg)
    lines = []
    for paragraph in body.split("\n"):
        lines.extend(wrap(paragraph, F_CARD_BODY, w - 56))
    max_lines = max(1, ((h - 92 - 18) // 22) + 1)
    for i, line in enumerate(lines[:max_lines]):
        d.text((x + 28, y + 92 + i * 22), line, font=F_CARD_BODY, fill=secondary)


def arrow(points, color=INK, width=5, dashed=False, label=None, label_xy=None):
    if dashed:
        for a, b in zip(points[:-1], points[1:]):
            x1, y1 = a
            x2, y2 = b
            length = max(abs(x2 - x1), abs(y2 - y1))
            if length == 0:
                continue
            steps = max(1, int(length / 24))
            for i in range(0, steps, 2):
                t1, t2 = i / steps, min((i + 1) / steps, 1)
                p1 = (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1)
                p2 = (x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2)
                d.line((p1, p2), fill=color, width=width)
    else:
        d.line(points, fill=color, width=width, joint="curve")
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 > x1 else -1
        tip = [(x2, y2), (x2 - 15 * direction, y2 - 10), (x2 - 15 * direction, y2 + 10)]
    else:
        direction = 1 if y2 > y1 else -1
        tip = [(x2, y2), (x2 - 10, y2 - 15 * direction), (x2 + 10, y2 - 15 * direction)]
    d.polygon(tip, fill=color)
    if label and label_xy:
        lx, ly = label_xy
        tw = text_width(label, F_SMALL)
        d.rectangle((lx - 7, ly - 3, lx + tw + 7, ly + 23), fill=BG)
        d.text((lx, ly), label, font=F_SMALL, fill=MUTED)


# Header
d.rectangle((0, 0, W, 172), fill=INK)
d.rectangle((0, 166, W, 172), fill=LIME)
d.text((64, 36), "ROLEVOX", font=F_TITLE, fill=LIME)
d.text((390, 45), "AGENTIC VOICE PRODUCTION ARCHITECTURE", font=font(39, bold=True), fill="#FFFFFF")
d.text((64, 112), "Multimodal casting → durable agent execution → self-critique → game-ready assets", font=F_SUB, fill="#D7D5CF")
x_tag = 1680
x_tag = tag(x_tag, 93, "VERTEX AI", fill="#2A2D2B", fg="#FFFFFF")
x_tag = tag(x_tag, 93, "GOOGLE ADK", fill="#2A2D2B", fg="#FFFFFF")
tag(x_tag, 93, "NO CLONING", fill=CORAL, fg="#FFFFFF")

# Zone headings
zones = [
    (54, 200, 420, "01 · INPUTS & TRIGGERS"),
    (505, 200, 520, "02 · DURABLE CLOUD RUNTIME"),
    (1058, 200, 700, "03 · AGENTIC AI LOOP"),
    (1790, 200, 556, "04 · GAME-READY OUTPUTS"),
]
for x, y, w, title in zones:
    d.text((x, y), title, font=F_ZONE, fill=CORAL)
    d.line((x, y + 34, x + w, y + 34), fill=LINE, width=2)

# Inputs
card(54, 260, 420, 150, "CREATOR", "Game Team / Voice Director", "Sets the world, scene, characters, dialogue, language, and revision limits.", dark=True)
card(54, 445, 420, 145, "PRODUCT SURFACE", "RoleVox Web Studio + API", "Character Cards, Visual Casting, Voice Lock, live traces, QA, and Run History.")
card(54, 665, 420, 135, "AUTONOMOUS ENTRY", "Private GCS Inbox", "A finalized inbox/*.json manifest can launch the same production workflow.")
card(54, 835, 420, 125, "EVENT DELIVERY", "Eventarc + Pub/Sub", "Object-finalized events are delivered through an authenticated trigger.")

# Durable runtime
card(505, 260, 520, 145, "PUBLIC APPLICATION", "Cloud Run · rolevox", "FastAPI application, REST endpoints, validation, job creation, and progress polling.", accent=LIME, dark=True)
card(505, 450, 520, 135, "PERSISTENT STATE", "Firestore", "Projects, Character Cards, Voice Locks, jobs, traces, results, and idempotency claims.")
card(505, 640, 520, 130, "DURABLE DISPATCH", "Cloud Tasks", "Bounded, throttled background work with deterministic task IDs and OIDC authentication.", accent=CORAL)
card(505, 825, 520, 145, "AUTHENTICATED WORKER", "Cloud Run · Production Worker", "A synchronous worker executes each production to completion and persists every stage.", dark=True)

# Agentic AI loop
card(1058, 260, 700, 135, "ORCHESTRATOR", "Google ADK · ProductionDirectorAgent", "Coordinates agents, constraints, locked identities, retry limits, and the production trace.", dark=True)
card(1058, 435, 700, 185, "REASONING + MULTIMODAL", "Gemini 3.5 Flash · Vertex AI", "Director Agent · Translation Agent · Casting Agent · Dialogue Agent\nVisual Casting · event-line drafting · audio critique", accent=LIME)
card(1058, 660, 330, 145, "PERFORMANCE", "Gemini 3.1 Flash TTS", "Generates controllable speech with allowlisted Google synthetic voices.", accent=LIME)
card(1428, 660, 330, 145, "LISTEN + SCORE", "Multimodal Voice Critic", "Emotion · identity · pronunciation · scene fit", accent=CORAL)
card(1058, 850, 700, 125, "QUALITY GATE", "Audio QA + Best-Take Selection", "Approves the strongest take or applies explicit direction and requests another bounded revision.")

# Outputs
card(1790, 260, 556, 135, "PRIVATE ASSET STORE", "Cloud Storage", "Character references, final WAV files, manifests, receipts, and ZIP packages.", dark=True)
card(1790, 440, 556, 155, "TRACEABLE DELIVERY", "Autonomous Run Receipt", "Agent trace · model IDs · human constraints · selected takes · retry counts · SHA-256 hashes")
card(1790, 640, 556, 145, "DOWNLOAD", "Game Package ZIP", "Named WAV assets plus source/translated text and implementation-ready metadata.", accent=LIME)

# Engine output grid
d.text((1790, 830), "ENGINE EXPORT PRESETS", font=F_SMALL, fill=CORAL)
engines = [
    (1790, "Unity", "JSON manifest"),
    (2073, "Unreal", "DataTable JSON"),
    (1790, "Godot", "JSON manifest"),
    (2073, "Generic", "CSV + JSON"),
]
for i, (x, name, detail) in enumerate(engines):
    y = 865 if i < 2 else 985
    rounded_box((x, y, x + 263, y + 96), fill=PANEL, outline=INK, width=2, radius=8)
    d.text((x + 20, y + 15), name, font=F_ENGINE, fill=INK)
    d.text((x + 20, y + 56), detail, font=F_SMALL, fill=MUTED)

# Main arrows
arrow([(474, 335), (505, 335)], color=LIME)
arrow([(264, 410), (264, 445)], color=INK)
arrow([(474, 895), (490, 895), (490, 332), (505, 332)], color=CORAL, label="OIDC", label_xy=(430, 610))
arrow([(264, 800), (264, 835)], color=INK)
arrow([(765, 405), (765, 450)], color=INK, label="persist", label_xy=(782, 419))
arrow([(765, 585), (765, 640)], color=INK, label="enqueue", label_xy=(782, 598))
arrow([(765, 770), (765, 825)], color=CORAL, label="OIDC", label_xy=(782, 785))
arrow([(1025, 895), (1040, 895), (1040, 330), (1058, 330)], color=LIME)
arrow([(1408, 395), (1408, 435)], color=INK)
arrow([(1223, 620), (1223, 660)], color=INK)
arrow([(1388, 733), (1428, 733)], color=INK)
arrow([(1593, 805), (1593, 850)], color=INK)

# Revision loop
arrow([(1593, 660), (1593, 635), (1223, 635), (1223, 660)], color=CORAL, width=5, label="below target · revise", label_xy=(1320, 608))

# Firestore state from worker
arrow([(505, 895), (488, 895), (488, 520), (505, 520)], color=INK, dashed=True, label="progress + trace", label_xy=(510, 790))

# Output arrows
arrow([(1758, 912), (1775, 912), (1775, 328), (1790, 328)], color=LIME)
arrow([(2068, 395), (2068, 440)], color=INK)
arrow([(2068, 595), (2068, 640)], color=INK)
arrow([(2068, 785), (2068, 820)], color=INK)

# Footer assurance strip
d.rectangle((0, 1165, W, H), fill=INK)
d.text((60, 1200), "SECURITY & RELIABILITY", font=F_ZONE, fill=CORAL)
footer_items = [
    (60, "OIDC-protected worker", "Exact service-account identity and audience verification"),
    (630, "Durable + idempotent", "Cloud Tasks, Firestore state, deterministic task and event claims"),
    (1220, "Bounded autonomy", "≤24 lines · ≤10 characters · ≤3 revisions per line"),
    (1780, "Synthetic-only policy", "Prebuilt Google voices · no uploads · no voice cloning"),
]
for x, title, body in footer_items:
    d.text((x, 1240), title, font=font(24, bold=True), fill=LIME)
    for i, line in enumerate(wrap(body, F_SMALL, 500)[:2]):
        d.text((x, 1277 + i * 23), line, font=F_SMALL, fill="#CFCCC5")

out = Path(__file__).with_name("rolevox-architecture-diagram.png")
img.save(out, "PNG", optimize=True)
print(out)
