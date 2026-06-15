"""Render branded, attractive LinkedIn infographics from structured content.

Unlike text-to-image models (which garble text), this builds a real HTML/CSS
layout and screenshots it with headless Chromium (Playwright) — so every heading,
number and label is crisp and readable, like a hand-designed Canva/Figma slide.

Supports several layouts so posts stay varied (not the same card list every day):
  - "stats"      → big bold numbers / percentages (the hero, eye-catching style)
  - "comparison" → two columns (e.g. WITHOUT vs WITH, Odoo vs Other)
  - "list"       → upgraded colourful key-points cards
The renderer is forgiving: if a layout's data is missing it falls back gracefully.
"""

import html
import os

# LinkedIn portrait 4:5 (1080x1350) rendered at 2x for crispness.
CANVAS_W = 1080
CANVAS_H = 1350
SCALE = 2

BRAND_NAME = os.environ.get("BRAND_NAME", "iNOTRO Multiservices")
BRAND_TAGLINE = os.environ.get("BRAND_TAGLINE", "Odoo ERP & AI · Dubai, UAE")

# Brand gradient + vibrant per-item accent palette (cycles).
GRAD_A = "#6C2BD9"   # violet
GRAD_B = "#0F9D8C"   # teal
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
    """Color the last 1-2 words of the title with the brand gradient."""
    title = _esc(title)
    words = title.split()
    if not words:
        return ""
    if len(words) <= 2:
        return '<span class="accentText">%s</span>' % title
    head = " ".join(words[:-2])
    tail = " ".join(words[-2:])
    return '%s <span class="accentText">%s</span>' % (head, tail)


# ----------------------------- shared chrome -----------------------------
def _header():
    return """
  <div class="topbar">
    <div class="logoMark">{initial}</div>
    <div>
      <div class="brand">{brand}</div>
      <div class="brandSub">{tagline}</div>
    </div>
    <div class="topTag">Odoo · AI</div>
  </div>""".format(
        initial=_esc(BRAND_NAME[:1]),
        brand=_esc(BRAND_NAME),
        tagline=_esc(BRAND_TAGLINE),
    )


def _footer():
    return (
        '<div class="footer"><span>{brand}</span>'
        '<span>{tagline}</span></div>'
    ).format(brand=_esc(BRAND_NAME), tagline=_esc(BRAND_TAGLINE))


def _cta(cta):
    if not cta:
        return ""
    return '<div class="cta"><span class="ctaDot"></span>%s</div>' % _esc(cta)


def _title_block(data):
    title = data.get("title") or "Odoo ERP Insights"
    subtitle = data.get("subtitle") or ""
    sub = '<div class="subtitle">%s</div>' % _esc(subtitle) if subtitle else ""
    return '<div class="title">%s</div>%s' % (_highlight_title(title), sub)


# ----------------------------- layouts -----------------------------
def _render_stats(data):
    """Big bold numbers. data['stats'] = [{value,label,caption?}]."""
    stats = data.get("stats") or []
    cards = []
    for i, s in enumerate(stats[:4]):
        accent, soft = ACCENTS[i % len(ACCENTS)]
        value = _esc(s.get("value"))
        label = _esc(s.get("label"))
        caption = _esc(s.get("caption"))
        caption_html = (
            '<div class="statCaption">%s</div>' % caption if caption else ""
        )
        cards.append(
            """
            <div class="statCard" style="--accent:{accent}; --soft:{soft};">
              <div class="statValue">{value}</div>
              <div class="statLabel">{label}</div>
              {caption_html}
            </div>""".format(
                accent=accent, soft=soft, value=value,
                label=label, caption_html=caption_html,
            )
        )
    grid_class = "statGrid two" if len(cards) <= 2 else "statGrid"
    body = '<div class="%s">%s</div>' % (grid_class, "".join(cards))
    return body


def _render_comparison(data):
    """Two columns. data['left'] / data['right'] = {label, items:[...] , tone?}."""
    def column(col, default_tone):
        col = col or {}
        tone = (col.get("tone") or default_tone).lower()
        label = _esc(col.get("label"))
        items = col.get("items") or []
        icon = "✓" if tone == "good" else ("✕" if tone == "bad" else "•")
        rows = "".join(
            '<li><span class="ci">%s</span>%s</li>' % (icon, _esc(it))
            for it in items[:5]
        )
        return (
            '<div class="compCol {tone}">'
            '<div class="compHead">{label}</div>'
            '<ul class="compList">{rows}</ul></div>'
        ).format(tone=tone, label=label, rows=rows)

    left = column(data.get("left"), "bad")
    right = column(data.get("right"), "good")
    return '<div class="compWrap">%s<div class="compVs">VS</div>%s</div>' % (
        left, right,
    )


def _render_list(data):
    """Upgraded colourful key-points cards."""
    points = data.get("points") or []
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
            </div>""".format(
                accent=accent, soft=soft, emoji=emoji,
                heading=heading, body=body,
            )
        )
    return '<div class="cards">%s</div>' % "".join(cards)


LAYOUTS = {
    "stats": _render_stats,
    "comparison": _render_comparison,
    "list": _render_list,
}


def _choose_layout(data):
    layout = (data.get("layout") or "").strip().lower()
    if layout in LAYOUTS:
        # Guard: if the chosen layout has no data, fall back sensibly.
        if layout == "stats" and not data.get("stats"):
            pass
        elif layout == "comparison" and not (data.get("left") or data.get("right")):
            pass
        else:
            return layout
    if data.get("stats"):
        return "stats"
    if data.get("left") or data.get("right"):
        return "comparison"
    return "list"


def build_html(data):
    """data: {layout, title, subtitle, cta, + layout-specific fields}."""
    layout = _choose_layout(data)
    body_inner = LAYOUTS[layout](data)

    return """<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{W}px; }}
  body {{ min-height:{H}px; }}
  body {{
    font-family:'Inter','Helvetica Neue','Segoe UI',Arial,sans-serif;
    background:
      radial-gradient(1200px 620px at 112% -12%, #EDE9FE 0%, rgba(237,233,254,0) 55%),
      radial-gradient(950px 520px at -12% 112%, #DCFCE7 0%, rgba(220,252,231,0) 52%),
      #FBFCFE;
    color:#0F172A; padding:64px 60px 56px; position:relative; overflow:hidden;
    display:flex; flex-direction:column;
  }}
  .stageMain {{ flex:1; display:flex; flex-direction:column; min-height:0; }}
  body::before {{
    content:""; position:absolute; top:-140px; right:-120px;
    width:380px; height:380px; border-radius:50%;
    background:linear-gradient(135deg,{ga},{gb}); opacity:.10; filter:blur(8px);
  }}
  .topbar {{ display:flex; align-items:center; gap:16px; margin-bottom:34px; }}
  .logoMark {{
    width:52px; height:52px; border-radius:14px;
    background:linear-gradient(135deg,{ga},{gb});
    display:flex; align-items:center; justify-content:center;
    color:#fff; font-weight:800; font-size:25px;
    box-shadow:0 8px 20px rgba(108,43,217,0.28);
  }}
  .brand {{ font-weight:800; font-size:23px; letter-spacing:-0.2px; }}
  .brandSub {{ font-size:14px; color:#64748B; font-weight:600; }}
  .topTag {{
    margin-left:auto; font-size:14px; font-weight:800; letter-spacing:.4px;
    color:{ga}; background:#F3EEFF; border:1px solid #E6DBFB;
    padding:9px 16px; border-radius:999px;
  }}
  .title {{ font-size:62px; line-height:1.04; font-weight:800; letter-spacing:-1.6px; margin-bottom:16px; }}
  .accentText {{
    background:linear-gradient(135deg,{ga},{gb});
    -webkit-background-clip:text; background-clip:text; color:transparent;
  }}
  .subtitle {{ font-size:24px; color:#475569; font-weight:500; margin-bottom:38px; max-width:92%; }}

  /* ---- stats ---- */
  .statGrid {{ flex:1; display:grid; grid-template-columns:1fr 1fr; grid-auto-rows:1fr; gap:26px; min-height:0; }}
  .statGrid.two {{ grid-template-columns:1fr 1fr; grid-auto-rows:1fr; }}
  .statCard {{
    background:#FFFFFF; border:1px solid #EEF1F6; border-top:8px solid var(--accent);
    border-radius:24px; padding:40px 34px; box-shadow:0 14px 36px rgba(15,23,42,0.06);
    display:flex; flex-direction:column; justify-content:center;
  }}
  .statValue {{
    font-size:84px; line-height:1; font-weight:800; letter-spacing:-2.5px;
    background:linear-gradient(135deg,var(--accent),{gb});
    -webkit-background-clip:text; background-clip:text; color:transparent;
  }}
  .statLabel {{ font-size:26px; font-weight:800; letter-spacing:-0.4px; margin-top:14px; }}
  .statCaption {{ font-size:19px; color:#64748B; font-weight:500; line-height:1.4; margin-top:8px; }}

  /* ---- comparison ---- */
  .compWrap {{ flex:1; display:flex; align-items:stretch; gap:0; position:relative; min-height:0; }}
  .compCol {{
    flex:1; background:#FFFFFF; border:1px solid #EEF1F6; border-radius:24px;
    padding:36px 30px; box-shadow:0 14px 36px rgba(15,23,42,0.06);
    display:flex; flex-direction:column;
  }}
  .compList {{ flex:1; justify-content:center; }}
  .compCol.bad {{ border-top:8px solid #EF4444; }}
  .compCol.good {{ border-top:8px solid #10B981; }}
  .compCol.neutral {{ border-top:8px solid {ga}; }}
  .compVs {{
    align-self:center; margin:0 -14px; z-index:2;
    width:66px; height:66px; border-radius:50%;
    background:linear-gradient(135deg,{ga},{gb}); color:#fff;
    display:flex; align-items:center; justify-content:center;
    font-weight:800; font-size:22px; box-shadow:0 10px 24px rgba(15,23,42,0.18);
  }}
  .compHead {{ font-size:27px; font-weight:800; letter-spacing:-0.4px; margin-bottom:20px; }}
  .compCol.bad .compHead {{ color:#DC2626; }}
  .compCol.good .compHead {{ color:#059669; }}
  .compList {{ list-style:none; display:flex; flex-direction:column; gap:16px; }}
  .compList li {{ display:flex; gap:12px; font-size:21px; line-height:1.4; color:#334155; font-weight:500; }}
  .ci {{ flex:0 0 auto; font-weight:800; font-size:20px; }}
  .compCol.bad .ci {{ color:#EF4444; }}
  .compCol.good .ci {{ color:#10B981; }}
  .compCol.neutral .ci {{ color:{ga}; }}

  /* ---- list ---- */
  .cards {{ flex:1; display:flex; flex-direction:column; gap:20px; min-height:0; }}
  .card {{
    flex:1; display:flex; gap:22px; align-items:center;
    background:#FFFFFF; border:1px solid #EEF1F6; border-left:8px solid var(--accent);
    border-radius:20px; padding:24px 28px; box-shadow:0 10px 30px rgba(15,23,42,0.05);
  }}
  .badge {{
    flex:0 0 auto; width:64px; height:64px; border-radius:16px;
    background:var(--soft); display:flex; align-items:center; justify-content:center; font-size:34px;
  }}
  .cardHeading {{ font-size:27px; font-weight:800; letter-spacing:-0.4px; margin-bottom:6px; }}
  .cardBody {{ font-size:20px; line-height:1.45; color:#475569; font-weight:500; }}

  /* ---- cta + footer ---- */
  .cta {{
    margin-top:36px; display:inline-flex; align-items:center; gap:12px;
    background:linear-gradient(135deg,{ga},{gb}); color:#fff;
    font-size:23px; font-weight:800; padding:18px 30px; border-radius:16px;
    box-shadow:0 12px 28px rgba(108,43,217,0.28);
  }}
  .ctaDot {{ width:12px; height:12px; border-radius:50%; background:#FACC15; }}
  .cta {{ align-self:flex-start; }}
  .footer {{
    margin-top:30px; display:flex; justify-content:space-between; align-items:center;
    font-size:15px; color:#94A3B8; font-weight:700;
    border-top:1px solid #EEF1F6; padding-top:20px;
  }}
</style></head>
<body>
  {header}
  <div class="stageMain">
    {title_block}
    {body_inner}
    {cta}
  </div>
  {footer}
</body></html>""".format(
        W=CANVAS_W, H=CANVAS_H, ga=GRAD_A, gb=GRAD_B,
        header=_header(),
        title_block=_title_block(data),
        body_inner=body_inner,
        cta=_cta(data.get("cta")),
        footer=_footer(),
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
            # full_page=True captures all content: the slide fills the page for
            # short copy and grows taller (never clips) when the text runs long.
            page.screenshot(path=out_path, full_page=True)
            browser.close()
        return out_path
    except Exception as e:
        print("Warning: infographic render failed (%s)." % e)
        return None
