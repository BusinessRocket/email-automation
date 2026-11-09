"""Automated sequences (drip emails).

A sequence starts for any subscribed contact carrying its trigger tag, for
example 'quote'. Each step waits `delay_days` after the previous step (the
first step waits after enrolment). A contact leaves the sequence when they
unsubscribe, bounce, or gain one of the sequence's exit tags (for example
'won' on a quote follow-up).

`run_sequences` is meant to run every 15 minutes (see tick.pyw); it is also safe to
run more often. Steps of business outreach sequences that fall due at the weekend
wait until Monday.
"""

from datetime import datetime

from . import db
from .config import BUSINESSES
from .mailer import Mailer, NotConfigured
from .sending import Log, SendRun

# Emails to businesses wait for a weekday: few people read cold email at the weekend.
WEEKDAY_ONLY_TRIGGERS = {"outreach"}


def _step_at_or_after(conn, sequence_id: int, position: int):
    return conn.execute(
        "SELECT * FROM sequence_steps WHERE sequence_id = ? AND position >= ?"
        " ORDER BY position LIMIT 1", (sequence_id, position)).fetchone()


def enroll_new(conn, log: Log) -> int:
    added = 0
    ts = db.now()
    for seq in conn.execute("SELECT * FROM sequences WHERE active = 1").fetchall():
        first = _step_at_or_after(conn, seq["id"], 0)
        if first is None:
            continue
        candidates = conn.execute(
            "SELECT * FROM contacts WHERE business = ? AND status = 'subscribed'"
            " AND tags LIKE ? AND id NOT IN"
            " (SELECT contact_id FROM enrollments WHERE sequence_id = ?)",
            (seq["business"], f"%,{seq['trigger_tag']},%", seq["id"])).fetchall()
        for c in candidates:
            if db.has_any_tag(c["tags"], seq["exit_tags"]):
                continue
            conn.execute(
                "INSERT INTO enrollments (sequence_id, contact_id, enrolled_at, next_position,"
                " next_due_at, status) VALUES (?, ?, ?, ?, ?, 'active')",
                (seq["id"], c["id"], ts, first["position"], db.shift(ts, days=first["delay_days"])))
            log(f"ENROLLED [{seq['business']}] {c['email']} in '{seq['name']}'")
            added += 1
    return added


def stop_exited(conn, log: Log) -> int:
    rows = conn.execute(
        "SELECT e.id, c.email, c.status, c.tags, s.exit_tags, s.name, s.business"
        " FROM enrollments e JOIN contacts c ON c.id = e.contact_id"
        " JOIN sequences s ON s.id = e.sequence_id WHERE e.status = 'active'").fetchall()
    stopped = 0
    for r in rows:
        if r["status"] != "subscribed":
            reason = r["status"]
        elif db.has_any_tag(r["tags"], r["exit_tags"]):
            reason = "exit tag"
        else:
            continue
        conn.execute("UPDATE enrollments SET status = 'stopped' WHERE id = ?", (r["id"],))
        log(f"STOPPED [{r['business']}] {r['email']} in '{r['name']}' ({reason})")
        stopped += 1
    return stopped


def due(conn, business: str) -> list:
    rows = conn.execute(
        "SELECT e.*, s.name AS sequence_name, s.trigger_tag FROM enrollments e"
        " JOIN sequences s ON s.id = e.sequence_id"
        " WHERE e.status = 'active' AND s.active = 1 AND s.business = ? AND e.next_due_at <= ?"
        " ORDER BY e.next_due_at", (business, db.now())).fetchall()
    if datetime.now().weekday() >= 5:  # Saturday or Sunday on this PC's clock
        rows = [r for r in rows if r["trigger_tag"] not in WEEKDAY_ONLY_TRIGGERS]
    return rows


def run_sequences(conn, *, dry_run: bool = True, log: Log = print,
                  businesses: list[str] | None = None) -> list[SendRun]:
    """Enrol, stop and send everything that's due. Dry runs change nothing."""
    log(f"Running sequences; dry_run={dry_run}")
    stop_exited(conn, log)
    enroll_new(conn, log)
    if not dry_run:
        conn.commit()

    runs = []
    for key in businesses or list(BUSINESSES):
        biz = BUSINESSES[key]
        pending = due(conn, key)
        if not pending:
            log(f"[{key}] nothing due")
            continue
        try:
            with Mailer(biz, dry_run) as mailer:
                run = SendRun(conn, mailer, log)
                for e in pending:
                    if not run.can_send():
                        break
                    _send_step(conn, run, e, log)
                runs.append(run)
                log(run.summary())
        except NotConfigured as e:
            log(f"SKIPPED [{key}] {len(pending)} due email(s): {e}")
        except OSError as e:  # no internet or Gmail unreachable; covers smtplib errors too
            log(f"FAILED [{key}] could not reach Gmail ({type(e).__name__}: {e});"
                f" {len(pending)} due email(s) wait for the next run")
    if dry_run:
        conn.rollback()
    return runs


def _send_step(conn, run: SendRun, enrollment, log: Log) -> None:
    step = _step_at_or_after(conn, enrollment["sequence_id"], enrollment["next_position"])
    if step is None:  # steps were removed after this contact enrolled
        conn.execute("UPDATE enrollments SET status = 'completed' WHERE id = ?", (enrollment["id"],))
        if not run.mailer.dry_run:
            conn.commit()
        return
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?",
                           (enrollment["contact_id"],)).fetchone()
    template = conn.execute("SELECT * FROM templates WHERE id = ?",
                            (step["template_id"],)).fetchone()

    def advance():
        nxt = _step_at_or_after(conn, enrollment["sequence_id"], step["position"] + 1)
        if nxt is None:
            conn.execute("UPDATE enrollments SET status = 'completed', next_due_at = NULL"
                         " WHERE id = ?", (enrollment["id"],))
        else:
            conn.execute("UPDATE enrollments SET next_position = ?, next_due_at = ? WHERE id = ?",
                         (nxt["position"], db.shift(db.now(), days=nxt["delay_days"]),
                          enrollment["id"]))

    run.deliver(contact, template, enrollment_id=enrollment["id"],
                step_position=step["position"], after_sent=advance)
