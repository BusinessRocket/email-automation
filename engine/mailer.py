"""Gmail SMTP sending, one connection per business account."""

import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .config import Business
from .render import Rendered, unsubscribe_href

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
DELAY_SECONDS = 1.0  # pause between sends to stay under Gmail rate limits


class NotConfigured(Exception):
    pass


class Mailer:
    """Context manager. In dry-run mode it builds messages but never connects."""

    def __init__(self, biz: Business, dry_run: bool = True):
        self.biz = biz
        self.dry_run = dry_run
        self.smtp: smtplib.SMTP_SSL | None = None

    def __enter__(self) -> "Mailer":
        if not self.dry_run:
            if not self.biz.configured:
                p = self.biz.env_prefix
                raise NotConfigured(f"{self.biz.name}: set {p}_GMAIL_ADDRESS and "
                                    f"{p}_GMAIL_APP_PASSWORD in .env")
            self._connect()
        return self

    def __exit__(self, *exc) -> None:
        if self.smtp is not None:
            try:
                self.smtp.quit()
            except Exception:
                pass
            self.smtp = None

    def _connect(self) -> None:
        self.smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        self.smtp.login(self.biz.gmail_address, self.biz.gmail_password)

    def build(self, to: str, r: Rendered) -> EmailMessage:
        sender = self.biz.gmail_address or "not-configured@example.invalid"
        msg = EmailMessage()
        msg["From"] = formataddr((self.biz.from_name, sender))
        msg["To"] = to
        msg["Subject"] = r.subject
        msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
        href = unsubscribe_href(self.biz)
        if href:
            msg["List-Unsubscribe"] = f"<{href}>"
        msg.set_content(r.text)
        msg.add_alternative(r.html, subtype="html")
        return msg

    def send(self, to: str, r: Rendered) -> None:
        msg = self.build(to, r)
        if self.dry_run:
            return
        try:
            self.smtp.send_message(msg)
        except smtplib.SMTPServerDisconnected:
            # Gmail drops long-lived connections; reconnect once and retry.
            self._connect()
            self.smtp.send_message(msg)
        time.sleep(DELAY_SECONDS)
