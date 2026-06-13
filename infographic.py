"""Render branded LinkedIn infographics from structured content.

Unlike text-to-image models (which garble text), this builds a real HTML/CSS
layout and screenshots it with headless Chromium (Playwright) — so headings and
body copy are always crisp and readable, like a hand-designed Canva slide.
"""

import html
import os

# LinkedIn portrait 4:5 (1080x1350) rendered at 2x for crispness.
CANVAS_W = 1080
CANVAS_H = 1350
SCALE = 2

BRAND_NAME = os.environ.get("BRAND_NAME", "iNOTRO Multiservices")
BRAND_TAGLINE = os.environ.get("BRAND_TAGLINE", "Odoo ERP & AI · Dubai, UAE")

# Vibrant, attractive accent palette assigned per card (cycles).
ACCENTS = [
    ("#6C2BD9", "#F3EEFF"),   # violet
    ("#0F9D8C", "#E6F7F4"),   # teal
    ("#2563EB", "#E8F0FE"),   # blue
    ("#E8590C", "#FFF1E6"),   # orange
    ("#DB2777", "#FDE8F2"),   # pink
    ("#0891B2", "#E3F6FB"),   # cyan
]

DEFAULT_EMOJI = ["🚀", "⚙️", "📈", "🛡️", "🤖", "💡", "🔗", "✅"]


def _esc(text):
    return html.escape(str(text or "").strip())


def _highlight_title(title):
    """Color the last 1-2 words of the title with the brand accent."""
    title = _esc(title)
    words = title.split()
    if len(words) <= 2:
        return '<span class="accentText">%s</span>' % title
    head = " ".join(words[:-2])
    tail = " ".join(words[-2:])
    return '%s <span class="accentText">%s</span>' % (head, tail)


def build_html(data):
    """data: {title, subtitle, points:[{emoji,heading,body}], cta, footer_note}"""
    title = data.get("title") or "Odoo ERP Insights"
    subtitle = data.get("subtitle") or ""
    points = data.get("points") or []
    cta = data.get("cta") or ""

    cards = []
    for i, p in enumerate(points[:5]):
        accent, soft = ACCENTS[i % len(ACCENTS)]
        emoji = (p.get("emoji") or DEFAULT_EMOJI[i % len(DEFAULT_EMOJI)]).strip()
        heading = _esc(p.get("heading"))
        body = _esc(p.get("body"))
        cards.append(
            """
            <div class="card" style="--accent:{accent}; --soft:{soft};">
              <div class="badge">{emoji}</div>
              <div class="cardText">
                <div class="cardHeading">{heading}</div>
                <div class="cardBody">{body}</div>
              </div>
            </div>
            """.format(accent=accent, soft=soft, emoji=emoji, heading=heading, body=body)
        )

    cta_html = (
        '<div class="cta"><span class="ctaDot"></span>%s</div>' % _esc(cta)
        if cta else ""
    )
    subtitle_html = '<div class="subtitle">%s</div>' % _esc(subtitle) if subtitle else ""

    return """<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{W}px; height:{H}px; }}
  body {{
    font-family:'Inter','Helvetica Neue','Segoe UI',Arial,sans-serif;
    background:
      radial-gradient(1200px 600px at 110% -10%, #EDE9FE 0%, rgba(237,233,254,0) 55%),
      radial-gradient(900px 500px at -10% 110%, #DCFCE7 0%, rgba(220,252,231,0) 50%),
      #FBFCFE;
    color:#0F172A; padding:72px 64px; position:relative; overflow:hidden;
  }}
  .topbar {{ display:flex; align-items:center; gap:14px; margin-bottom:40px; }}
  .logoMark {{
    width:46px; height:46px; border-radius:12px;
    background:linear-gradient(135deg,#6C2BD9,#0F9D8C);
    display:flex; align-items:center; justify-content:center;
    color:#fff; font-weight:800; font-size:22px;
  }}
  .brand {{ font-weight:800; font-size:22px; letter-spacing:-0.2px; }}
  .brandSub {{ font-size:14px; color:#64748B; font-weight:600; }}
  .title {{ font-size:62px; line-height:1.05; font-weight:800; letter-spacing:-1.5px; margin-bottom:18px; }}
  .accentText {{
    background:linear-gradient(135deg,#6C2BD9,#0F9D8C);
    -webkit-background-clip:text; background-clip:text; color:transparent;
  }}
  .subtitle {{ font-size:24px; color:#475569; font-weight:500; margin-bottom:40px; max-width:90%; }}
  .cards {{ display:flex; flex-direction:column; gap:22px; }}
  .card {{
    display:flex; gap:22px; align-items:flex-start;
    background:#FFFFFF; border:1px solid #EEF1F6; border-left:7px solid var(--accent);
    border-radius:20px; padding:26px 28px;
    box-shadow:0 10px 30px rgba(15,23,42,0.05);
  }}
  .badge {{
    flex:0 0 auto; width:64px; height:64px; border-radius:16px;
    background:var(--soft); display:flex; align-items:center; justify-content:center;
    font-size:34px;
  }}
  .cardHeading {{ font-size:27px; font-weight:800; letter-spacing:-0.4px; margin-bottom:6px; }}
  .cardBody {{ font-size:20px; line-height:1.45; color:#475569; font-weight:500; }}
  .cta {{
    margin-top:38px; display:inline-flex; align-items:center; gap:12px;
    background:linear-gradient(135deg,#6C2BD9,#0F9D8C); color:#fff;
    font-size:22px; font-weight:700; padding:18px 28px; border-radius:16px;
  }}
  .ctaDot {{ width:12px; height:12px; border-radius:50%; background:#FACC15; }}
  .footer {{
    position:absolute; left:64px; right:64px; bottom:40px;
    display:flex; justify-content:space-between; align-items:center;
    font-size:15px; color:#94A3B8; font-weight:600;
    border-top:1px solid #EEF1F6; padding-top:20px;
  }}
</style></head>
<body>
  <div class="topbar">
    <div class="logoMark">{initial}</div>
    <div>
      <div class="brand">{brand}</div>
      <div class="brandSub">{tagline}</div>
    </div>
  </div>
  <div class="title">{title_html}</div>
  {subtitle_html}
  <div class="cards">{cards}</div>
  {cta_html}
  <div class="footer"><span>{brand}</span><span>{tagline}</span></div>
</body></html>""".format(
        W=CANVAS_W,
        H=CANVAS_H,
        initial=_esc(BRAND_NAME[:1]),
        brand=_esc(BRAND_NAME),
        tagline=_esc(BRAND_TAGLINE),
        title_html=_highlight_title(title),
        subtitle_html=subtitle_html,
        cards="".join(cards),
        cta_html=cta_html,
    )


def render_infographic(data, out_path):
    """Render structured data to a PNG. Returns out_path, or None if unavailable."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Warning: playwright not installed — cannot render infographic.\n"
            "  pip install -r requirements.txt && playwright install chromium"
        )
        return None

    html_str = build_html(data)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(
                viewport={"width": CANVAS_W, "height": CANVAS_H},
                device_scale_factor=SCALE,
            )
            page.set_content(html_str, wait_until="networkidle")
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            page.screenshot(path=out_path, clip={
                "x": 0, "y": 0, "width": CANVAS_W, "height": CANVAS_H,
            })
            browser.close()
        return out_path
    except Exception as e:
        print("Warning: infographic render failed (%s)." % e)
        return None
