"""One-off campaigns: send a template to a business's list (optionally one tag)."""

from . import db
from .config import get_business
from .mailer import Mailer
from .sending import Log, SendRun


def pending_recipients(conn, campaign) -> list:
    """Subscribed contacts in the campaign's audience that haven't been sent it yet."""
    sql = ("SELECT * FROM contacts WHERE business = ? AND status = 'subscribed'"
           " AND id NOT IN (SELECT contact_id FROM sends WHERE campaign_id = ?"
           "               AND status = 'sent' AND contact_id IS NOT NULL)")
    params = [campaign["business"], campaign["id"]]
    if campaign["tag"]:
        sql += " AND tags LIKE ?"
        params.append(f"%,{campaign['tag']},%")
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def send_campaign(conn, campaign_id: int, *, dry_run: bool = True, log: Log = print) -> SendRun:
    """Send a campaign. Safe to run again: contacts already sent to are skipped,
    so a run stopped by the daily limit picks up where it left off."""
    campaign = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if campaign is None:
        raise ValueError(f"no campaign with id {campaign_id}")
    biz = get_business(campaign["business"])
    template = conn.execute("SELECT * FROM templates WHERE id = ?",
                            (campaign["template_id"],)).fetchone()
    recipients = pending_recipients(conn, campaign)
    audience = f"tag '{campaign['tag']}'" if campaign["tag"] else "all subscribed contacts"
    log(f"Campaign '{campaign['name']}' ({biz.name}, {audience}): "
        f"{len(recipients)} recipient(s) still to send; dry_run={dry_run}")

    with Mailer(biz, dry_run) as mailer:
        run = SendRun(conn, mailer, log)
        if not dry_run and recipients:
            conn.execute("UPDATE campaigns SET status = 'sending' WHERE id = ?", (campaign_id,))
            conn.commit()
        for contact in recipients:
            if not run.can_send():
                break
            run.deliver(contact, template, campaign_id=campaign_id)

    if dry_run:
        conn.rollback()
    else:
        left = len(pending_recipients(conn, campaign))
        conn.execute("UPDATE campaigns SET status = ?, sent_at = COALESCE(sent_at, ?) WHERE id = ?",
                     ("sent" if left == 0 else "partial", db.now(), campaign_id))
        conn.commit()
        if left:
            log(f"{left} recipient(s) not sent yet. Send the campaign again to continue.")
    log(run.summary())
    return run
