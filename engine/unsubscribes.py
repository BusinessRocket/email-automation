"""Read each business inbox over IMAP and apply unsubscribes, bounces and replies.

Every email carries a "List-Unsubscribe: mailto:...?subject=unsubscribe"
header and a footer asking people to reply "unsubscribe". Gmail's own
unsubscribe button uses the header, so these all arrive in the inbox with
"unsubscribe" in the subject. Bounces arrive from mailer-daemon with an
X-Failed-Recipients header.

Only the subject is searched: replies quote our footer, so searching the body
would unsubscribe anyone who simply replied.

Any other email from a known contact, or from a colleague at the same company
domain, counts as a reply and tags them 'replied', which stops their follow-ups (sequences exit on that tag) so a
person can answer them. Replies are looked for in Spam as well as the inbox. Out-of-office and other automatic replies are ignored.
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
REPLY_FOLDERS = ("INBOX", '"[Gmail]/Spam"')
REPLIED_TAG = "replied"
AUTO_REPLY_SUBJECTS = ("automatic reply", "auto reply", "autoreply", "auto:", "out of office",
                       "away from", "on leave")
FREE_MAIL_DOMAINS = {"gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "live.com",
                     "live.com.au", "yahoo.com", "yahoo.com.au", "icloud.com", "me.com",
                     "bigpond.com", "bigpond.net.au", "optusnet.com.au", "proton.me",
                     "protonmail.com", "aol.com"}


def _is_auto_reply(msg) -> bool:
    if (msg.get("Auto-Submitted") or "no").strip().lower() != "no":
        return True
    if msg.get("X-Autoreply") or msg.get("X-Autorespond"):
        return True
    if (msg.get("Precedence") or "").strip().lower() in ("auto_reply", "bulk", "junk"):
        return True
    subject = (msg.get("Subject") or "").strip().lower()
    return any(subject.startswith(s) or s in subject[:40] for s in AUTO_REPLY_SUBJECTS)


def _mark_replied(conn, business: str, address: str) -> list[str]:
    """Tag the contact 'replied' and return the addresses newly tagged.

    Businesses often answer from a person's own address (jess@) rather than
    the one we wrote to (hello@), so with no exact match, every contact at the
    same company domain counts. Free-mail domains are never matched this way.
    """
    rows = conn.execute("SELECT id, email, tags FROM contacts WHERE business = ? AND email = ?",
                        (business, address)).fetchall()
    domain = address.rpartition("@")[2]
    if not rows and domain and domain not in FREE_MAIL_DOMAINS:
        rows = conn.execute("SELECT id, email, tags FROM contacts WHERE business = ?"
                            " AND lower(email) LIKE ?", (business, f"%@{domain}")).fetchall()
    tagged = []
    for row in rows:
        if REPLIED_TAG in db.tag_list(row["tags"]):
            continue
        conn.execute("UPDATE contacts SET tags = ?, updated_at = ? WHERE id = ?",
                     (db.store_tags(db.tag_list(row["tags"]) + [REPLIED_TAG]), db.now(), row["id"]))
        tagged.append(row["email"])
    return tagged


def _messages(imap, query: str, fields: str) -> list:
    """Header-only messages matching an IMAP search; nothing is marked as read.

    Headers are fetched in batches, since one request per message takes about
    a minute for a month of mail.
    """
    typ, data = imap.search(None, query)
    if typ != "OK" or not data or not data[0]:
        return []
    nums = data[0].split()
    found = []
    for i in range(0, len(nums), 200):
        typ, parts = imap.fetch(b",".join(nums[i:i + 200]),
                                f"(BODY.PEEK[HEADER.FIELDS ({fields})])")
        if typ == "OK":
            found += [email.message_from_bytes(p[1]) for p in parts if isinstance(p, tuple)]
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
        # A first reply to a cold email sometimes lands in Spam, so look there too.
        for folder in REPLY_FOLDERS:
            if folder != "INBOX" and imap.select(folder, readonly=True)[0] != "OK":
                continue
            for msg in _messages(imap, f"(SINCE {since})",
                                 "FROM SUBJECT AUTO-SUBMITTED PRECEDENCE X-AUTOREPLY X-AUTORESPOND"):
                addr = parseaddr(msg.get("From", ""))[1].lower()
                if not addr or "mailer-daemon" in addr or _is_auto_reply(msg):
                    continue
                where = "" if folder == "INBOX" else ", found in Spam"
                for contact in _mark_replied(conn, biz.key, addr):
                    via = "" if contact.lower() == addr else f" (replied from {addr})"
                    log(f"REPLIED [{biz.key}] {contact}{via}{where}: follow-ups stopped;"
                        " answer them yourself")
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
