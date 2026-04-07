import datetime
import logging
import os
import sys
import threading

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)

_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_STARTED = False
_SCHEDULER_STOP_EVENT = threading.Event()
_SCHEDULER_SKIP_COMMANDS = {
    'makemigrations',
    'migrate',
    'collectstatic',
    'shell',
    'dbshell',
    'createsuperuser',
    'changepassword',
    'test',
}


def years_ago(reference_date, years):
    try:
        return reference_date.replace(year=reference_date.year - years)
    except ValueError:
        return reference_date.replace(month=2, day=28, year=reference_date.year - years)


def age_on_date(birthdate, reference_date=None):
    if not birthdate:
        return None
    reference_date = reference_date or datetime.date.today()
    return reference_date.year - birthdate.year - (
        (reference_date.month, reference_date.day) < (birthdate.month, birthdate.day)
    )


def is_birthdate_aged_out(birthdate, reference_date=None):
    if not birthdate:
        return False
    reference_date = reference_date or datetime.date.today()
    return birthdate <= years_ago(reference_date, 31)


def oldest_allowed_birthdate(reference_date=None):
    reference_date = reference_date or datetime.date.today()
    return years_ago(reference_date, 31) + datetime.timedelta(days=1)


def purge_aged_out_youths(reference_date=None):
    from .models import Youth

    reference_date = reference_date or datetime.date.today()
    cutoff = years_ago(reference_date, 31)
    deleted_count, _ = Youth.objects.filter(
        birthdate__isnull=False,
        birthdate__lte=cutoff,
    ).delete()
    return deleted_count


def _should_skip_scheduler_start():
    if os.environ.get('LYDO_DISABLE_AGE_OUT_SCHEDULER') == '1':
        return True
    if getattr(settings, 'DEBUG', False) and os.environ.get('RUN_MAIN') != 'true':
        return True
    if any(command in sys.argv for command in _SCHEDULER_SKIP_COMMANDS):
        return True
    return False


def _cleanup_interval_seconds():
    return max(300, int(getattr(settings, 'AGE_OUT_CLEANUP_INTERVAL_SECONDS', 3600)))


def _cleanup_loop():
    interval_seconds = _cleanup_interval_seconds()
    while not _SCHEDULER_STOP_EVENT.is_set():
        try:
            close_old_connections()
            deleted_count = purge_aged_out_youths()
            if deleted_count:
                logger.info("Age-out cleanup removed %s youth record(s).", deleted_count)
        except Exception:
            logger.exception("Age-out cleanup job failed.")
        finally:
            close_old_connections()

        if _SCHEDULER_STOP_EVENT.wait(interval_seconds):
            break


def start_aged_out_cleanup_scheduler():
    global _SCHEDULER_STARTED

    if _should_skip_scheduler_start():
        return False

    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return False

        worker = threading.Thread(
            target=_cleanup_loop,
            name='lydo-age-out-cleanup',
            daemon=True,
        )
        worker.start()
        _SCHEDULER_STARTED = True
        return True
