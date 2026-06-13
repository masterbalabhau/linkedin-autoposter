#!/usr/bin/env python3
"""
LinkedIn daily auto-poster (personal profile).

Modes:
  python linkedin_poster.py auth              # run ONCE: authorize + store tokens
  python linkedin_poster.py preview           # show the next queued post (no publish)
  python linkedin_poster.py post              # preview, then ask before publishing
  python linkedin_poster.py post --yes        # publish immediately (for cron)

Posts the next unposted item from posts.json, uploads its image if present,
auto-refreshes the access token, and marks the item as posted.

LinkedIn's API cannot save drafts — review happens locally before publish.

Setup secrets via a .env file (recommended) or environment variables:
  LI_CLIENT_ID=your_client_id
  LI_CLIENT_SECRET=your_client_secret

LinkedIn app must have BOTH products enabled (Developer Portal → Products):
  - Share on LinkedIn
  - Sign In with LinkedIn using OpenID Connect
Requires: pip install requests
"""

import json
import os
import sys
import time
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

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
REDIRECT_URI = "http://localhost:8765/callback"   # must match the app's Authorized redirect URL
SCOPES = "openid profile w_member_social"
LINKEDIN_VERSION = "202605"   # YYYYMM. Bump to a recent month every few months.

TOKENS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens.json")
POSTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts.json")

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
    os.chmod(TOKENS_FILE, 0o600)  # keep secrets readable only by you


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
        pass  # silence the server


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
            sys.exit("LinkedIn authorization error: %s — %s" % (_received["error"], desc))
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

    # exchange code for tokens
    r = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    r.raise_for_status()
    tok = r.json()

    # fetch the member's id (the "sub" field) to build the author URN
    me = requests.get(API + "/v2/userinfo",
                      headers={"Authorization": "Bearer " + tok["access_token"]})
    me.raise_for_status()
    person_id = me.json()["sub"]

    now = int(time.time())
    save_tokens({
        "access_token": tok["access_token"],
        "expires_at": now + int(tok.get("expires_in", 5184000)),
        "refresh_token": tok.get("refresh_token", ""),
        "refresh_expires_at": now + int(tok.get("refresh_token_expires_in", 31536000)),
        "person_urn": "urn:li:person:" + person_id,
    })
    print("Success. Tokens saved to", TOKENS_FILE)
    print("Author URN:", "urn:li:person:" + person_id)


# ===================== token refresh =====================
def valid_access_token():
    t = load_tokens()
    if not t:
        sys.exit("No tokens. Run:  python linkedin_poster.py auth")

    now = int(time.time())
    # refresh if the access token expires within the next 24h
    if now < t["expires_at"] - 86400:
        return t["access_token"], t["person_urn"]

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
    return t["access_token"], t["person_urn"]


# ===================== image upload =====================
def upload_image(token, person_urn, path):
    headers = {
        "Authorization": "Bearer " + token,
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    init = requests.post(API + "/rest/images?action=initializeUpload",
                         headers=headers,
                         json={"initializeUploadRequest": {"owner": person_urn}})
    init.raise_for_status()
    val = init.json()["value"]
    upload_url, image_urn = val["uploadUrl"], val["image"]

    with open(path, "rb") as f:
        put = requests.put(upload_url,
                           headers={"Authorization": "Bearer " + token},
                           data=f.read())
    put.raise_for_status()
    time.sleep(3)  # give LinkedIn a moment to process the asset
    return image_urn


# ===================== text escaping for Posts API =====================
def escape_commentary(text):
    # The Posts API "commentary" treats these as reserved; escaping renders
    # them normally and prevents 422 errors. '#' is left alone so hashtags work.
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
    idx = next((i for i, p in enumerate(posts) if not p.get("posted")), None)
    if idx is None:
        return None, None
    return idx, posts[idx]


def resolve_image(item):
    if not item.get("image"):
        return None, "none"
    img_path = item["image"]
    if not os.path.isabs(img_path):
        img_path = os.path.join(os.path.dirname(POSTS_FILE), img_path)
    if os.path.exists(img_path):
        return img_path, "ready"
    return img_path, "missing"


def show_preview(idx, item):
    img_path, img_status = resolve_image(item)
    divider = "=" * 60
    print(divider)
    print("PREVIEW — post #%d (not published yet)" % idx)
    print(divider)
    print(item["text"])
    print("-" * 60)
    if img_status == "none":
        print("Image: none (text-only post)")
    elif img_status == "ready":
        print("Image: %s" % img_path)
        if item.get("alt"):
            print("Alt text: %s" % item["alt"])
    else:
        print("Image: %s (missing — will post text only)" % img_path)
    print(divider)


def confirm_post():
    try:
        answer = input("Post to LinkedIn now? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


# ===================== create the post =====================
def publish_post(idx, item, posts):
    token, person_urn = valid_access_token()

    body = {
        "author": person_urn,
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

    img_path, img_status = resolve_image(item)
    if img_status == "ready":
        image_urn = upload_image(token, person_urn, img_path)
        body["content"] = {"media": {"id": image_urn, "altText": item.get("alt", "")}}
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
        sys.exit("Post failed (%s): %s" % (r.status_code, r.text))

    post_urn = r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id", "")
    posts[idx]["posted"] = True
    posts[idx]["posted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    posts[idx]["post_urn"] = post_urn
    save_posts(posts)
    print("Posted item %d  ->  %s" % (idx, post_urn))


def do_preview():
    posts = load_posts()
    idx, item = next_queue_item(posts)
    if item is None:
        print("Queue empty - nothing to preview.")
        return
    show_preview(idx, item)


def do_post(skip_confirm=False):
    posts = load_posts()
    idx, item = next_queue_item(posts)
    if item is None:
        print("Queue empty - nothing to post today.")
        return

    show_preview(idx, item)
    if not skip_confirm and not confirm_post():
        print("Cancelled — nothing was posted.")
        return

    publish_post(idx, item, posts)


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
