#!/usr/bin/env python3
"""Build a preview email for the next LinkedIn post that will auto-publish.

Run by the preview-email GitHub Actions workflow each posting morning, BEFORE
the poster runs. It finds the post that will go out (the newest unposted item,
matching linkedin_poster's "publish newest" logic), GENERATES its image, pins
that exact image onto the post (so the poster reuses it instead of making a new
one), writes an HTML email body, and outputs the image path so the workflow can
attach it. The workflow then commits the image + queue update and emails you the
preview so you can review/skip on your phone before publishing.

Outputs (to $GITHUB_OUTPUT): has_post, image_path, subject.
"""

import html
import json
import os
import re
import shutil

POSTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts.json")
IMAGES_DIR = os.path.join(os.path.dirname(POSTS_FILE), "post_images")
EDIT_URL = "https://github.com/masterbalabhau/linkedin-autoposter/edit/main/posts.json"


def _set_output(key, value):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write("%s=%s\n" % (key, value))
    print("%s=%s" % (key, value))


def _slug(text):
    text = re.sub(r"[^a-z0-9]+", "-", (text or "post").lower()).strip("-")
    return (text or "post")[:50]


def _save_posts(posts):
    with open(POSTS_FILE, "w") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)


def _ensure_image(item, idx, posts):
    """Make sure the post has a committed image file; return its repo-relative path.

    Reuses an already-pinned image, renders an infographic, or generates the
    photo via Imagen — then pins it onto the post so the poster uses the SAME
    image. Returns "" if no image could be produced (e.g. no API key).
    """
    # 1. Already pinned and on disk -> reuse it.
    existing = item.get("image")
    if existing:
        abs_existing = existing if os.path.isabs(existing) else os.path.join(
            os.path.dirname(POSTS_FILE), existing)
        if os.path.exists(abs_existing):
            return existing

    os.makedirs(IMAGES_DIR, exist_ok=True)
    style = (item.get("image_style") or "").strip().lower()
    stamp = item.get("generated_at", "post")
    base = "%s-%s.png" % (stamp, _slug(item.get("topic", "")))
    target = os.path.join(IMAGES_DIR, base)
    rel = os.path.join("post_images", base)

    # 2. Infographic -> render the designed slide.
    if style == "infographic" and item.get("infographic"):
        try:
            from infographic import render_infographic
            if render_infographic(item["infographic"], target):
                posts[idx]["image"] = rel
                _save_posts(posts)
                return rel
        except Exception as exc:
            print("Infographic render failed: %s" % exc)
        return ""

    # 3. Photo -> generate the Imagen image (the exact one that will publish).
    try:
        from linkedin_poster import generate_image
    except Exception as exc:
        print("Could not import image generator: %s" % exc)
        return ""

    prompt = item.get("image_prompt", "")
    gen = generate_image(prompt, post_id=idx, style="photo")
    if gen and os.path.exists(gen):
        shutil.copy(gen, target)
        try:
            os.unlink(gen)
        except OSError:
            pass
        posts[idx]["image"] = rel
        _save_posts(posts)
        return rel

    print("Image generation unavailable — preview will show the prompt only.")
    return ""


def main():
    with open(POSTS_FILE) as f:
        posts = json.load(f)

    # The post that will publish = newest unposted (last in list with posted:false).
    idx = next((i for i in range(len(posts) - 1, -1, -1)
                if not posts[i].get("posted")), None)

    if idx is None:
        _set_output("has_post", "false")
        print("Queue empty - nothing will publish today.")
        return

    item = posts[idx]
    _set_output("has_post", "true")

    caption = item.get("text", "")
    topic = item.get("topic", "LinkedIn post")
    style = (item.get("image_style") or "").strip().lower()

    image_path = _ensure_image(item, idx, posts)
    _set_output("image_path", image_path)

    if image_path:
        img_note = (
            "<p><b>Image:</b> attached below — this exact image will publish "
            "with the post.</p>"
        )
    elif style == "photo":
        img_note = (
            "<p><b>Image:</b> AI photo, generated at publish time.<br>"
            "<i>Prompt:</i> %s</p>" % html.escape(item.get("image_prompt", ""))
        )
    else:
        img_note = "<p><b>Image:</b> %s</p>" % html.escape(style or "none")

    body = """<div style="font-family:Arial,Helvetica,sans-serif;color:#0F172A;max-width:640px">
  <h2 style="margin:0 0 4px">Today's LinkedIn post</h2>
  <p style="color:#64748B;margin:0 0 16px">Publishes automatically around 9:00 AM IST.</p>
  <p style="margin:0 0 6px"><b>Topic:</b> %s</p>
  <div style="white-space:pre-wrap;border-left:4px solid #6C2BD9;padding:8px 0 8px 14px;background:#FAF8FF;font-size:15px;line-height:1.5">%s</div>
  %s
  <p style="margin-top:18px">To <b>skip or edit</b> this before it posts, open
  <a href="%s">posts.json on GitHub</a> — set the last entry's <code>"posted"</code>
  to <code>true</code> to skip it, or change its <code>"text"</code>. Do this before 9:00 AM IST.</p>
</div>""" % (
        html.escape(topic),
        html.escape(caption),
        img_note,
        EDIT_URL,
    )

    with open(os.path.join(os.path.dirname(POSTS_FILE), "preview_email.html"), "w") as f:
        f.write(body)

    _set_output("subject", "LinkedIn preview - %s" % topic)
    print("Prepared preview email for: %s" % topic)


if __name__ == "__main__":
    main()
