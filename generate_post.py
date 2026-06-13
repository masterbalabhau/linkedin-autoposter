#!/usr/bin/env python3
"""
Daily LinkedIn post generator — powered by Google Gemini 2.0 Flash.

Writes ONE new AI + Odoo post and appends it to posts.json.
Run via GitHub Actions (generate.yml) every day at 2 AM UTC.

Requires: GOOGLE_API_KEY env var (Google AI Studio key)
"""

import json
import os
import sys
import time
import requests

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

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

Write posts that:
- Are authoritative but conversational (1st person "we" for team, "I" for personal insights)
- Lead with a sharp hook (pain point, surprising fact, or bold statement)
- Give 3–5 specific, actionable insights using → bullet arrows
- Include a clear CTA (comment a keyword like "AUDIT", "SCALE", "CONNECT", etc.)
- End with 5–8 relevant hashtags on their own line
- Are 200–350 words total
- Are specific to UAE/GCC context where relevant
- Never mention competitor names negatively
- Sound like a senior Odoo architect with 10+ years experience, not a salesperson

Also provide a vivid image_prompt for Google Imagen 3 (portrait 4:5) that visually
represents the post topic in a premium, corporate, infographic style with navy/teal/white palette.
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


def generate_post(topic):
    """Call Gemini 2.0 Flash to write a LinkedIn post. Returns dict or None."""
    if not GOOGLE_API_KEY:
        sys.exit("GOOGLE_API_KEY is not set.")

    user_prompt = (
        "Write a LinkedIn post for iNOTRO Multiservices about: %s\n\n"
        "Return ONLY valid JSON with exactly these keys:\n"
        "  text         — the full LinkedIn post text (string)\n"
        "  image_prompt — Imagen 3 generation prompt (string, 50-100 words)\n"
        "  topic        — short topic label (string, 3-6 words)\n\n"
        "No markdown, no code fences, just raw JSON."
    ) % topic

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }

    resp = requests.post(
        GEMINI_URL,
        headers={"Content-Type": "application/json"},
        params={"key": GOOGLE_API_KEY},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    # Strip any accidental markdown fences
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)


def main():
    # Load existing posts
    if os.path.exists(POSTS_FILE):
        with open(POSTS_FILE) as f:
            posts = json.load(f)
    else:
        posts = []

    topic = pick_topic(posts)
    print("Generating post about: %s" % topic)

    result = generate_post(topic)

    new_post = {
        "topic": result.get("topic", topic),
        "text": result["text"],
        "image_prompt": result.get("image_prompt", ""),
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
