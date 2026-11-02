"""Read each business inbox over IMAP and apply unsubscribes and bounces.

Every email carries a "List-Unsubscribe: mailto:...?subject=unsubscribe"
header and a footer asking people to reply "unsubscribe". Gmail's own
unsubscribe button uses the header, so these all arrive in the inbox with
"unsubscribe" in the subject. Bounces arrive from mailer-daemon with an
X-Failed-Recipients header.

Only the subject is searched: replies quote our footer, so searching the body
would unsubscribe anyone who simply replied.
"""

import email
import imaplib
from datetime import date, timedelta
from email.utils import getaddresses, parseaddr

from .config import BUSINESSES, Business
from .contacts import set_status
from .sending import Log

IMAP_HOST = "imap.gmail.com"


def _headers(imap, query: str, field: str) -> list[str]:
    typ, data = imap.search(None, query)
    if typ != "OK" or not data or not data[0]:
        return []
    values = []
    for num in data[0].split():
        typ, parts = imap.fetch(num, f"(BODY.PEEK[HEADER.FIELDS ({field})])")
        if typ == "OK" and parts and isinstance(parts[0], tuple):
            msg = email.message_from_bytes(parts[0][1])
            values.extend(msg.get_all(field) or [])
    return values


def sync_business(conn, biz: Business, *, days: int = 30, log: Log = print) -> tuple[int, int]:
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
        conn.commit()
        return unsub, bounced
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
            unsub, bounced = sync_business(conn, biz, log=log)
            log(f"[{biz.key}] inbox checked: {unsub} unsubscribe(s), {bounced} bounce(s)")
        except Exception as e:
            log(f"FAILED [{biz.key}] inbox check: {type(e).__name__}: {e}")
