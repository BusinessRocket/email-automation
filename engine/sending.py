"""Shared send loop bookkeeping: daily limits, failure cut-off and the send log."""

from typing import Callable

from . import db
from .mailer import Mailer
from .render import render_email

MAX_CONSECUTIVE_FAILURES = 5

Log = Callable[[str], None]


def sent_last_24h(conn, business: str) -> int:
    since = db.shift(db.now(), hours=-24)
    return conn.execute(
        "SELECT COUNT(*) FROM sends WHERE business = ? AND status = 'sent' AND sent_at >= ?",
        (business, since)).fetchone()[0]


class SendRun:
    """One pass of sending for one business.

    Live sends are recorded in `sends` and committed one at a time, so a crash
    never forgets an email that already went out. Dry runs record nothing.
    """

    def __init__(self, conn, mailer: Mailer, log: Log):
        self.conn = conn
        self.mailer = mailer
        self.log = log
        biz = mailer.biz
        self.remaining = max(0, biz.daily_limit - sent_last_24h(conn, biz.key))
        self.sent = self.failed = self.consecutive_failures = 0
        self.stop_reason = ""

    def can_send(self) -> bool:
        biz = self.mailer.biz
        if self.remaining <= 0:
            self.stop_reason = (f"{biz.name} reached its limit of {biz.daily_limit} emails "
                                f"in 24 hours; the rest will go on a later run")
        elif self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self.stop_reason = f"stopped after {self.consecutive_failures} failures in a row"
        else:
            return True
        return False

    def deliver(self, contact, template, *, campaign_id=None, enrollment_id=None,
                step_position=None, after_sent: Callable[[], None] | None = None) -> bool:
        """Send one email. `after_sent` runs inside the same commit as the send record."""
        biz = self.mailer.biz
        r = render_email(biz, template["subject"], template["body"], contact)
        to = contact["email"]
        if self.mailer.dry_run:
            self.log(f"DRY RUN [{biz.key}] would send to {to}: {r.subject!r}")
            ok = True
        else:
            try:
                self.mailer.send(to, r)
                ok, error = True, ""
            except Exception as e:
                ok, error = False, f"{type(e).__name__}: {e}"
            self.conn.execute(
                "INSERT INTO sends (business, contact_id, email, campaign_id, enrollment_id,"
                " step_position, subject, status, error, sent_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (biz.key, contact["id"], to, campaign_id, enrollment_id, step_position,
                 r.subject, "sent" if ok else "failed", error, db.now()))
            if ok and after_sent:
                after_sent()
            self.conn.commit()
            self.log(f"SENT [{biz.key}] {to}: {r.subject!r}" if ok
                     else f"FAILED [{biz.key}] {to}: {error}")
        if ok:
            self.sent += 1
            self.remaining -= 1
            self.consecutive_failures = 0
        else:
            self.failed += 1
            self.consecutive_failures += 1
        return ok

    def summary(self) -> str:
        verb = "would send" if self.mailer.dry_run else "sent"
        s = f"[{self.mailer.biz.key}] {verb} {self.sent}, failed {self.failed}"
        return f"{s} ({self.stop_reason})" if self.stop_reason else s
