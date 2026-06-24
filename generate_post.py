#!/usr/bin/env python3
"""
Daily LinkedIn post generator — GLOBAL AI NEWS edition.

Writes ONE new "what's moving in AI" post and appends it to posts.json.
Run via GitHub Actions (generate.yml) every day at 2 AM UTC. Posting happens on
alternate days, so each published post is a fresh take on an important AI shift.

Text provider (best quality first):
  - Claude Opus 4.8  (set ANTHROPIC_API_KEY) — default when available
  - Google Gemini    (set GOOGLE_API_KEY)    — fallback

Control with TEXT_PROVIDER=claude|gemini|auto (default: auto).

IMPORTANT — accuracy model:
  The text model writes from its own knowledge (no live web fetch), so it CANNOT
  know what broke today. To protect the brand it is hard-instructed never to
  invent dates, version numbers, benchmark figures, funding amounts, or quotes,
  and to frame posts as sharp analysis of well-established AI developments and
  credible near-term trajectories — not fake same-day scoops.

  OPTIONAL real-news upgrade (hook, no extra deps): if a file `news_context.txt`
  exists next to this script (or env NEWS_CONTEXT is set), its contents are
  injected as VERIFIED headlines and the model must write about those instead of
  picking a theme. Fill that file from an RSS/news step to get true daily news.
"""

import json
import os
import sys
import time
import requests

from image_prompts import pick_image_style


def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + GEMINI_MODEL
    + ":generateContent"
)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "").strip() or "claude-opus-4-8"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

TEXT_PROVIDER = (os.environ.get("TEXT_PROVIDER", "").strip().lower() or "auto")

POSTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts.json")

# Global AI themes to rotate through so posts stay fresh and varied.
# These are CATEGORIES, not specific scoops — the model turns one into a sharp,
# accurate take on a well-established development or a credible near-term trend.
# (Ignored automatically when news_context.txt / NEWS_CONTEXT supplies real news.)
TOPIC_POOL = [
    "Frontier LLMs: the jump from chatbots to reasoning models",
    "AI agents that actually do work, not just chat",
    "Open-weight models closing the gap with closed labs",
    "Multimodal AI: models that see, hear, and act",
    "AI for science: protein folding, materials, and drug discovery",
    "The compute race: GPUs, custom AI chips, and scarcity",
    "AI coding assistants reshaping how software is built",
    "Small, on-device models bringing AI to phones and laptops",
    "AI safety and alignment: why labs are racing to control it",
    "Global AI regulation: the EU AI Act and what follows",
    "Robotics and embodied AI stepping out of the lab",
    "Retrieval and long context: AI that remembers more",
    "AI in healthcare: diagnosis, imaging, and triage",
    "The economics of inference: why running AI is the new cost",
    "Synthetic data and the looming 'data wall'",
    "AI video and image generation going production-grade",
    "Enterprise AI: from pilots to real deployment at scale",
    "AI and energy: the data-center power problem",
    "Evaluations and benchmarks: how we actually measure AI",
    "Voice and real-time AI: the new human-computer interface",
]

SYSTEM_PROMPT = """# ROLE
You write the daily AI brief for a sharp, globally-followed LinkedIn page. Voice:
a senior AI insider who explains the field to smart, busy people — engineers,
founders, and executives. Confident, curious, and clear. Never hype, never salesy,
never a Twitter-thread guru. Think "trusted analyst who actually ships," not influencer.

# WHAT TO WRITE ABOUT
ONE genuinely interesting development, capability shift, or credible near-term
trajectory in AI — global in scope, never tied to one country or region. Good
angles: a real capability leap and why it matters, a counter-intuitive truth most
people miss, a "here's what's actually changing" reframe, or a grounded look at
where a trend is heading. Make the reader feel they understand something better
than they did 15 seconds ago.

# ACCURACY — NON-NEGOTIABLE (this auto-posts to a real brand)
You write from your own training knowledge with NO live news feed, so you CANNOT
know what happened today. Therefore:
- NEVER invent or imply a same-day scoop. No "Breaking", no "today", no "just
  announced", no specific calendar dates.
- NEVER fabricate specifics: do NOT state exact version numbers, benchmark scores,
  parameter counts, funding amounts, valuations, user counts, percentages, or
  direct quotes unless they are genuinely well-established, widely-known facts.
- Prefer durable truths and directional framing ("reasoning models are pulling
  ahead", "agents are moving from demos to production", "inference cost is the new
  bottleneck") over precise figures you can't verify.
- When pointing at the future, hedge honestly: "the trajectory suggests",
  "signals point to", "expect", "is likely to" — never assert the unknowable.
- If you're not sure a fact is solid, leave it out. A sharp, true idea beats a
  specific, fragile claim. When in doubt, write insight, not statistics.

# IF VERIFIED NEWS IS PROVIDED
If the user message includes a "VERIFIED HEADLINES" block, treat it as today's real,
fact-checked news: write your post strictly about ONE of those items, you MAY use the
concrete facts it contains, and ignore the suggested theme.

# FORMAT (strict)
- HARD LIMIT: 60 words MAXIMUM for the post body (NOT counting the hashtag line).
  Shorter and punchier is better.
- Line 1: a scroll-stopping hook — a surprising fact, a sharp claim, or a vivid
  one-liner. No "Did you know" clichés.
- Then ONE idea in 2–4 tight sentences. No bullet lists, no arrows, no jargon walls,
  no em-dash soup. Plain, confident English a non-expert still follows.
- End with a light engagement nudge that invites a real reply (e.g. a genuine
  question, or 'What would you build with this?'). Keep it natural, not gimmicky.
- Then EXACTLY 3 relevant hashtags on their OWN final line (e.g. #AI #MachineLearning #Tech).
- First person ("I"/"we"), human, opinionated but fair. No emojis in the body text.

# IMAGE — always ONE original, photorealistic AI image (no text, no infographics)
Every post gets a single striking, cinematic photo that visually captures THIS
post's idea. Set image_style = "photo" ALWAYS, and ALWAYS provide image_prompt.

image_prompt rules:
- 30–60 words describing ONE real, photographable SCENE a world-class photographer
  could shoot — concrete and visual. Name the SUBJECT, the ACTION, the SETTING, the
  LIGHTING, the LENS/MOOD, and the COLOR. One hero subject, not a busy collage.
- Translate the abstract AI idea into a bold, unexpected, metaphor-rich VISUAL.
  Avoid the tired "person smiling at a laptop" — make it cinematic and original.
- It must clearly relate to the post's topic at a glance.
- NEVER mention text, words, letters, numbers, labels, logos, dashboards, charts,
  or UI screens — AI-rendered text looks broken and the renderer adds none.

Good image_prompt examples (match this vividness, vary the idea):
  • Agents doing work → "A human hand and a sleek matte-black robotic hand together
    assembling a glowing circuit board on a dark workbench, blue sparks suspended in
    the air, dramatic side light, shallow focus."
  • AI for science → "A lone researcher silhouetted in a darkened lab, studying a
    luminous floating 3D protein structure made of light, cool blue glow on her face,
    cinematic haze."
  • The compute race → "Extreme macro of an advanced AI processor, circuitry pulsing
    electric blue, a single warm rim light, fine dust particles drifting, deep black
    background."
  • On-device AI → "A smartphone on a wooden desk projecting a small hologram of a
    brain woven from light, soft golden window light behind, intimate and quiet."
  • AI safety → "One engineer dwarfed by a vast dark data hall, a single illuminated
    control console casting cold blue light across endless server racks."
"""

_STOPWORDS = {
    "ai", "the", "a", "an", "and", "of", "to", "for", "in", "on", "with",
    "from", "that", "not", "just", "new", "how", "why", "what", "is", "are",
}


def _topic_signature(topic):
    """Most distinctive word in a topic, used for light de-duplication."""
    for word in topic.lower().replace(":", " ").replace(",", " ").split():
        w = word.strip("-")
        if w and w not in _STOPWORDS and len(w) > 3:
            return w
    return topic.split()[0].lower()


def pick_topic(existing_posts):
    """Pick a theme whose distinctive keyword wasn't used in recent posts."""
    recent_texts = " ".join(
        (p.get("text", "") + " " + p.get("topic", "")) for p in existing_posts[-12:]
    ).lower()
    for topic in TOPIC_POOL:
        if _topic_signature(topic) not in recent_texts:
            return topic
    # Fallback: rotate deterministically by date so we still vary.
    day_of_year = int(time.strftime("%j"))
    return TOPIC_POOL[day_of_year % len(TOPIC_POOL)]


def _load_news_context():
    """Optional real-news hook. Returns verified-headlines text, or ''.

    Lets you upgrade to true daily news WITHOUT changing this script: have an
    upstream step (RSS reader, news API, etc.) write recent, fact-checked AI
    headlines to env NEWS_CONTEXT or to a `news_context.txt` file beside this
    script. When present, the model writes about those instead of a theme.
    """
    ctx = os.environ.get("NEWS_CONTEXT", "").strip()
    if ctx:
        return ctx
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_context.txt")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""
    return ""


def _build_user_prompt(topic, suggested_style):
    news = _load_news_context()
    if news:
        focus = (
            "VERIFIED HEADLINES (real, fact-checked — write about ONE of these and "
            "you MAY use their concrete facts):\n%s\n\n"
            "Pick the single most interesting item above and write the post about it."
            % news
        )
    else:
        focus = (
            "Write about this AI theme (turn it into one sharp, accurate insight — "
            "do NOT fabricate specific figures, dates, or quotes): %s" % topic
        )

    return (
        "%s\n\n"
        "Return ONLY valid JSON with these keys:\n"
        "  text         — the full LinkedIn post text incl. the 3-hashtag final line (string)\n"
        "  image_style  — always \"photo\" (string)\n"
        "  topic        — short topic label (string, 3-6 words)\n"
        "  image_prompt — REQUIRED: one vivid, cinematic, photorealistic SCENE for this\n"
        "                 post (30-60 words). No text, words, logos, charts, or UI screens.\n\n"
        "No markdown, no code fences, just raw JSON."
    ) % focus


def _extract_json(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.lstrip("`")
        if raw[:4].lower() == "json":
            raw = raw[4:]
        raw = raw.strip().rstrip("`").strip()
    # Fall back to slicing the outermost JSON object if there is extra prose.
    if not raw.startswith("{"):
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end + 1]
    return json.loads(raw)


def _resolve_provider():
    """Decide which text provider to use based on env + available keys."""
    if TEXT_PROVIDER == "claude":
        if not ANTHROPIC_API_KEY:
            sys.exit("TEXT_PROVIDER=claude but ANTHROPIC_API_KEY is not set.")
        return "claude"
    if TEXT_PROVIDER == "gemini":
        if not GOOGLE_API_KEY:
            sys.exit("TEXT_PROVIDER=gemini but GOOGLE_API_KEY is not set.")
        return "gemini"
    # auto
    if ANTHROPIC_API_KEY:
        return "claude"
    if GOOGLE_API_KEY:
        return "gemini"
    sys.exit(
        "No text provider configured. Add one to .env:\n"
        "  ANTHROPIC_API_KEY=sk-ant-...   (Claude Opus 4.8, best quality)\n"
        "  or GOOGLE_API_KEY=AIza.../AQ.  (Gemini, cheaper)\n"
        "Keys: https://console.anthropic.com/  |  https://aistudio.google.com/apikey"
    )


def generate_with_claude(topic, suggested_style):
    print("Using model: %s (Claude)" % CLAUDE_MODEL)
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 2048,
        "temperature": 0.85,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _build_user_prompt(topic, suggested_style)}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    resp = None
    for attempt in range(3):
        resp = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=90)
        if resp.status_code not in (429, 500, 503, 529):
            break
        if attempt < 2:
            wait = 5 * (attempt + 1)
            print("Claude busy (%s), retrying in %ss..." % (resp.status_code, wait))
            time.sleep(wait)
    if not resp.ok:
        try:
            msg = resp.json().get("error", {}).get("message") or resp.text
        except Exception:
            msg = resp.text
        sys.exit("Claude API error (%s): %s" % (resp.status_code, msg))

    data = resp.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    raw = "".join(parts)
    try:
        return _extract_json(raw)
    except json.JSONDecodeError as exc:
        sys.exit("Claude returned invalid JSON (%s). Try running again." % exc)


def generate_with_gemini(topic, suggested_style):
    if not (GOOGLE_API_KEY.startswith("AIza") or GOOGLE_API_KEY.startswith("AQ.")):
        sys.exit(
            "GOOGLE_API_KEY format not recognized (expected AIza... or AQ....).\n"
            "Create a key at: https://aistudio.google.com/apikey"
        )
    print("Using model: %s (Gemini)" % GEMINI_MODEL)
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": _build_user_prompt(topic, suggested_style)}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    resp = None
    for attempt in range(3):
        resp = requests.post(
            GEMINI_URL,
            headers={"Content-Type": "application/json", "x-goog-api-key": GOOGLE_API_KEY},
            json=payload,
            timeout=60,
        )
        if resp.status_code not in (429, 503):
            break
        if attempt < 2:
            wait = 5 * (attempt + 1)
            print("Gemini busy (%s), retrying in %ss..." % (resp.status_code, wait))
            time.sleep(wait)
    if not resp.ok:
        try:
            msg = resp.json().get("error", {}).get("message") or resp.text
        except Exception:
            msg = resp.text
        sys.exit("Gemini API error (%s): %s" % (resp.status_code, msg))

    candidate = resp.json()["candidates"][0]
    if candidate.get("finishReason") == "MAX_TOKENS":
        sys.exit("Gemini response truncated. Try again or increase maxOutputTokens.")
    raw = candidate["content"]["parts"][0]["text"]
    try:
        return _extract_json(raw)
    except json.JSONDecodeError as exc:
        sys.exit("Gemini returned invalid JSON (%s). Try running again." % exc)


def generate_post(topic, suggested_style="photo"):
    """Write a LinkedIn post using the configured provider. Returns dict."""
    provider = _resolve_provider()
    if provider == "claude":
        return generate_with_claude(topic, suggested_style)
    return generate_with_gemini(topic, suggested_style)


def main():
    # Load existing posts
    if os.path.exists(POSTS_FILE):
        with open(POSTS_FILE) as f:
            posts = json.load(f)
    else:
        posts = []

    topic = pick_topic(posts)
    print("Generating post about: %s" % topic)

    result = generate_post(topic, suggested_style="photo")

    image_prompt = (result.get("image_prompt") or "").strip()
    if not image_prompt:
        # Safety net: never ship a post without an image concept.
        image_prompt = (
            "A striking cinematic photograph that captures the idea of %s — a single "
            "hero subject, dramatic lighting, electric blue and violet glow, shallow "
            "depth of field. No text or screens." % result.get("topic", topic)
        )

    new_post = {
        "topic": result.get("topic", topic),
        "text": result["text"],
        "image_style": "photo",           # this edition is photo-only
        "image_prompt": image_prompt,
        "posted": False,
        "generated_at": time.strftime("%Y-%m-%d"),
    }

    posts.append(new_post)

    with open(POSTS_FILE, "w") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)

    remaining = sum(1 for p in posts if not p.get("posted"))
    print("Done. Queue now has %d unposted post(s)." % remaining)
    print("New post topic: %s" % new_post["topic"])


if __name__ == "__main__":
    main()
