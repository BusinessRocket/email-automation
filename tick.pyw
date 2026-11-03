"""Scheduled job: apply unsubscribes and bounces from both inboxes, then send
due sequence emails. Task Scheduler runs it every 15 minutes with pythonw, so
no console window pops up (see README). Output goes to data/tick.log.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
(ROOT / "data").mkdir(exist_ok=True)

with open(ROOT / "data" / "tick.log", "a", encoding="utf-8") as log_file:
    sys.stdout = sys.stderr = log_file
    from engine.__main__ import main
    try:
        main(["tick", "--live"])
    except Exception:
        import traceback
        traceback.print_exc()
