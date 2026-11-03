"""Command line for the marketing engine. Run `python -m engine --help`.

Everything that sends is a dry run unless you pass --live.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import campaigns, contacts, db, sequences, unsubscribes
from .config import BUSINESSES, get_business
from .mailer import Mailer, NotConfigured
from .seed import seed


# The scheduled job runs every 15 minutes, day and night. Sequence emails only go
# out between these hours (this PC's local time); anything due overnight waits.
SEND_FROM_HOUR, SEND_UNTIL_HOUR = 8, 19


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def cmd_init(conn, args) -> int:
    seed(conn)
    log(f"Database ready at {db.DB_PATH}; starter templates and sequences added")
    return 0


def cmd_check(conn, args) -> int:
    ok = True
    for biz in BUSINESSES.values():
        if not biz.configured:
            log(f"[{biz.key}] NOT CONFIGURED: set {biz.env_prefix}_GMAIL_ADDRESS and "
                f"{biz.env_prefix}_GMAIL_APP_PASSWORD in .env")
            ok = False
            continue
        try:
            with Mailer(biz, dry_run=False):
                pass
            log(f"[{biz.key}] Gmail login OK as {biz.gmail_address}")
        except Exception as e:
            log(f"[{biz.key}] Gmail login FAILED: {type(e).__name__}: {e}")
            ok = False
        if biz.profile_gaps:
            log(f"[{biz.key}] businesses.json is missing: {', '.join(biz.profile_gaps)}")
    return 0 if ok else 1


def cmd_import(conn, args) -> int:
    get_business(args.business)
    text = Path(args.csv).read_text(encoding="utf-8-sig")
    counts = contacts.import_csv(conn, args.business, text, args.tag,
                                 source=f"csv:{Path(args.csv).name}")
    log(f"[{args.business}] added {counts['added']}, updated {counts['updated']}, "
        f"skipped {counts['invalid']} invalid")
    return 0


def cmd_campaign(conn, args) -> int:
    run = campaigns.send_campaign(conn, args.id, dry_run=not args.live, log=log)
    return 1 if run.failed else 0


def cmd_tick(conn, args) -> int:
    if args.live:
        unsubscribes.sync_all(conn, log=log)
    if args.live and not args.any_time and not SEND_FROM_HOUR <= datetime.now().hour < SEND_UNTIL_HOUR:
        log(f"Outside sending hours ({SEND_FROM_HOUR}:00 to {SEND_UNTIL_HOUR}:00); "
            f"due emails wait for the next run inside them")
        return 0
    runs = sequences.run_sequences(conn, dry_run=not args.live, log=log)
    return 1 if any(r.failed for r in runs) else 0


def cmd_sync(conn, args) -> int:
    unsubscribes.sync_all(conn, log=log)
    return 0


def cmd_serve(conn, args) -> int:
    from .web import app
    log(f"Dashboard on http://127.0.0.1:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m engine", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the database and starter templates/sequences")
    sub.add_parser("check", help="test the Gmail login for each business")
    s = sub.add_parser("import", help="import contacts from a CSV file")
    s.add_argument("business", choices=list(BUSINESSES))
    s.add_argument("csv")
    s.add_argument("--tag", default="", help="tag(s) to add to every imported contact, e.g. quote")
    s = sub.add_parser("campaign", help="send a campaign by id")
    s.add_argument("id", type=int)
    s.add_argument("--live", action="store_true", help="really send (default is a dry run)")
    s = sub.add_parser("tick", help="scheduled job: check inboxes, then run sequences")
    s.add_argument("--live", action="store_true", help="really send (default is a dry run)")
    s.add_argument("--any-time", action="store_true",
                   help=f"send even outside {SEND_FROM_HOUR}:00 to {SEND_UNTIL_HOUR}:00")
    sub.add_parser("sync-unsubscribes", help="apply unsubscribes and bounces from both inboxes")
    s = sub.add_parser("serve", help="start the dashboard")
    s.add_argument("--port", type=int, default=5050)
    args = p.parse_args(argv)

    handlers = {"init": cmd_init, "check": cmd_check, "import": cmd_import,
                "campaign": cmd_campaign, "tick": cmd_tick,
                "sync-unsubscribes": cmd_sync, "serve": cmd_serve}
    conn = db.connect()
    try:
        return handlers[args.cmd](conn, args)
    except (ValueError, NotConfigured, FileNotFoundError) as e:
        log(f"ERROR: {e}")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
