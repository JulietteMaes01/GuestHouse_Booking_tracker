"""
run.py
──────
Orchestrator: parses new elloha emails, then regenerates and pushes the HTML
schedule.  Run this daily (manually or via cron / launchd).

    python run.py

Optional flags:
    python run.py --emails-only    # only parse emails
    python run.py --schedule-only  # only generate/push schedule
"""
import sys
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

args = sys.argv[1:]
do_emails   = "--schedule-only" not in args
do_schedule = "--emails-only"   not in args

log.info("═" * 50)
log.info(f"  La Ferme de la Cour — Daily Update")
log.info(f"  {datetime.now().strftime('%A %d %B %Y, %H:%M')}")
log.info("═" * 50)

if do_emails:
    log.info("\n── Step 1: Parsing elloha emails ──")
    try:
        import email_parser
        email_parser.run()
    except Exception as exc:
        log.error(f"Email parsing failed: {exc}")

if do_schedule:
    log.info("\n── Step 2: Generating HTML schedule ──")
    try:
        import schedule_generator
        schedule_generator.run()
    except Exception as exc:
        log.error(f"Schedule generation failed: {exc}")

log.info("\nDone ✓")
