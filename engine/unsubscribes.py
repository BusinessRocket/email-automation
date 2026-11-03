"""Read each business inbox over IMAP and apply unsubscribes, bounces and replies.

Every email carries a "List-Unsubscribe: mailto:...?subject=unsubscribe"
header and a footer asking people to reply "unsubscribe". Gmail's own
unsubscribe button uses the header, so these all arrive in the inbox with
"unsubscribe" in the subject. Bounces arrive from mailer-daemon with an
X-Failed-Recipients header.

Only the subject is searched: replies quote our footer, so searching the body
would unsubscribe anyone who simply replied.

Any other email from a known contact counts as a reply and tags them
'replied', which stops their follow-ups (sequences exit on that tag) so a
person can answer them. Out-of-office and other automatic replies are ignored.
"""

import email
import imaplib
from datetime import date, timedelta
from email.utils import getaddresses, parseaddr

from . import db
from .config import BUSINESSES, Business
from .contacts import set_status
from .sending import Log

IMAP_HOST = "imap.gmail.com"
REPLIED_TAG = "replied"
AUTO_REPLY_SUBJECTS = ("automatic reply", "auto reply", "autoreply", "auto:", "out of office",
                       "away from", "on leave")


def _is_auto_reply(msg) -> bool:
    if (msg.get("Auto-Submitted") or "no").strip().lower() != "no":
        return True
    if msg.get("X-Autoreply") or msg.get("X-Autorespond"):
        return True
    if (msg.get("Precedence") or "").strip().lower() in ("auto_reply", "bulk", "junk"):
        return True
    subject = (msg.get("Subject") or "").strip().lower()
    return any(subject.startswith(s) or s in subject[:40] for s in AUTO_REPLY_SUBJECTS)


def _mark_replied(conn, business: str, address: str) -> bool:
    """Tag a known contact 'replied'. Returns True if the tag was new."""
    row = conn.execute("SELECT id, tags FROM contacts WHERE business = ? AND email = ?",
                       (business, address)).fetchone()
    if row is None or REPLIED_TAG in db.tag_list(row["tags"]):
        return False
    conn.execute("UPDATE contacts SET tags = ?, updated_at = ? WHERE id = ?",
                 (db.store_tags(db.tag_list(row["tags"]) + [REPLIED_TAG]), db.now(), row["id"]))
    return True


def _messages(imap, query: str, fields: str) -> list:
    """Header-only messages matching an IMAP search; nothing is marked as read."""
    typ, data = imap.search(None, query)
    if typ != "OK" or not data or not data[0]:
        return []
    found = []
    for num in data[0].split():
        typ, parts = imap.fetch(num, f"(BODY.PEEK[HEADER.FIELDS ({fields})])")
        if typ == "OK" and parts and isinstance(parts[0], tuple):
            found.append(email.message_from_bytes(parts[0][1]))
    return found


def _headers(imap, query: str, field: str) -> list[str]:
    return [v for msg in _messages(imap, query, field) for v in msg.get_all(field) or []]


def sync_business(conn, biz: Business, *, days: int = 30, log: Log = print) -> tuple[int, int, int]:
    since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    try:
        imap.login(biz.gmail_address, biz.gmail_password)
        imap.select("INBOX", readonly=True)
        unsub = bounced = 0
        for raw in _headers(imap, f'(SINCE {since} SUBJECT "unsubscribe")', "FROM"):
            addr = parseaddr(raw)[1]
            if addr and set_status(conn, biz.key, addr, "unsubscribed"):
                log(f"UNSUBSCRIBED [{biz.key}] {addr}")
                unsub += 1
        for raw in _headers(imap, f'(SINCE {since} FROM "mailer-daemon")', "X-FAILED-RECIPIENTS"):
            for _, addr in getaddresses([raw]):
                if addr and set_status(conn, biz.key, addr, "bounced"):
                    log(f"BOUNCED [{biz.key}] {addr}")
                    bounced += 1
        replied = 0
        for msg in _messages(imap, f"(SINCE {since})",
                             "FROM SUBJECT AUTO-SUBMITTED PRECEDENCE X-AUTOREPLY X-AUTORESPOND"):
            addr = parseaddr(msg.get("From", ""))[1].lower()
            if not addr or "mailer-daemon" in addr or _is_auto_reply(msg):
                continue
            if _mark_replied(conn, biz.key, addr):
                log(f"REPLIED [{biz.key}] {addr}: follow-ups stopped; answer them yourself")
                replied += 1
        conn.commit()
        return unsub, bounced, replied
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def sync_all(conn, *, log: Log = print) -> None:
    for biz in BUSINESSES.values():
        if not biz.configured:
            log(f"[{biz.key}] skipped inbox check: Gmail credentials not set")
            continue
        try:
            unsub, bounced, replied = sync_business(conn, biz, log=log)
            log(f"[{biz.key}] inbox checked: {unsub} unsubscribe(s), {bounced} bounce(s),"
                f" {replied} new repl(ies)")
        except Exception as e:
            log(f"FAILED [{biz.key}] inbox check: {type(e).__name__}: {e}")
