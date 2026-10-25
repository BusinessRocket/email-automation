"""Send a personalized email to every recipient in a CSV via Gmail SMTP.

Configuration (environment variables, set as GitHub Actions secrets):
  GMAIL_ADDRESS       sender Gmail address
  GMAIL_APP_PASSWORD  16-char Google App Password (not your normal password)
  RECIPIENTS_CSV      full CSV text with header: email,name[,any extra columns]
  DRY_RUN             "true" to render and log emails without sending

The subject and body come from template/subject.txt and template/body.txt.
Any CSV column can be used as a placeholder, e.g. {name}.

Exit code is non-zero if configuration is missing or any send fails, so a
failed run shows up red in GitHub Actions instead of failing silently.
"""

import csv
import io
import os
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).parent
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
DELAY_SECONDS = 1.0  # pause between sends to stay under Gmail rate limits


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] {msg}", flush=True)


def load_recipients(csv_text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(csv_text.strip())))
    if not rows or "email" not in rows[0]:
        raise ValueError("RECIPIENTS_CSV must have a header row containing 'email'")
    clean = []
    for i, row in enumerate(rows, start=2):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if not row.get("email") or "@" not in row["email"]:
            log(f"SKIP line {i}: invalid email {row.get('email')!r}")
            continue
        row.setdefault("name", "")
        clean.append(row)
    return clean


def render(template: str, row: dict) -> str:
    try:
        return template.format(**row)
    except KeyError as e:
        raise ValueError(f"template uses {{{e.args[0]}}} but CSV has no such column")


def main() -> int:
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"
    sender = os.environ.get("GMAIL_ADDRESS", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    csv_text = os.environ.get("RECIPIENTS_CSV", "")

    missing = [n for n, v in [("GMAIL_ADDRESS", sender),
                              ("GMAIL_APP_PASSWORD", password),
                              ("RECIPIENTS_CSV", csv_text)] if not v]
    if dry_run and "GMAIL_APP_PASSWORD" in missing:
        missing.remove("GMAIL_APP_PASSWORD")
    if dry_run and "RECIPIENTS_CSV" in missing:
        log("DRY RUN: RECIPIENTS_CSV not set, using recipients.example.csv")
        csv_text = (ROOT / "recipients.example.csv").read_text(encoding="utf-8")
        missing.remove("RECIPIENTS_CSV")
    if dry_run and "GMAIL_ADDRESS" in missing:
        sender = "sender@example.com"
        missing.remove("GMAIL_ADDRESS")
    if missing:
        log(f"FAILED: missing required secrets: {', '.join(missing)}")
        return 2

    subject_tpl = (ROOT / "template" / "subject.txt").read_text(encoding="utf-8").strip()
    body_tpl = (ROOT / "template" / "body.txt").read_text(encoding="utf-8")
    recipients = load_recipients(csv_text)
    log(f"{len(recipients)} recipient(s); dry_run={dry_run}")

    sent, failed = 0, []
    smtp = None
    try:
        if not dry_run:
            smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
            smtp.login(sender, password)
        for row in recipients:
            to = row["email"]
            try:
                msg = EmailMessage()
                msg["From"] = sender
                msg["To"] = to
                msg["Subject"] = render(subject_tpl, row)
                msg.set_content(render(body_tpl, row))
                if dry_run:
                    log(f"DRY RUN would send to {to}: {msg['Subject']!r}")
                else:
                    smtp.send_message(msg)
                    log(f"SENT {to}")
                    time.sleep(DELAY_SECONDS)
                sent += 1
            except Exception as e:  # log and continue with the next recipient
                failed.append(to)
                log(f"FAILED {to}: {type(e).__name__}: {e}")
    except Exception as e:
        log(f"FAILED before/while sending: {type(e).__name__}: {e}")
        return 1
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass

    log(f"done: {sent} ok, {len(failed)} failed")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Email run ({'dry run' if dry_run else 'live'})\n\n"
                    f"- Sent: {sent}\n- Failed: {len(failed)}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
