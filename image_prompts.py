"""Shared image style rules for LinkedIn post visuals (Imagen 4 Ultra)."""

import time

# "photo" is preferred — photorealistic scenes look far more professional on
# LinkedIn and avoid the gibberish-text problem of AI infographics.
IMAGE_STYLES = ("photo", "infographic")

STYLE_ASPECT_RATIO = {
    "photo": "4:3",
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
    "Ultra-realistic, high-resolution professional photograph for a Dubai/GCC "
    "Odoo ERP and AI consultancy brand. Cinematic natural lighting, shallow depth "
    "of field, premium corporate magazine quality, authentic modern Middle East "
    "business setting, real people and real objects. "
    "Absolutely NO text, NO words, NO logos, NO charts, NO UI screens, NO captions."
)

INFOGRAPHIC_SUFFIX = (
    "Clean premium flat-vector concept illustration for an Odoo ERP consultancy. "
    "Simple icon shapes, smooth gradients, generous whitespace, balanced composition. "
    "Palette: Odoo purple (#714B67), teal, navy, white. "
    "Absolutely NO readable text, NO letters, NO numbers, NO fake dashboards, NO UI."
)

NEGATIVE_HINT = (
    "Avoid: garbled text, fake words, watermark, distorted faces, extra fingers, "
    "cluttered layout, low resolution, generic stock-photo feel."
)


def normalize_style(style):
    style = (style or "").strip().lower()
    style = STYLE_ALIASES.get(style, style)
    return style if style in IMAGE_STYLES else "photo"


def pick_image_style(existing_posts):
    """Mostly designed infographics (~3:1), with an occasional photo for variety.

    Designed infographics read far better on LinkedIn (crisp text, on-brand) than
    generic AI photos, so they dominate. A photo appears roughly every 4th post,
    and never two photos in a row.
    """
    last_style = ""
    for post in reversed(existing_posts):
        style = post.get("image_style")
        if style:
            last_style = normalize_style(style)
            break

    # Never two photos back-to-back.
    if last_style == "photo":
        return "infographic"

    # Otherwise infographic ~3 of every 4 posts; photo on the 4th.
    day = int(time.strftime("%j"))
    return "photo" if day % 4 == 0 else "infographic"


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
