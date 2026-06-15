#!/usr/bin/env python3
"""Build a preview email for the next LinkedIn post that will auto-publish.

Run by the preview-email GitHub Actions workflow each posting morning, BEFORE
the poster runs. It finds the post that will go out (the newest unposted item,
matching linkedin_poster's "publish newest" logic), renders its infographic to
a PNG, and writes an HTML email body. The workflow then emails it to you so you
can review/skip on your phone before publishing.

Outputs (to $GITHUB_OUTPUT): has_post, image_path, subject.
"""

import html
import json
import os

POSTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts.json")
EDIT_URL = "https://github.com/masterbalabhau/linkedin-autoposter/edit/main/posts.json"


def _set_output(key, value):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write("%s=%s\n" % (key, value))
    print("%s=%s" % (key, value))


def main():
    with open(POSTS_FILE) as f:
        posts = json.load(f)

    # The post that will publish = newest unposted (last in list with posted:false).
    item = next((p for p in reversed(posts) if not p.get("posted")), None)

    if not item:
        _set_output("has_post", "false")
        print("Queue empty - nothing will publish today.")
        return

    _set_output("has_post", "true")

    caption = item.get("text", "")
    topic = item.get("topic", "LinkedIn post")
    style = (item.get("image_style") or "").strip().lower()

    # Render the infographic to a PNG so it can be attached to the email.
    image_path = ""
    if style == "infographic" and item.get("infographic"):
        try:
            from infographic import render_infographic
            target = os.path.join(os.path.dirname(POSTS_FILE), "preview.png")
            if render_infographic(item["infographic"], target):
                image_path = target
        except Exception as exc:
            print("Infographic render failed: %s" % exc)

    _set_output("image_path", image_path)

    if style == "photo":
        img_note = (
            "<p><b>Image:</b> AI photo, generated at publish time.<br>"
            "<i>Prompt:</i> %s</p>" % html.escape(item.get("image_prompt", ""))
        )
    elif image_path:
        img_note = "<p><b>Image:</b> infographic (preview attached to this email).</p>"
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
