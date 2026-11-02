"""Local dashboard. Start with `python -m engine serve`; it listens on 127.0.0.1 only."""

import secrets
import threading
import uuid

from flask import (Flask, abort, flash, g, redirect, render_template, request, session,
                   url_for)

from . import campaigns as campaigns_mod
from . import contacts as contacts_mod
from . import db, sequences as sequences_mod, unsubscribes
from .config import BUSINESSES, DATA_DIR
from .mailer import Mailer, NotConfigured
from .render import SAMPLE_CONTACT, render_email
from .seed import seed
from .sending import sent_last_24h

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


def _secret_key() -> str:
    path = DATA_DIR / "secret_key"
    if not path.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


app.secret_key = _secret_key()
_init_conn = db.connect()
seed(_init_conn)
_init_conn.close()


def conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.teardown_appcontext
def _close(exc):
    c = g.pop("conn", None)
    if c is not None:
        c.close()


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def _check_csrf():
    # Stops other websites from posting to this dashboard (and sending email) behind your back.
    if request.method == "POST":
        token = session.get("csrf")
        if not token or not secrets.compare_digest(token, request.form.get("csrf", "")):
            abort(400, "This form expired. Go back, reload the page and try again.")


@app.context_processor
def _globals():
    return {"businesses": BUSINESSES, "csrf_token": csrf_token, "tag_list": db.tag_list}


def business(key: str):
    if key not in BUSINESSES:
        abort(404)
    return BUSINESSES[key]


def one(sql: str, *params):
    row = conn().execute(sql, params).fetchone()
    if row is None:
        abort(404)
    return row


# --- background jobs -------------------------------------------------------

JOBS: dict[str, dict] = {}
_live_lock = threading.Lock()


def start_job(title: str, fn, *, live: bool):
    """Run fn(conn, log) on a thread and redirect to its progress page.
    Only one live job runs at a time so nothing is sent twice."""
    if live and not _live_lock.acquire(blocking=False):
        flash("A live send is already running. Wait for it to finish first.", "error")
        return redirect(request.referrer or url_for("overview"))
    job_id = uuid.uuid4().hex[:8]
    job = {"id": job_id, "title": title, "lines": [], "done": False, "live": live}
    JOBS[job_id] = job

    def run():
        c = db.connect()
        try:
            fn(c, job["lines"].append)
        except NotConfigured as e:
            job["lines"].append(f"NOT CONFIGURED: {e}")
        except Exception as e:
            job["lines"].append(f"ERROR: {type(e).__name__}: {e}")
        finally:
            c.close()
            job["done"] = True
            if live:
                _live_lock.release()

    threading.Thread(target=run, daemon=True).start()
    return redirect(url_for("job", job_id=job_id))


@app.route("/jobs/<job_id>")
def job(job_id):
    if job_id not in JOBS:
        abort(404)
    return render_template("job.html", job=JOBS[job_id], biz=None)


# --- overview & activity ---------------------------------------------------

@app.route("/")
def overview():
    c = conn()
    since30 = db.shift(db.now(), days=-30)
    stats = {}
    for key, biz in BUSINESSES.items():
        counts = dict(c.execute("SELECT status, COUNT(*) FROM contacts WHERE business = ?"
                                " GROUP BY status", (key,)).fetchall())
        s30 = dict(c.execute("SELECT status, COUNT(*) FROM sends WHERE business = ?"
                             " AND sent_at >= ? GROUP BY status", (key, since30)).fetchall())
        stats[key] = {
            "subscribed": counts.get("subscribed", 0),
            "unsubscribed": counts.get("unsubscribed", 0),
            "bounced": counts.get("bounced", 0),
            "sent_24h": sent_last_24h(c, key),
            "sent_30d": s30.get("sent", 0),
            "failed_30d": s30.get("failed", 0),
            "active_enrollments": c.execute(
                "SELECT COUNT(*) FROM enrollments e JOIN sequences s ON s.id = e.sequence_id"
                " WHERE s.business = ? AND e.status = 'active'", (key,)).fetchone()[0],
            "due_now": len(sequences_mod.due(c, key)),
        }
    return render_template("overview.html", stats=stats, biz=None)


@app.post("/run/sequences")
def run_sequences():
    live = request.form.get("mode") == "live"
    return start_job("Run sequences" + ("" if live else " (dry run)"),
                     lambda c, log: sequences_mod.run_sequences(c, dry_run=not live, log=log),
                     live=live)


@app.post("/run/sync")
def run_sync():
    return start_job("Check inboxes for unsubscribes and bounces",
                     lambda c, log: unsubscribes.sync_all(c, log=log), live=False)


@app.route("/activity")
def activity():
    key = request.args.get("business", "")
    sql = "SELECT * FROM sends"
    params = []
    if key in BUSINESSES:
        sql += " WHERE business = ?"
        params.append(key)
    rows = conn().execute(sql + " ORDER BY id DESC LIMIT 300", params).fetchall()
    return render_template("activity.html", rows=rows, current=key, biz=None)


# --- contacts --------------------------------------------------------------

@app.route("/b/<key>/contacts")
def contacts(key):
    biz = business(key)
    q = request.args.get("q", "").strip()
    tag = db.clean_tag(request.args.get("tag", ""))
    status = request.args.get("status", "")
    sql = "SELECT * FROM contacts WHERE business = ?"
    params: list = [key]
    if q:
        sql += " AND (email LIKE ? OR name LIKE ? OR suburb LIKE ?)"
        params += [f"%{q}%"] * 3
    if tag:
        sql += " AND tags LIKE ?"
        params.append(f"%,{tag},%")
    if status in ("subscribed", "unsubscribed", "bounced"):
        sql += " AND status = ?"
        params.append(status)
    rows = conn().execute(sql + " ORDER BY id DESC LIMIT 500", params).fetchall()
    total = conn().execute("SELECT COUNT(*) FROM contacts WHERE business = ?", (key,)).fetchone()[0]
    all_tags = sorted({t for r in conn().execute("SELECT tags FROM contacts WHERE business = ?",
                                                 (key,)) for t in db.tag_list(r[0])})
    return render_template("contacts.html", biz=biz, section="contacts", rows=rows, total=total,
                           q=q, tag=tag, status=status, all_tags=all_tags)


@app.post("/b/<key>/contacts")
def add_contact(key):
    business(key)
    f = request.form
    result = contacts_mod.upsert(conn(), key, f.get("email", ""), name=f.get("name", ""),
                                 phone=f.get("phone", ""), suburb=f.get("suburb", ""),
                                 tags=f.get("tags", ""), source="dashboard")
    conn().commit()
    flash({"added": "Contact added.", "updated": "That email was already on the list; "
           "details merged.", "invalid": "That email address doesn't look valid."}[result],
          "error" if result == "invalid" else "ok")
    return redirect(url_for("contacts", key=key))


@app.post("/b/<key>/contacts/import")
def import_contacts(key):
    business(key)
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Choose a CSV file to import.", "error")
        return redirect(url_for("contacts", key=key))
    text = upload.read().decode("utf-8-sig", errors="replace")
    try:
        counts = contacts_mod.import_csv(conn(), key, text, request.form.get("tags", ""),
                                         source=f"csv:{upload.filename}")
    except (ValueError, UnicodeError) as e:
        flash(f"Import failed: {e}", "error")
    else:
        flash(f"Imported {upload.filename}: {counts['added']} added, {counts['updated']} "
              f"updated, {counts['invalid']} skipped (invalid email).", "ok")
    return redirect(url_for("contacts", key=key))


@app.post("/b/<key>/contacts/<int:cid>")
def update_contact(key, cid):
    business(key)
    row = one("SELECT * FROM contacts WHERE id = ? AND business = ?", cid, key)
    action = request.form.get("action")
    c = conn()
    if action == "tags":
        c.execute("UPDATE contacts SET tags = ?, updated_at = ? WHERE id = ?",
                  (db.store_tags(request.form.get("tags", "")), db.now(), cid))
    elif action in ("unsubscribe", "resubscribe"):
        new = "unsubscribed" if action == "unsubscribe" else "subscribed"
        c.execute("UPDATE contacts SET status = ?, updated_at = ? WHERE id = ?",
                  (new, db.now(), cid))
        flash(f"{row['email']} is now {new}.", "ok")
    c.commit()
    return redirect(request.referrer or url_for("contacts", key=key))


# --- templates -------------------------------------------------------------

@app.route("/b/<key>/templates")
def templates(key):
    biz = business(key)
    rows = conn().execute("SELECT * FROM templates WHERE business = ? ORDER BY name",
                          (key,)).fetchall()
    return render_template("templates_list.html", biz=biz, section="templates", rows=rows)


@app.route("/b/<key>/templates/new", methods=["GET", "POST"])
@app.route("/b/<key>/templates/<int:tid>", methods=["GET", "POST"])
def template_edit(key, tid=None):
    biz = business(key)
    row = one("SELECT * FROM templates WHERE id = ? AND business = ?", tid, key) if tid else None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").replace("\r\n", "\n").strip()
        if not (name and subject and body):
            flash("Name, subject and body are all required.", "error")
        else:
            c = conn()
            try:
                if row:
                    c.execute("UPDATE templates SET name = ?, subject = ?, body = ?, updated_at = ?"
                              " WHERE id = ?", (name, subject, body, db.now(), tid))
                else:
                    tid = c.execute("INSERT INTO templates (business, name, subject, body)"
                                    " VALUES (?, ?, ?, ?)", (key, name, subject, body)).lastrowid
                c.commit()
            except db.sqlite3.IntegrityError:
                flash(f"There is already a template called '{name}'.", "error")
            else:
                flash("Template saved.", "ok")
                return redirect(url_for("template_edit", key=key, tid=tid))
        row = {"id": tid, "name": name, "subject": subject, "body": body}
    preview = render_email(biz, row["subject"], row["body"], SAMPLE_CONTACT) if row else None
    return render_template("template_edit.html", biz=biz, section="templates", row=row,
                           preview=preview)


@app.route("/b/<key>/templates/<int:tid>/preview")
def template_preview(key, tid):
    biz = business(key)
    row = one("SELECT * FROM templates WHERE id = ? AND business = ?", tid, key)
    return render_email(biz, row["subject"], row["body"], SAMPLE_CONTACT).html


@app.post("/b/<key>/templates/<int:tid>/test")
def template_test(key, tid):
    biz = business(key)
    row = one("SELECT * FROM templates WHERE id = ? AND business = ?", tid, key)
    to = request.form.get("to", "").strip()
    if not contacts_mod.valid_email(to):
        flash("Enter a valid address for the test email.", "error")
    else:
        try:
            r = render_email(biz, row["subject"], row["body"], SAMPLE_CONTACT)
            r.subject = f"[TEST] {r.subject}"
            with Mailer(biz, dry_run=False) as m:
                m.send(to, r)
            flash(f"Test email sent to {to} from {biz.gmail_address}.", "ok")
        except Exception as e:
            flash(f"Test send failed: {type(e).__name__}: {e}", "error")
    return redirect(url_for("template_edit", key=key, tid=tid))


# --- campaigns -------------------------------------------------------------

@app.route("/b/<key>/campaigns", methods=["GET", "POST"])
def campaigns(key):
    biz = business(key)
    c = conn()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        tid = request.form.get("template_id", type=int)
        one("SELECT id FROM templates WHERE id = ? AND business = ?", tid, key)
        if not name:
            flash("Give the campaign a name.", "error")
        else:
            cid = c.execute("INSERT INTO campaigns (business, name, template_id, tag)"
                            " VALUES (?, ?, ?, ?)",
                            (key, name, tid, db.clean_tag(request.form.get("tag", "")))).lastrowid
            c.commit()
            return redirect(url_for("campaign", key=key, cid=cid))
    rows = c.execute(
        "SELECT ca.*, t.name AS template_name,"
        " (SELECT COUNT(*) FROM sends s WHERE s.campaign_id = ca.id AND s.status = 'sent') AS sent,"
        " (SELECT COUNT(*) FROM sends s WHERE s.campaign_id = ca.id AND s.status = 'failed') AS failed"
        " FROM campaigns ca JOIN templates t ON t.id = ca.template_id"
        " WHERE ca.business = ? ORDER BY ca.id DESC", (key,)).fetchall()
    tpls = c.execute("SELECT id, name FROM templates WHERE business = ? ORDER BY name",
                     (key,)).fetchall()
    return render_template("campaigns.html", biz=biz, section="campaigns", rows=rows, tpls=tpls)


@app.route("/b/<key>/campaigns/<int:cid>")
def campaign(key, cid):
    biz = business(key)
    row = one("SELECT ca.*, t.name AS template_name FROM campaigns ca"
              " JOIN templates t ON t.id = ca.template_id WHERE ca.id = ? AND ca.business = ?",
              cid, key)
    pending = campaigns_mod.pending_recipients(conn(), row)
    sends = conn().execute("SELECT * FROM sends WHERE campaign_id = ? ORDER BY id DESC LIMIT 200",
                           (cid,)).fetchall()
    return render_template("campaign.html", biz=biz, section="campaigns", row=row,
                           pending=pending, sends=sends,
                           remaining_today=max(0, biz.daily_limit - sent_last_24h(conn(), key)))


@app.post("/b/<key>/campaigns/<int:cid>/send")
def campaign_send(key, cid):
    business(key)
    row = one("SELECT * FROM campaigns WHERE id = ? AND business = ?", cid, key)
    live = request.form.get("mode") == "live"
    return start_job(f"Campaign '{row['name']}'" + ("" if live else " (dry run)"),
                     lambda c, log: campaigns_mod.send_campaign(c, cid, dry_run=not live, log=log),
                     live=live)


# --- sequences -------------------------------------------------------------

@app.route("/b/<key>/sequences", methods=["GET", "POST"])
def sequences(key):
    biz = business(key)
    c = conn()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        trigger = db.clean_tag(request.form.get("trigger_tag", ""))
        if not (name and trigger):
            flash("A sequence needs a name and a trigger tag.", "error")
        else:
            try:
                sid = c.execute("INSERT INTO sequences (business, name, trigger_tag, exit_tags)"
                                " VALUES (?, ?, ?, ?)",
                                (key, name, trigger,
                                 db.store_tags(request.form.get("exit_tags", "")))).lastrowid
                c.commit()
                return redirect(url_for("sequence", key=key, sid=sid))
            except db.sqlite3.IntegrityError:
                flash(f"There is already a sequence called '{name}'.", "error")
    rows = c.execute(
        "SELECT s.*,"
        " (SELECT COUNT(*) FROM sequence_steps st WHERE st.sequence_id = s.id) AS steps,"
        " (SELECT COUNT(*) FROM enrollments e WHERE e.sequence_id = s.id AND e.status = 'active') AS active_n,"
        " (SELECT COUNT(*) FROM enrollments e WHERE e.sequence_id = s.id AND e.status = 'completed') AS completed_n"
        " FROM sequences s WHERE s.business = ? ORDER BY s.name", (key,)).fetchall()
    return render_template("sequences.html", biz=biz, section="sequences", rows=rows)


@app.route("/b/<key>/sequences/<int:sid>", methods=["GET", "POST"])
def sequence(key, sid):
    biz = business(key)
    c = conn()
    seq = one("SELECT * FROM sequences WHERE id = ? AND business = ?", sid, key)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "settings":
            trigger = db.clean_tag(request.form.get("trigger_tag", "")) or seq["trigger_tag"]
            c.execute("UPDATE sequences SET trigger_tag = ?, exit_tags = ?, active = ? WHERE id = ?",
                      (trigger, db.store_tags(request.form.get("exit_tags", "")),
                       1 if request.form.get("active") else 0, sid))
            flash("Sequence saved.", "ok")
        elif action == "add_step":
            tid = request.form.get("template_id", type=int)
            one("SELECT id FROM templates WHERE id = ? AND business = ?", tid, key)
            delay = max(0, request.form.get("delay_days", type=int) or 0)
            pos = c.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM sequence_steps"
                            " WHERE sequence_id = ?", (sid,)).fetchone()[0]
            c.execute("INSERT INTO sequence_steps (sequence_id, position, delay_days, template_id)"
                      " VALUES (?, ?, ?, ?)", (sid, pos, delay, tid))
            flash("Step added.", "ok")
        elif action == "delete_step":
            c.execute("DELETE FROM sequence_steps WHERE id = ? AND sequence_id = ?",
                      (request.form.get("step_id", type=int), sid))
            flash("Step removed.", "ok")
        c.commit()
        return redirect(url_for("sequence", key=key, sid=sid))
    steps = c.execute("SELECT st.*, t.name AS template_name FROM sequence_steps st"
                      " JOIN templates t ON t.id = st.template_id WHERE st.sequence_id = ?"
                      " ORDER BY st.position", (sid,)).fetchall()
    enrolled = c.execute("SELECT e.*, ct.email, ct.name FROM enrollments e"
                         " JOIN contacts ct ON ct.id = e.contact_id WHERE e.sequence_id = ?"
                         " ORDER BY e.status, e.next_due_at LIMIT 300", (sid,)).fetchall()
    tpls = c.execute("SELECT id, name FROM templates WHERE business = ? ORDER BY name",
                     (key,)).fetchall()
    return render_template("sequence.html", biz=biz, section="sequences", seq=seq, steps=steps,
                           enrolled=enrolled, tpls=tpls)
