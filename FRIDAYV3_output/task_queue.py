"""
task_queue.py — FRIDAY Background Task Queue

Allows scheduling functions to run after a delay, at a specific time,
or repeatedly at an interval — all in background daemon threads.

Used by:
  - set_timer()          → already uses threading; this gives a richer API
  - proactive_loop()     → email checks, download watcher alerts
  - future scheduled tasks ("remind me every Monday at 9am")

Usage:
    from task_queue import schedule, schedule_at, schedule_recurring, cancel

    # Run after 30 seconds
    tid = schedule(lambda: speak("Break time!"), delay=30, label="break")

    # Run at a specific datetime
    schedule_at(my_fn, when=datetime(2025, 6, 1, 9, 0), label="morning brief")

    # Run every 60 seconds
    schedule_recurring(check_emails, interval=60, label="email check")

    # Cancel a scheduled task
    cancel(tid)
"""

import threading
import time
import datetime
import uuid
from typing import Callable

# Registry of active tasks: task_id → threading.Event (set to cancel)
_tasks: dict[str, threading.Event] = {}
_tasks_lock = threading.Lock()


# ================= SCHEDULE (delay) =================

def schedule(
    fn:     Callable,
    delay:  float = 0,
    label:  str   = "task",
    args:   tuple = (),
    kwargs: dict  = None,
) -> str:
    """
    Run fn() after `delay` seconds in a background thread.

    Returns:
        task_id (str) — use with cancel() to abort before execution.
    """
    if kwargs is None:
        kwargs = {}

    task_id    = str(uuid.uuid4())[:8]
    cancel_evt = threading.Event()

    with _tasks_lock:
        _tasks[task_id] = cancel_evt

    def _run():
        if delay > 0:
            # Sleep in small increments so cancel() can interrupt
            deadline = time.time() + delay
            while time.time() < deadline:
                if cancel_evt.is_set():
                    print(f"[TASK QUEUE] Cancelled: {label} ({task_id})")
                    _cleanup(task_id)
                    return
                time.sleep(min(1.0, deadline - time.time()))

        if not cancel_evt.is_set():
            print(f"[TASK QUEUE] Running: {label} ({task_id})")
            try:
                fn(*args, **kwargs)
            except Exception as e:
                print(f"[TASK QUEUE] Error in {label}: {e}")

        _cleanup(task_id)

    t = threading.Thread(target=_run, daemon=True, name=f"friday-task-{task_id}")
    t.start()
    print(f"[TASK QUEUE] Scheduled '{label}' in {delay}s (id={task_id})")
    return task_id


# ================= SCHEDULE AT (specific datetime) =================

def schedule_at(
    fn:     Callable,
    when:   datetime.datetime,
    label:  str  = "task",
    args:   tuple = (),
    kwargs: dict  = None,
) -> str:
    """
    Run fn() at a specific datetime.

    Returns:
        task_id (str)
    """
    now   = datetime.datetime.now()
    delay = (when - now).total_seconds()

    if delay < 0:
        print(f"[TASK QUEUE] Warning: '{label}' scheduled time is in the past.")
        delay = 0

    return schedule(fn, delay=delay, label=label, args=args, kwargs=kwargs)


# ================= SCHEDULE RECURRING =================

def schedule_recurring(
    fn:       Callable,
    interval: float,
    label:    str   = "recurring",
    args:     tuple = (),
    kwargs:   dict  = None,
    run_immediately: bool = False,
) -> str:
    """
    Run fn() every `interval` seconds until cancelled.

    Args:
        interval:       Seconds between each run.
        run_immediately: If True, run once before the first wait.

    Returns:
        task_id (str)
    """
    if kwargs is None:
        kwargs = {}

    task_id    = str(uuid.uuid4())[:8]
    cancel_evt = threading.Event()

    with _tasks_lock:
        _tasks[task_id] = cancel_evt

    def _run():
        if run_immediately and not cancel_evt.is_set():
            try:
                fn(*args, **kwargs)
            except Exception as e:
                print(f"[TASK QUEUE] Error in {label}: {e}")

        while not cancel_evt.is_set():
            # Wait for `interval` seconds, checking cancel every second
            deadline = time.time() + interval
            while time.time() < deadline:
                if cancel_evt.is_set():
                    break
                time.sleep(min(1.0, deadline - time.time()))

            if cancel_evt.is_set():
                break

            print(f"[TASK QUEUE] Running recurring: {label} ({task_id})")
            try:
                fn(*args, **kwargs)
            except Exception as e:
                print(f"[TASK QUEUE] Error in {label}: {e}")

        print(f"[TASK QUEUE] Recurring task stopped: {label} ({task_id})")
        _cleanup(task_id)

    t = threading.Thread(target=_run, daemon=True, name=f"friday-recurring-{task_id}")
    t.start()
    print(f"[TASK QUEUE] Recurring '{label}' every {interval}s (id={task_id})")
    return task_id


# ================= CANCEL =================

def cancel(task_id: str) -> bool:
    """
    Cancel a scheduled or recurring task by ID.

    Returns:
        True if the task was found and cancelled, False if not found.
    """
    with _tasks_lock:
        evt = _tasks.get(task_id)

    if evt:
        evt.set()
        print(f"[TASK QUEUE] Cancel requested for task {task_id}")
        return True

    print(f"[TASK QUEUE] Task not found: {task_id}")
    return False


def cancel_all():
    """Cancel every active scheduled/recurring task."""
    with _tasks_lock:
        ids = list(_tasks.keys())
    for tid in ids:
        cancel(tid)
    print(f"[TASK QUEUE] Cancelled all {len(ids)} tasks.")


# ================= HELPERS =================

def _cleanup(task_id: str):
    with _tasks_lock:
        _tasks.pop(task_id, None)


def list_tasks() -> list[dict]:
    """Return info about all currently active tasks."""
    with _tasks_lock:
        return [{"id": tid, "cancelled": evt.is_set()} for tid, evt in _tasks.items()]


# ================= PROACTIVE LOOP =================

def start_proactive_loop():
    """
    Start FRIDAY's proactive agent loop.
    Checks for new emails every 5 minutes and alerts the user.
    Add more checks here as needed.

    Call this from main.py after startup:
        from task_queue import start_proactive_loop
        start_proactive_loop()
    """
    def _check_emails():
        try:
            from gmail_plugin import get_unread_count
            count = get_unread_count()
            if count and count > 0:
                from brain_v4 import process_command
                process_command(f"tell me I have {count} new unread emails")
        except Exception:
            pass  # Gmail not configured — silently skip

    schedule_recurring(
        fn=_check_emails,
        interval=300,           # every 5 minutes
        label="email check",
        run_immediately=False,  # don't fire on startup
    )

    print("[TASK QUEUE] Proactive loop started.")
