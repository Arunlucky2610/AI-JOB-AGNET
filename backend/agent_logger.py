"""Structured persistent logging for Orbit AI agent runs and application executions."""
import os, json, logging, traceback
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / 'data'
LOG_FILE = LOG_DIR / 'orbit_agent.log'
JSONL_FILE = LOG_DIR / 'orbit_agent.jsonl'

# Configure standard Python logger
logger = logging.getLogger('orbit_agent')
logger.setLevel(logging.INFO)

if not logger.handlers:
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [Orbit] %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(LOG_FILE), encoding='utf-8')
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        logger.warning(f"Could not initialize file handler for {LOG_FILE}: {e}")

def log_event(stage: str, message: str, run_id: str = None, app_id: str = None, job_id: str = None, outcome: str = None, exc: Exception = None):
    """Write a persistent structured entry to the log file and console."""
    entry = {
        'time': datetime.now(timezone.utc).isoformat(),
        'stage': stage,
        'message': message,
        'run_id': run_id,
        'app_id': app_id,
        'job_id': job_id,
        'outcome': outcome,
    }
    if exc is not None:
        entry['exception_type'] = type(exc).__name__
        entry['exception_message'] = str(exc)
        entry['traceback'] = traceback.format_exc()

    log_line = f"stage={stage} run_id={run_id or '-'} app_id={app_id or '-'} outcome={outcome or '-'} :: {message}"
    if exc:
        log_line += f" | {type(exc).__name__}: {exc}"
        logger.error(log_line)
    else:
        logger.info(log_line)

    # Append JSON line to structured jsonl file for automated auditability
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(str(JSONL_FILE), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass
