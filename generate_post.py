#!/usr/bin/env python3
"""
Daily LinkedIn post generator.

Writes ONE new AI + Odoo post and appends it to posts.json.
Run via GitHub Actions (generate.yml) every day at 2 AM UTC.

Text provider (best quality first):
  - Claude Opus 4.8  (set ANTHROPIC_API_KEY) — default when available
  - Google Gemini    (set GOOGLE_API_KEY)    — fallback

Control with TEXT_PROVIDER=claude|gemini|auto (default: auto).
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

# Topics to rotate through so posts stay fresh and varied
TOPIC_POOL = [
    "UAE e-invoicing Phase 2 compliance and Odoo readiness",
    "AI agents automating Odoo workflows (sales, procurement, HR)",
    "Odoo 19 new features for GCC businesses",
    "QuickBooks vs Odoo for growing Dubai SMEs",
    "NetSuite vs Odoo total cost of ownership in UAE",
    "UAE payroll automation and WPS compliance in Odoo",
    "Odoo multi-company setup for GCC holding groups",
    "Python performance tips for Odoo developers",
    "Odoo.sh CI/CD pipelines for enterprise deployments",
    "AI-powered demand forecasting in Odoo inventory",
    "Data residency and PDPL compliance for UAE ERP systems",
    "Odoo OWL frontend framework for custom UI development",
    "Integration architecture: Odoo as hub for UAE businesses",
    "KSA ZATCA Phase 2 e-invoicing with Odoo",
    "Odoo Community vs Enterprise: what UAE CFOs need to know",
    "AI-driven financial close automation in Odoo accounting",
    "Custom Odoo module development best practices",
    "Odoo for Dubai e-commerce: Shopify and marketplace integration",
    "Real-time inventory visibility for UAE trading companies",
    "Odoo HR and leave management for UAE labour law compliance",
]

SYSTEM_PROMPT = """You are an expert LinkedIn content writer for iNOTRO Multiservices,
a boutique Odoo ERP and AI implementation firm based in Dubai, UAE.

Write SHORT, scroll-stopping posts in a mini-story style:
- HARD LIMIT: 50 words MAXIMUM for the whole post, NOT counting the hashtag line. Shorter is better. Never exceed 50 words.
- Open with a sharp one-line hook — a surprising fact, a relatable pain point, or a bold statement.
- Tell ONE tiny story or insight in 2–4 punchy sentences. One idea only. NO bullet lists, NO arrows, NO jargon walls.
- End with a short, soft CTA (e.g. 'Comment "AUDIT".' or 'DM "SCALE".').
- Then EXACTLY 3 relevant hashtags on their own final line.
- First person ("we" for the team, "I" for personal insight), confident and human — a senior Odoo architect, never salesy.
- Specific to UAE/GCC context where it fits. Never mention competitor names negatively.

Also provide an image for the post. Strongly PREFER image_style = "infographic"
(a crisp, designed graphic). Only use image_style = "photo" occasionally.

If image_style = "photo":
  Provide image_prompt: a SHORT visual concept (30-50 words) describing a REAL
  photographic SCENE for this Odoo ERP topic — people, objects, setting, lighting,
  mood, like a professional photographer. Do NOT mention text, words, labels, logos,
  dashboards, or UI screens. Use a realistic Dubai/GCC business setting.

If image_style = "infographic":
  Provide an "infographic" object rendered into a DESIGNED slide with real, crisp
  text (NOT an AI image). Choose ONE layout that best fits the topic and fill the
  matching fields. ALWAYS include: layout, title, subtitle, cta.
    layout   — "stats" | "comparison" | "list"  (PREFER "stats" when the topic has
               any numbers, percentages, savings, time, or growth — it is most eye-catching)
    title    — the headline
    subtitle — a supporting line
    cta      — call to action (e.g. 'Comment "AUDIT" to start')

  For layout = "stats" (the hero style — use most often):
    stats — array of 2-4 items, each: {value, label, caption}
            value   = a bold number/percentage/figure, e.g. "40%", "3x", "AED 0", "<2 wks"
            label   = a label for the figure
            caption = context for the figure
    Use realistic, defensible figures; never invent precise fake statistics —
    use directional ranges or well-known industry figures.

  For layout = "comparison":
    left  — {label, tone:"bad",  items:[strings]}   e.g. "Without Odoo"
    right — {label, tone:"good", items:[strings]}   e.g. "With Odoo"

  For layout = "list":
    points — array of 3-4 items, each: {emoji, heading, body}
             emoji=one relevant emoji, heading=a short heading, body=a sentence

  Write the infographic text as fully and informatively as the topic needs — do NOT
  cut it short. Keep it specific, accurate, and jargon-light.
"""

def pick_topic(existing_posts):
    """Pick a topic not recently used."""
    recent_texts = " ".join(
        p.get("text", "") for p in existing_posts[-20:]
    ).lower()
    for topic in TOPIC_POOL:
        # Use topic if key words not in recent 20 posts
        key = topic.split()[0].lower()
        if key not in recent_texts:
            return topic
    # Fallback: rotate by date
    day_of_year = int(time.strftime("%j"))
    return TOPIC_POOL[day_of_year % len(TOPIC_POOL)]


def _build_user_prompt(topic, suggested_style):
    return (
        "Write a SHORT LinkedIn post (50 words MAX, excluding hashtags) for "
        "iNOTRO Multiservices about: %s\n\n"
        "Return ONLY valid JSON with these keys:\n"
        "  text         — the full LinkedIn post text (string)\n"
        "  image_style  — \"photo\" or \"infographic\" (string)\n"
        "  topic        — short topic label (string, 3-6 words)\n"
        "  image_prompt — REQUIRED only if image_style is \"photo\": real scene, no text/UI\n"
        "  infographic  — REQUIRED only if image_style is \"infographic\": object with\n"
        "                 keys title, subtitle, points (3-4 of {emoji, heading, body}), cta\n\n"
        "Suggested image_style for this post: %s\n\n"
        "No markdown, no code fences, just raw JSON."
    ) % (topic, suggested_style)


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
    image_style = pick_image_style(posts)
    print("Generating post about: %s" % topic)

    result = generate_post(topic, suggested_style=image_style)

    new_post = {
        "topic": result.get("topic", topic),
        "text": result["text"],
        "image_style": result.get("image_style", image_style),
        "image_prompt": result.get("image_prompt", ""),
        "posted": False,
        "generated_at": time.strftime("%Y-%m-%d"),
    }
    if result.get("infographic"):
        new_post["infographic"] = result["infographic"]

    posts.append(new_post)

    with open(POSTS_FILE, "w") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)

    remaining = sum(1 for p in posts if not p.get("posted"))
    print("Done. Queue now has %d unposted post(s)." % remaining)
    print("New post topic: %s" % new_post["topic"])


if __name__ == "__main__":
    main()
