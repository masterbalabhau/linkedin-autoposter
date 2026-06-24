"""Shared image style rules for LinkedIn post visuals (Imagen 4 Ultra)."""

import os

# This edition posts ONE photorealistic AI image per post (no text/infographics).
IMAGE_STYLES = ("photo", "infographic")

# Portrait 3:4 fills more of the LinkedIn feed and reads like a magazine cover.
# Override with IMAGE_ASPECT (Imagen supports 1:1, 3:4, 4:3, 9:16, 16:9).
_PHOTO_ASPECT = os.environ.get("IMAGE_ASPECT", "").strip() or "3:4"
STYLE_ASPECT_RATIO = {
    "photo": _PHOTO_ASPECT,
    "infographic": "4:3",
}

# Map legacy style names to the current set.
STYLE_ALIASES = {
    "workspace": "photo",
    "office": "photo",
    "realistic": "photo",
    "vector": "infographic",
}

PHOTO_SUFFIX = (
    "Hyperrealistic editorial photograph, shot for the cover of WIRED or MIT "
    "Technology Review. One strong hero subject, bold cinematic composition with "
    "negative space, dramatic volumetric lighting and gentle lens flare, shallow "
    "depth of field on an 85mm prime lens, razor-sharp focus, ultra-fine photoreal "
    "texture and micro-detail, high dynamic range, subtle atmospheric haze and fine "
    "dust in the light. Sophisticated futuristic color grade: deep blacks, electric "
    "blue and violet glow with warm amber accents. Awe-inspiring, intelligent, "
    "premium mood — emphatically NOT generic stock photography. "
    "Absolutely NO text, NO words, NO letters, NO numbers, NO logos, NO charts, "
    "NO graphs, NO UI screens, NO captions, NO watermark."
)

INFOGRAPHIC_SUFFIX = (
    "Clean premium flat-vector concept illustration for a global AI/technology "
    "publication. Simple icon shapes (neural nets, chips, robots, nodes), smooth "
    "gradients, generous whitespace, balanced composition. "
    "Palette: electric violet (#6C2BD9), teal (#0F9D8C), deep navy, white. "
    "Absolutely NO readable text, NO letters, NO numbers, NO fake dashboards, NO UI."
)

NEGATIVE_HINT = (
    "Avoid: garbled text, fake words, watermark, distorted faces, extra or fused "
    "fingers, malformed hands, cluttered composition, flat or dull lighting, low "
    "resolution, oversaturation, plastic CGI look, cheesy corporate stock-photo feel."
)


def normalize_style(style):
    style = (style or "").strip().lower()
    style = STYLE_ALIASES.get(style, style)
    return style if style in IMAGE_STYLES else "photo"


def pick_image_style(existing_posts):
    """Every post is a pure photorealistic AI image (no text/infographics)."""
    return "photo"


def build_imagen_prompt(concept, style="photo"):
    """Wrap a topic concept with style guardrails that prevent gibberish UI mockups."""
    concept = (concept or "").strip()
    if not concept:
        concept = "Odoo ERP digital transformation for a UAE business"

    style = normalize_style(style)
    suffix = PHOTO_SUFFIX if style == "photo" else INFOGRAPHIC_SUFFIX

    return (
        "%s %s %s"
        % (
            ("Scene: " + concept + ".") if style == "photo" else ("Concept: " + concept + "."),
            suffix,
            NEGATIVE_HINT,
        )
    )
