"""Turn a template into an HTML email plus a plain-text version.

Template bodies are plain text with a few extras:
  {first_name}, {name}, {suburb}, {business_name}, {booking_url} ...  placeholders
  blank line                 new paragraph
  **bold**                   bold text
  [[Button label|https://...]]  a link or button (dropped if the link is empty)

Two styles:
  plain    looks like an email typed in Gmail: no banner, links instead of
           buttons. Gmail tends to put these in the Primary tab.
  branded  coloured header, buttons and a footer panel. Reads as a newsletter,
           so Gmail usually files it under Promotions.
"""

import html
import re
from dataclasses import dataclass, field

from .config import Business

PLACEHOLDER = re.compile(r"\{(\w+)\}")
BUTTON = re.compile(r"\[\[(.+?)\|(.*?)\]\]")
BOLD = re.compile(r"\*\*(.+?)\*\*")
SAFE_URL = re.compile(r"^(https?://|mailto:|tel:)\S+$")

STYLES = ("plain", "branded")

SAMPLE_CONTACT = {"name": "Alex Sample", "email": "alex@example.com",
                  "phone": "0400 000 000", "suburb": "Sampleville"}


@dataclass
class Rendered:
    subject: str
    text: str
    html: str
    unknown: list[str] = field(default_factory=list)  # placeholders with no value source


def contact_vars(contact) -> dict[str, str]:
    name = (contact["name"] or "").strip()
    return {
        "name": name,
        "first_name": name.split()[0] if name else "there",
        "email": contact["email"],
        "phone_contact": contact["phone"] or "",
        "suburb": contact["suburb"] or "",
    }


def fill(text: str, values: dict, unknown: set) -> str:
    def sub(m):
        key = m.group(1)
        if key in values:
            return str(values[key])
        unknown.add(key)
        return ""
    return PLACEHOLDER.sub(sub, text)


def unsubscribe_href(biz: Business) -> str:
    return f"mailto:{biz.gmail_address}?subject=unsubscribe" if biz.gmail_address else ""


def render_email(biz: Business, subject: str, body: str, contact,
                 style: str = "plain") -> Rendered:
    values = {**biz.template_vars(), **contact_vars(contact)}
    unknown: set = set()
    subject = " ".join(fill(subject, values, unknown).split())
    body = fill(body, values, unknown).strip()
    make_html = _branded_html if style == "branded" else _plain_html
    return Rendered(subject=subject, text=_text(biz, body), html=make_html(biz, body),
                    unknown=sorted(unknown))


def _footer_lines(biz: Business) -> list[str]:
    lines = [biz.name]
    if biz.address:
        lines.append(biz.address)
    contact_bits = [b for b in (biz.phone, biz.website) if b]
    if contact_bits:
        lines.append(" · ".join(contact_bits))
    return lines


def _unsubscribe_text(biz: Business) -> str:
    return (f"You're getting this because you've been in touch with {biz.name}. "
            f"If you'd rather not hear from us, just reply \"unsubscribe\".")


def _text(biz: Business, body: str) -> str:
    def button(m):
        label, url = m.group(1).strip(), m.group(2).strip()
        return f"{label}: {url}" if SAFE_URL.match(url) else ""
    text = BOLD.sub(r"\1", BUTTON.sub(button, body))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    footer = "\n".join(_footer_lines(biz))
    return f"{text}\n\n--\n{footer}\n\n{_unsubscribe_text(biz)}\n"


def _paragraphs(body: str, link_style: str) -> list[str]:
    """Escaped HTML for each paragraph, with links and bold filled in."""
    def link(m):
        label, url = m.group(1).strip(), html.unescape(m.group(2).strip())
        if not SAFE_URL.match(url):
            return ""
        style = f' style="{link_style}"' if link_style else ""
        return f'<a href="{html.escape(url)}"{style}>{label}</a>'

    paragraphs = []
    for para in re.split(r"\n\s*\n", body):
        p = BUTTON.sub(link, html.escape(para.strip()))
        p = BOLD.sub(r"<strong>\1</strong>", p).replace("\n", "<br>")
        if p.strip():
            paragraphs.append(p)
    return paragraphs


def _plain_html(biz: Business, body: str) -> str:
    # Mirrors the markup Gmail itself produces, so the message looks hand-typed.
    paragraphs = "<br>".join(f"<div>{p}</div>" for p in _paragraphs(body, ""))
    footer = "<br>".join(html.escape(line) for line in _footer_lines(biz))
    unsub = html.escape(_unsubscribe_text(biz))
    return (f'<div dir="ltr">{paragraphs}<br><div>--</div>'
            f'<div style="color:#555555;">{footer}</div><br>'
            f'<div style="color:#888888;font-size:12px;">{unsub}</div></div>')


def _branded_html(biz: Business, body: str) -> str:
    color = html.escape(biz.brand_color)
    button = (f"display:inline-block;background:{color};color:#ffffff;padding:12px 22px;"
              f"border-radius:6px;text-decoration:none;font-weight:bold;")
    paragraphs = [f'<p style="margin:0 0 16px;">{p}</p>' for p in _paragraphs(body, button)]

    footer = "<br>".join(html.escape(line) for line in _footer_lines(biz))
    unsub = html.escape(_unsubscribe_text(biz))
    href = unsubscribe_href(biz)
    if href:
        unsub += f' <a href="{html.escape(href)}" style="color:#777;">Unsubscribe</a>'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f2;"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;color:#222222;">
<tr><td style="background:{color};padding:20px 28px;color:#ffffff;">
<div style="font-size:20px;font-weight:bold;">{html.escape(biz.name)}</div>
<div style="font-size:13px;opacity:0.9;">{html.escape(biz.tagline)}</div></td></tr>
<tr><td style="padding:28px;font-size:16px;line-height:1.55;">{''.join(paragraphs)}</td></tr>
<tr><td style="padding:18px 28px;background:#fafafa;border-top:1px solid #eeeeee;font-size:12px;color:#777777;line-height:1.5;">
{footer}<br><br>{unsub}</td></tr>
</table></td></tr></table></body></html>"""
