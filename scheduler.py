# =============================================================================
# FILE: scheduler.py
# AURA Proactive Scheduler Daemon
#
# Lets AURA act without you prompting it:
#   - "remind me at 9am every day to drink water"
#   - "check Hacker News headlines every hour"
#   - "run a deep research on AI trends every Monday"
#   - "check CPU temperature every 5 minutes"
#
# Scheduled tasks persist in scheduler_jobs.json across restarts.
#
# Requirements:
#   pip install apscheduler
# =============================================================================

import os
import re
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Callable, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# ── APScheduler import ────────────────────────────────────────────────────────
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.jobstores.memory import MemoryJobStore
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler not installed. Run: pip install apscheduler")


JOBS_FILE = Path("scheduler_jobs.json")


# =============================================================================
# JOB DEFINITIONS
# =============================================================================

class ScheduledJob:
    """
    Represents a single scheduled task.
    Persisted to scheduler_jobs.json so it survives restarts.
    """

    def __init__(
        self,
        job_id:   str,
        name:     str,
        task:     str,          # natural language description of what to do
        trigger:  str,          # human-readable: "daily at 09:00", "every 1 hour", etc.
        enabled:  bool = True,
        meta:     Dict = None,
        last_run: str  = None,
        next_run: str  = None,
    ):
        self.job_id   = job_id
        self.name     = name
        self.task     = task
        self.trigger  = trigger
        self.enabled  = enabled
        self.meta     = meta or {}
        self.last_run = last_run
        self.next_run = next_run

    def to_dict(self) -> Dict:
        return {
            "job_id":   self.job_id,
            "name":     self.name,
            "task":     self.task,
            "trigger":  self.trigger,
            "enabled":  self.enabled,
            "meta":     self.meta,
            "last_run": self.last_run,
            "next_run": self.next_run,
        }

    @staticmethod
    def from_dict(d: Dict) -> "ScheduledJob":
        return ScheduledJob(**d)


# =============================================================================
# TRIGGER PARSER
# Converts natural language schedules to APScheduler triggers
# =============================================================================

def parse_trigger(schedule_text: str):
    """
    Parse a human schedule string into an APScheduler trigger.
    Returns (trigger, human_summary) or raises ValueError.

    Supported patterns:
      "every 30 minutes"
      "every 2 hours"
      "every day at 09:00" / "daily at 9am"
      "every Monday at 08:00"
      "every weekday at 17:00"
      "once at 2024-01-15 14:30"
      "in 10 minutes"
    """
    low = schedule_text.lower().strip()

    # "every N minutes/hours/seconds"
    m = re.search(r'every\s+(\d+)\s+(second|minute|hour|day)s?', low)
    if m:
        n    = int(m.group(1))
        unit = m.group(2) + 's'
        kwargs = {unit: n}
        return IntervalTrigger(**kwargs), f"every {n} {unit}"

    # "every hour"
    if re.search(r'every\s+hour', low):
        return IntervalTrigger(hours=1), "every 1 hour"

    # "every day at HH:MM" / "daily at HH:MM" / "every day at Xam/pm"
    m = re.search(r'(?:every\s+day|daily)\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', low)
    if m:
        hour   = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm   = m.group(3)
        if ampm == 'pm' and hour < 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        return CronTrigger(hour=hour, minute=minute), f"daily at {hour:02d}:{minute:02d}"

    # "every Monday/Tuesday/... at HH:MM"
    days = {
        'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
        'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
    }
    for day_name, day_code in days.items():
        m = re.search(rf'every\s+{day_name}\s+at\s+(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)?', low)
        if m:
            hour   = int(m.group(1))
            minute = int(m.group(2) or 0)
            ampm   = m.group(3)
            if ampm == 'pm' and hour < 12:
                hour += 12
            return CronTrigger(day_of_week=day_code, hour=hour, minute=minute), \
                   f"every {day_name.title()} at {hour:02d}:{minute:02d}"

    # "every weekday at HH:MM"
    m = re.search(r'every\s+weekday\s+at\s+(\d{1,2})(?::(\d{2}))?', low)
    if m:
        hour   = int(m.group(1))
        minute = int(m.group(2) or 0)
        return CronTrigger(day_of_week='mon-fri', hour=hour, minute=minute), \
               f"weekdays at {hour:02d}:{minute:02d}"

    # "in N minutes/hours"
    m = re.search(r'in\s+(\d+)\s+(minute|hour)s?', low)
    if m:
        n    = int(m.group(1))
        unit = m.group(2)
        run_at = datetime.now() + (timedelta(minutes=n) if unit == 'minute' else timedelta(hours=n))
        return DateTrigger(run_date=run_at), f"once in {n} {unit}{'s' if n>1 else ''}"

    # "once at YYYY-MM-DD HH:MM" / "at HH:MM today"
    m = re.search(r'(?:once\s+)?at\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', low)
    if m:
        run_at = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
        return DateTrigger(run_date=run_at), f"once at {run_at.strftime('%Y-%m-%d %H:%M')}"

    m = re.search(r'(?:once\s+)?at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+today', low)
    if m:
        hour   = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm   = m.group(3)
        if ampm == 'pm' and hour < 12:
            hour += 12
        run_at = datetime.now().replace(hour=hour, minute=minute, second=0)
        return DateTrigger(run_date=run_at), f"today at {hour:02d}:{minute:02d}"

    raise ValueError(
        f"Could not parse schedule: '{schedule_text}'\n"
        "Examples: 'every 30 minutes', 'daily at 09:00', 'every Monday at 08:00', 'in 15 minutes'"
    )


# =============================================================================
# AURA SCHEDULER
# =============================================================================

class AuraScheduler:
    """
    Manages all of AURA's scheduled tasks.

    Usage:
        scheduler = AuraScheduler(on_trigger=my_handler)
        scheduler.start()
        scheduler.add_job("morning brief", "summarise today's news", "daily at 08:00")
    """

    def __init__(self, on_trigger: Optional[Callable] = None):
        """
        on_trigger(job: ScheduledJob) is called when a job fires.
        Inject your AURA response function here.
        """
        self._on_trigger = on_trigger
        self._jobs: Dict[str, ScheduledJob] = {}
        self._sched = None
        self._lock  = threading.Lock()
        self._started = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if not APSCHEDULER_AVAILABLE:
            logger.error("APScheduler not installed — scheduler disabled")
            return
        if self._started:
            return
        self._sched = BackgroundScheduler(
            jobstores={'default': MemoryJobStore()},
            timezone='local'
        )
        self._sched.start()
        self._started = True
        self._load_jobs()
        logger.info(f"📅 Scheduler started with {len(self._jobs)} job(s)")

    def stop(self):
        if self._sched and self._started:
            self._sched.shutdown(wait=False)
            self._started = False

    # ── Job management ────────────────────────────────────────────────────────

    def add_job(
        self,
        name:     str,
        task:     str,
        schedule: str,
        notify:   Optional[Callable] = None,
    ) -> ScheduledJob:
        """
        Add a new scheduled job.

        Args:
            name:     Short label, e.g. "morning briefing"
            task:     What AURA should do, e.g. "search for AI news and summarise"
            schedule: Human-readable schedule, e.g. "daily at 08:00"
            notify:   Optional override callback for this specific job

        Returns:
            ScheduledJob

        Raises:
            ValueError if schedule can't be parsed
            RuntimeError if scheduler not started
        """
        if not self._started:
            raise RuntimeError("Call scheduler.start() before adding jobs")

        trigger, summary = parse_trigger(schedule)
        job_id = f"aura_{re.sub(r'[^a-z0-9]', '_', name.lower())}_{len(self._jobs)}"

        job = ScheduledJob(
            job_id=job_id,
            name=name,
            task=task,
            trigger=summary,
            enabled=True,
        )

        def _fire():
            job.last_run = datetime.now().isoformat()
            logger.info(f"🔔 Scheduled job fired: {job.name}")
            cb = notify or self._on_trigger
            if cb:
                try:
                    cb(job)
                except Exception as e:
                    logger.error(f"Job callback error ({job.name}): {e}")
            self._save_jobs()

        self._sched.add_job(
            _fire,
            trigger=trigger,
            id=job_id,
            name=name,
            replace_existing=True,
            misfire_grace_time=300
        )

        # Update next_run
        aps_job = self._sched.get_job(job_id)
        if aps_job and aps_job.next_run_time:
            job.next_run = aps_job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            self._jobs[job_id] = job
        self._save_jobs()

        logger.info(f"✅ Scheduled: '{name}' — {summary}")
        return job

    def remove_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id not in self._jobs:
                return False
            try:
                self._sched.remove_job(job_id)
            except Exception:
                pass
            del self._jobs[job_id]
        self._save_jobs()
        return True

    def enable_job(self, job_id: str, enabled: bool = True):
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].enabled = enabled
        if enabled:
            self._sched.resume_job(job_id)
        else:
            self._sched.pause_job(job_id)
        self._save_jobs()

    def list_jobs(self) -> List[Dict]:
        """Return a list of job metadata dicts for display."""
        with self._lock:
            result = []
            for job in self._jobs.values():
                # Refresh next_run from scheduler
                aps_job = self._sched.get_job(job.job_id) if self._sched else None
                if aps_job and aps_job.next_run_time:
                    job.next_run = aps_job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                result.append(job.to_dict())
            return result

    # ── NL shortcut ───────────────────────────────────────────────────────────

    def schedule_from_text(self, text: str) -> str:
        """
        Parse a natural language scheduling request and create the job.

        Examples:
          "remind me every day at 9am to check emails"
          "search for AI news every Monday at 08:00"
          "run a system status check every 30 minutes"

        Returns a human-readable confirmation string.
        """
        # Extract schedule portion
        schedule_patterns = [
            r'(every\s+\w+(?:\s+at\s+[\d:apm]+)?)',
            r'(daily\s+at\s+[\d:apm]+)',
            r'(every\s+\d+\s+(?:minute|hour|day)s?)',
            r'(in\s+\d+\s+(?:minute|hour)s?)',
            r'(once\s+at\s+[\d\-:\s]+)',
        ]
        schedule = None
        for pat in schedule_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                schedule = m.group(1).strip()
                break

        if not schedule:
            return (
                "I couldn't find a schedule in that. Try:\n"
                "• 'every day at 09:00'\n"
                "• 'every 30 minutes'\n"
                "• 'every Monday at 08:00'\n"
                "• 'in 15 minutes'"
            )

        # The task is everything that isn't the schedule phrase
        task = text.replace(schedule, "").strip()
        task = re.sub(r'^(?:remind me to|schedule|run|do|check|please)\s+', '', task, flags=re.IGNORECASE).strip()
        if not task:
            task = text

        name = task[:40].strip()

        try:
            job = self.add_job(name=name, task=task, schedule=schedule)
            return (
                f"✅ Scheduled: **{job.name}**\n"
                f"📅 When: {job.trigger}\n"
                f"⏭️ Next run: {job.next_run or 'soon'}"
            )
        except ValueError as e:
            return f"Schedule error: {e}"

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_jobs(self):
        try:
            data = {jid: job.to_dict() for jid, job in self._jobs.items()}
            JOBS_FILE.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.warning(f"Could not save jobs: {e}")

    def _load_jobs(self):
        if not JOBS_FILE.exists():
            return
        try:
            data = json.loads(JOBS_FILE.read_text())
            for jid, jdict in data.items():
                try:
                    job = ScheduledJob.from_dict(jdict)
                    # Re-register with scheduler using stored trigger string
                    trigger, summary = parse_trigger(job.trigger)
                    job_copy = job  # capture

                    def _make_fire(j):
                        def _fire():
                            j.last_run = datetime.now().isoformat()
                            logger.info(f"🔔 Restored job fired: {j.name}")
                            if self._on_trigger:
                                try:
                                    self._on_trigger(j)
                                except Exception as e:
                                    logger.error(f"Restored job error ({j.name}): {e}")
                            self._save_jobs()
                        return _fire

                    self._sched.add_job(
                        _make_fire(job_copy),
                        trigger=trigger,
                        id=jid,
                        name=job.name,
                        replace_existing=True,
                        misfire_grace_time=300
                    )
                    self._jobs[jid] = job
                    logger.info(f"  ↩️ Restored: {job.name} ({job.trigger})")
                except Exception as e:
                    logger.warning(f"Could not restore job '{jid}': {e}")
        except Exception as e:
            logger.warning(f"Could not load jobs file: {e}")


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_scheduler: Optional[AuraScheduler] = None


def get_scheduler(on_trigger: Optional[Callable] = None) -> AuraScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AuraScheduler(on_trigger=on_trigger)
    if on_trigger and not _scheduler._on_trigger:
        _scheduler._on_trigger = on_trigger
    return _scheduler


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO)

    def on_fire(job):
        print(f"\n🔔 JOB FIRED: {job.name}\n   Task: {job.task}\n   At: {job.last_run}")

    s = AuraScheduler(on_trigger=on_fire)
    s.start()

    print(s.schedule_from_text("check the weather every 1 minute"))
    print(s.schedule_from_text("remind me to stretch in 2 minutes"))
    print("\nScheduled jobs:")
    for j in s.list_jobs():
        print(f"  [{j['job_id']}] {j['name']} — {j['trigger']} — next: {j['next_run']}")

    print("\nWaiting 3 minutes to see jobs fire... Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        s.stop()
        print("Done.")
