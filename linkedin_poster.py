#!/usr/bin/env python3
"""
LinkedIn daily auto-poster — personal profile + company page.

Modes:
  python linkedin_poster.py auth              # run ONCE: authorize + store tokens
  python linkedin_poster.py preview           # show the next queued post (no publish)
  python linkedin_poster.py post              # preview, then ask before publishing
  python linkedin_poster.py post --yes        # publish immediately (for cron)

Posts the next unposted item from posts.json, generates an AI image via Google
Imagen 3 (if GOOGLE_API_KEY is set and post has an image_prompt), uploads it to
LinkedIn, auto-refreshes the access token, and marks the item as posted.

Set COMPAY_ID in your .env to also post to your LinkedIn company page.
LinkedIn's API cannot save drafts — review happens locally before publish.

Setup secrets via a .env file (recommended) or environment variables:
  LI_CLIENT_ID=your_client_id
  LI_CLIENT_SECRET=your_client_secret
  COMPANY_ID=your_company_numeric_id   # optional: enables company page posting
  GOOGLE_API_KEY=your_google_ai_key    # optional: enables Imagen 3 image generation

LinkedIn app must have ALL products enabled (Developer Portal → Products):
  - Share on LinkedIn
  - Sign In with LinkedIn using OpenID Connect
  - Community Management API  ← required for company page posting

Scopes used: openid profile w_member_social w_organization_social r_organization_social

Requires: pip install -r requirements.txt
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from image_prompts import (
    STYLE_ASPECT_RATIO,
    build_imagen_prompt,
    normalize_style,
    pick_image_style,
)

# ----------------------------- CONFIG -----------------------------
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
CLIENT_ID = os.environ.get("LI_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("LI_CLIENT_SECRET", "")
COMPANY_ID = os.environ.get("COMPANY_ID", "")       # numeric org ID, e.g. "12345678"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "") # Google AI Studio key for Imagen
REDIRECT_URI = "http://localhost:8765/callback"  # must match app's Authorized redirect URL
# Include org scopes so one auth covers both personal + company
SCOPES = "openid profile w_member_social w_organization_social r_organization_social"
LINKEDIN_VERSION = "202605"   # YYYYMM. Bump to a recent month every few months.

# Google Imagen 4 family (Ultra = highest quality + 2K). Override via env.
#   imagen-4.0-ultra-generate-001  (best)
#   imagen-4.0-generate-001        (standard)
#   imagen-4.0-fast-generate-001   (cheap/fast)
IMAGEN_MODEL = os.environ.get("IMAGEN_MODEL", "").strip() or "imagen-4.0-ultra-generate-001"
IMAGE_SIZE = os.environ.get("IMAGE_SIZE", "").strip() or "2K"  # 1K or 2K (Ultra/Standard)

TOKENS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens.json")
POSTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts.json")
PREVIEW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "previews")

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
API = "https://api.linkedin.com"
# -------------------------------------------------------------------


# ===================== token storage helpers =====================
def load_tokens():
    if not os.path.exists(TOKENS_FILE):
        return {}
    with open(TOKENS_FILE) as f:
        return json.load(f)


def save_tokens(t):
    with open(TOKENS_FILE, "w") as f:
        json.dump(t, f, indent=2)
    os.chmod(TOKENS_FILE, 0o600)


# ===================== one-time OAuth (mode: auth) =====================
_received = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]
        if code:
            _received["code"] = code
            _received["state"] = params.get("state", [None])[0]
            body = b"<h2>Authorized. You can close this tab and return to the terminal.</h2>"
        elif error:
            _received["error"] = error
            _received["error_description"] = params.get("error_description", [""])[0]
            desc = _received["error_description"].encode()
            body = b"<h2>Authorization failed.</h2><p>" + desc + b"</p>"
        else:
            body = b"<h2>Invalid callback. Return to the terminal and run auth again.</h2>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def do_auth():
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("Set LI_CLIENT_ID and LI_CLIENT_SECRET environment variables first.")

    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "scope": SCOPES,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    print("Opening browser to authorize...\nIf it doesn't open, paste this URL:\n", url, "\n")
    webbrowser.open(url)

    _received.clear()
    server = HTTPServer(("127.0.0.1", 8765), _CallbackHandler)
    server.timeout = 1
    print("Waiting for callback on %s (2 min timeout)..." % REDIRECT_URI)
    deadline = time.time() + 120
    while time.time() < deadline:
        server.handle_request()
        if _received.get("error"):
            server.server_close()
            desc = _received.get("error_description", "")
            sys.exit("LinkedIn authorization error: %s —#%s" % (_received["error"], desc))
        if _received.get("code"):
            break
    server.server_close()

    if not _received.get("code"):
        sys.exit(
            "No authorization code received. Check that your LinkedIn app has this "
            "exact redirect URL: %s" % REDIRECT_URI
        )
    if _received.get("state") != state:
        sys.exit("State mismatch - aborting for safety.")
    code = _received["code"]

    r = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    r.raise_for_status()
    tok = r.json()

    me = requests.get(API + "/v2/userinfo",
                      headers={"Authorization": "Bearer " + tok["access_token"]})
    me.raise_for_status()
    personid = me.json()["sub"]

    now = int(time.time())
    tokens = {
        "access_token": tok["access_token"],
        "expires_at": now + int(tok.get("expires_in", 5184000)),
        "refresh_token": tok.get("refresh_token", ""),
        "refresh_expires_at": now + int(tok.get("refresh_token_expires_in", 31536000)),
        "person_urn": "urn:li:person:" + personid,
    }
    if COMPANY_ID:
        tokens["company_urn"] = "urn:li:organization:" + COMPANY_ID
    save_tokens(tokens)
    print("Success. Tokens saved to", TOKENS_FILE)
    print("Author URN:", "urn:li:person:" + personid)
    if COMPANY_ID:
        print("Company URN:", "urn:li:organization:" + COMPANY_ID)


# ===================== token refresh =====================
def valid_access_token():
    t = load_tokens()
    if not t:
        sys.exit("No tokens. Run:  python linkedin_poster.py auth")

    now = int(time.time())
    if now < t["expires_at"] - 86400:
        return t["access_token"], t["person_urn"], t.get("company_urn", "")

    if now >= t.get("refresh_expires_at", 0):
        sys.exit("Refresh token expired (365-day limit). Re-run:  python linkedin_poster.py auth")

    r = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": t["refresh_token"],
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    r.raise_for_status()
    nt = r.json()
    t["access_token"] = nt["access_token"]
    t["expires_at"] = now + int(nt.get("expires_in", 5184000))
    if nt.get("refresh_token"):
        t["refresh_token"] = nt["refresh_token"]
        t["refresh_expires_at"] = now + int(nt.get("refresh_token_expires_in", 31536000))
    save_tokens(t)
    return t["access_token"], t["person_urn"], t.get("company_urn", "")


# ===================== Imagen 4 generation =====================
def generate_image(prompt, post_id=0, style="photo"):
    """
    Call Google Imagen 4 (Ultra by default) via google-genai SDK.
    Returns a local temp file path on success, or None if unavailable/failed.
    """
    if not GOOGLE_API_KEY:
        return None
    if not prompt:
        return None

    style = normalize_style(style)
    full_prompt = build_imagen_prompt(prompt, style=style)
    aspect_ratio = STYLE_ASPECT_RATIO[style]

    print(
        "Generating image with %s (%s, %s, %s)..."
        % (IMAGEN_MODEL, style, aspect_ratio, IMAGE_SIZE)
    )
    try:
        from google import genai as _genai
        from google.genai import types as _gtypes
        client = _genai.Client(api_key=GOOGLE_API_KEY)
        cfg_kwargs = {
            "number_of_images": 1,
            "aspect_ratio": aspect_ratio,
            "output_mime_type": "image/png",
        }
        # image_size (2K) is only supported on Ultra/Standard, not Fast.
        if "fast" not in IMAGEN_MODEL:
            cfg_kwargs["image_size"] = IMAGE_SIZE
        try:
            response = client.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=full_prompt,
                config=_gtypes.GenerateImagesConfig(**cfg_kwargs),
            )
        except TypeError:
            # Older SDK without image_size support — retry without it.
            cfg_kwargs.pop("image_size", None)
            response = client.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=full_prompt,
                config=_gtypes.GenerateImagesConfig(**cfg_kwargs),
            )
        img_bytes = response.generated_images[0].image.image_bytes

        # Write to a temp file
        tmp = tempfile.NamedTemporaryFile(
            suffix=".png", prefix="li_post_%d_" % post_id, delete=False
        )
        tmp.write(img_bytes)
        tmp.close()
        print("Image generated:", tmp.name)
        return tmp.name
    except ImportError:
        print(
            "Warning: google-genai not installed — posting text only.\n"
            "  pip install -r requirements.txt"
        )
        return None
    except Exception as e:
        print("Warning: image generation failed (%s) — posting text only." % e)
        return None
def upload_image(token, owner_urn, path):
    headers = {
        "Authorization": "Bearer " + token,
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    init = requests.post(API + "/rest/images?action=initializeUpload",
                         headers=headers,
                         json={"initializeUploadRequest": {"owner": owner_urn}})
    init.raise_for_status()
    val = init.json()["value"]
    upload_url, image_urn = val["uploadUrl"], val["image"]

    with open(path, "rb") as f:
        put = requests.put(upload_url,
                           headers={"Authorization": "Bearer " + token},
                           data=f.read())
    put.raise_for_status()
    time.sleep(3)
    return image_urn


# ===================== text escaping for Posts API =====================
def escape_commentary(text):
    for ch in "\\(){}[]<>":
        text = text.replace(ch, "\\" + ch)
    return text


# ===================== queue + preview helpers =====================
def load_posts():
    if not os.path.exists(POSTS_FILE):
        sys.exit("No posts.json found next to this script.")
    with open(POSTS_FILE) as f:
        return json.load(f)


def save_posts(posts):
    with open(POSTS_FILE, "w") as f:
        json.dump(posts, f, indent=2)


def next_queue_item(posts):
    # Publish the NEWEST unposted item (last in the list) so the post that goes
    # out is the freshest one generated — not an older backlogged post.
    idx = next(
        (i for i in range(len(posts) - 1, -1, -1) if not posts[i].get("posted")),
        None,
    )
    if idx is None:
        return None, None
    return idx, posts[idx]


def render_infographic_image(item, idx):
    """Render a designed infographic slide (crisp text) to a temp PNG."""
    data = item.get("infographic")
    if not data:
        return None
    try:
        from infographic import render_infographic
    except ImportError:
        return None
    tmp = tempfile.NamedTemporaryFile(
        suffix=".png", prefix="li_infographic_%d_" % idx, delete=False
    )
    tmp.close()
    return render_infographic(data, tmp.name)


def resolve_image(item, idx=0):
    """
    Returns (path_or_None, status) where status is:
      "ready"     — local file found
      "generated" — produced a temp file (template or Imagen)
      "missing"   — path in JSON but file not on disk and generation unavailable
      "none"      — no image at all
    """
    # 1. Explicit file path in posts.json
    if item.get("image"):
        img_path = item["image"]
        if not os.path.isabs(img_path):
            img_path = os.path.join(os.path.dirname(POSTS_FILE), img_path)
        if os.path.exists(img_path):
            return img_path, "ready"
        # File path set but missing on disk — fall through to generation

    style = normalize_style(item.get("image_style") or pick_image_style([]))

    # 2a. Designed infographic (HTML template → crisp readable text)
    if style == "infographic" and item.get("infographic"):
        path = render_infographic_image(item, idx)
        if path:
            return path, "generated"
        # template unavailable — fall back to a photo via Imagen below

    # 2b. Photorealistic image via Imagen
    if GOOGLE_API_KEY:
        prompt = item.get("image_prompt") or (
            "A striking cinematic photograph evoking the frontier of artificial "
            "intelligence — glowing data center, dramatic blue-violet light, one "
            "hero subject, shallow depth of field"
        )
        photo_style = "photo" if style == "infographic" else style
        gen_path = generate_image(prompt, idx, style=photo_style)
        if gen_path:
            return gen_path, "generated"

    # 3. Nothing available
    if item.get("image"):
        return item["image"], "missing"
    return None, "none"


def abs_path(path):
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(os.path.dirname(POSTS_FILE), path))


def persist_preview_image(src_path, idx):
    """Copy generated image into project previews/ folder for easy viewing."""
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    dest = os.path.join(PREVIEW_DIR, "post_%d_preview.png" % idx)
    shutil.copy2(src_path, dest)
    return os.path.abspath(dest)


def open_image(path):
    """Open image in the default viewer (Preview on macOS)."""
    if not path or not os.path.exists(path):
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", path], check=False)
        elif sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
    except OSError:
        pass


def show_preview(idx, item, open_viewer=True):
    img_path, img_status = resolve_image(item, idx)
    divider = "=" * 60
    print(divider)
    print("PREVIEW — post #%d (not published yet)" % idx)
    print(divider)
    print(item["text"])
    print("-" * 60)
    if img_status == "none":
        print("Image: none (text-only post)")
    elif img_status in ("ready", "generated"):
        label = "Image (generated)" if img_status == "generated" else "Image"
        if img_status == "generated":
            img_path = persist_preview_image(img_path, idx)
        else:
            img_path = abs_path(img_path)
        print("%s: %s" % (label, img_path))
        if item.get("image_style"):
            print("Image style: %s" % item["image_style"])
        if item.get("alt"):
            print("Alt text: %s" % item["alt"])
        elif item.get("image_prompt"):
            print("Alt text: (auto from prompt)")
        if open_viewer:
            open_image(img_path)
            print("Opened in default viewer.")
    else:
        print("Image: %s (missing — will generate or post text only)" % img_path)
    print(divider)


def confirm_post():
    try:
        answer = input("Post to LinkedIn now? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


# ===================== create a single post =====================
def _publish_to_author(token, author_urn, item, idx=0, generated_img_path=None):
    """Post to one author (person or organization). Returns post URN or empty string."""
    body = {
        "author": author_urn,
        "commentary": escape_commentary(item["text"]),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    # Use pre-generated image path if provided (avoids calling Imagen twice)
    if generated_img_path and os.path.exists(generated_img_path):
        img_path, img_status = generated_img_path, "ready"
    else:
        img_path, img_status = resolve_image(item, idx)

    alt_text = item.get("alt") or item.get("image_prompt", "")[:200] or ""
    if img_status in ("ready", "generated"):
        image_urn = upload_image(token, author_urn, img_path)
        body["content"] = {"media": {"id": image_urn, "altText": alt_text}}
    elif img_status == "missing":
        print("Warning: image not found (%s) — posting text only." % img_path)

    headers = {
        "Authorization": "Bearer " + token,
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    r = requests.post(API + "/rest/posts", headers=headers, json=body)
    if r.status_code not in (200, 201):
        print("Post failed for %s (%s): %s" % (author_urn, r.status_code, r.text))
        return ""
    return r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id", "")


def publish_post(idx, item, posts):
    token, person_urn, company_urn = valid_access_token()

    # Produce the image ONCE (template infographic or Imagen photo) and reuse it
    # for both personal + company posts.
    gen_path = None
    if not item.get("image"):
        path, status = resolve_image(item, idx)
        if status == "generated":
            gen_path = path

    # Post to personal profile
    personal_urn = _publish_to_author(token, person_urn, item, idx, gen_path)
    if personal_urn:
        print("✒ Personal profile  ₒ  %s" % personal_urn)

    # Post to company page if configured
    company_post_urn = ""
    if company_urn:
        company_post_urn = _publish_to_author(token, company_urn, item, idx, gen_path)
        if company_post_urn:
            print("✒ Company page      →  %s" % company_post_urn)
    else:
        print("ℹ  No COMPANY_ID set — skipped company page.")

    # Clean up generated temp image
    if gen_path and os.path.exists(gen_path):
        try:
            os.unlink(gen_path)
        except OSError:
            pass

    posts[idx]["posted"] = True
    posts[idx]["posted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    posts[idx]["post_urn"] = personal_urn
    if company_post_urn:
        posts[idx]["company_post_urn"] = company_post_urn
    save_posts(posts)


def do_preview():
    posts = load_posts()
    idx, item = next_queue_item(posts)
    if item is None:
        print("Queue empty - nothing to preview.")
        return
    show_preview(idx, item, open_viewer="--no-open" not in sys.argv)


def do_post(skip_confirm=False):
    posts = load_posts()
    idx, item = next_queue_item(posts)
    if item is None:
        print("Queue empty - nothing to post today.")
        return

    show_preview(idx, item)
    if not skip_confirm and not confirm_post():
        print("Cancelled — post not published.")
        return

    publish_post(idx, item, posts)

    # Warn when queue is running low
    remaining = sum(1 for p in posts if not p.get("posted"))
    if remaining <= 3:
        print("\n⚠️  Only %d post(s) left in queue. Add more to posts.json soon." % remaining)


# ===================== entry point =====================
if __name__ == "__main__":
    args = sys.argv[1:]
    mode = args[0] if args else ""
    skip_confirm = "--yes" in args or "-y" in args

    if mode == "auth":
        do_auth()
    elif mode == "preview":
        do_preview()
    elif mode == "post":
        do_post(skip_confirm=skip_confirm)
    else:
        print(__doc__)
