# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Turnover calculation and UID generation."""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from custom_components.turnovercal.models import TurnoverEvent

if TYPE_CHECKING:
    from homeassistant.components.calendar import CalendarEvent

_LOGGER = logging.getLogger(__name__)
_TRAILING_SENTINEL = "TRAILING"
_UID_SEPARATOR = "\x00"
_MIN_TRAILING_HOURS = 1
_MAX_TRAILING_HOURS = 24


def _as_datetime(value: date | datetime, tz: ZoneInfo) -> datetime:
    """Ensure a date-or-datetime value is a timezone-aware datetime.

    CalendarEvent.start/end may be date or datetime. All-day events
    (plain date) are converted to midnight in the given timezone.
    Naive datetimes are rejected to prevent mixed-offset arithmetic.

    Raises:
        TypeError: If value is neither date nor datetime.
        ValueError: If value is a naive (no tzinfo) datetime.

    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            msg = "Naive datetime not allowed; expected tz-aware"
            raise ValueError(msg)
        return value.astimezone(tz)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=tz)
    msg = f"Expected date or datetime, got {type(value).__name__}"
    raise TypeError(msg)


def generate_uid(checkout_id: str, checkin_id: str) -> str:
    """Generate a deterministic UID from checkout and checkin event IDs.

    Uses a null-byte separator to prevent concatenation collisions.
    Produces a 16-character hex digest followed by the domain suffix.
    """
    raw = f"{checkout_id}{_UID_SEPARATOR}{checkin_id}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{digest}@turnovercal.homeassistant"


def generate_trailing_uid(checkout_id: str) -> str:
    """Generate a deterministic UID for a trailing turnover event.

    Uses a TRAILING sentinel as the checkin identifier.
    """
    return generate_uid(checkout_id, _TRAILING_SENTINEL)


def _source_id(event: CalendarEvent, tz: ZoneInfo) -> str:
    """Derive a stable, PII-free source identifier from a CalendarEvent.

    Hashes the event summary and normalized start/end times to avoid
    storing guest PII and ensure timezone-independent stability.
    """
    start = _as_datetime(event.start, tz)
    end = _as_datetime(event.end, tz)
    raw = f"{event.summary}|{start.isoformat()}|{end.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def compute_turnover_events(
    events: list[CalendarEvent],
    summary_prefix: str,
    property_name: str,
    trailing_duration_hours: int,
    timezone_str: str,
) -> list[TurnoverEvent]:
    """Compute turnover events from a list of calendar events.

    For N consecutive guest stays, produces up to N-1 regular turnover
    events (one between each pair) plus one trailing event after the
    last guest departs. Overlapping pairs are skipped with a warning.

    Raises:
        ValueError: If trailing_duration_hours is outside 1-24 range.

    """
    if not (_MIN_TRAILING_HOURS <= trailing_duration_hours <= _MAX_TRAILING_HOURS):
        msg = (
            f"trailing_duration_hours must be between "
            f"{_MIN_TRAILING_HOURS} and {_MAX_TRAILING_HOURS}, "
            f"got {trailing_duration_hours}"
        )
        raise ValueError(msg)

    if not events:
        return []

    tz = ZoneInfo(timezone_str)
    sorted_events = sorted(events, key=lambda e: _as_datetime(e.start, tz))
    summary = f"{summary_prefix} - {property_name}"
    result: list[TurnoverEvent] = []
    now_utc = datetime.now(tz=ZoneInfo("UTC"))

    # Cache source IDs to avoid redundant hashing
    sid_cache: dict[int, str] = {}

    def _cached_source_id(event: CalendarEvent) -> str:
        """Return cached source ID for a CalendarEvent."""
        eid = id(event)
        if eid not in sid_cache:
            sid_cache[eid] = _source_id(event, tz)
        return sid_cache[eid]

    for i in range(len(sorted_events) - 1):
        checkout_event = sorted_events[i]
        checkin_event = sorted_events[i + 1]
        checkout_time = _as_datetime(checkout_event.end, tz)
        checkin_time = _as_datetime(checkin_event.start, tz)

        if checkout_time > checkin_time:
            _LOGGER.warning(
                "Overlap detected between events %s and %s; skipping pair",
                _cached_source_id(checkout_event)[:8],
                _cached_source_id(checkin_event)[:8],
            )
            continue

        src_checkout = _cached_source_id(checkout_event)
        src_checkin = _cached_source_id(checkin_event)

        result.append(
            TurnoverEvent(
                uid=generate_uid(src_checkout, src_checkin),
                summary=summary,
                dtstart=checkout_time,
                dtend=checkin_time,
                timezone=timezone_str,
                source_checkout_id=src_checkout,
                source_checkin_id=src_checkin,
                created_at=now_utc,
                is_trailing=False,
            )
        )

    # Trailing event for the last guest
    last_event = sorted_events[-1]
    src_last = _cached_source_id(last_event)
    last_end = _as_datetime(last_event.end, tz)
    result.append(
        TurnoverEvent(
            uid=generate_trailing_uid(src_last),
            summary=summary,
            dtstart=last_end,
            dtend=last_end + timedelta(hours=trailing_duration_hours),
            timezone=timezone_str,
            source_checkout_id=src_last,
            source_checkin_id=None,
            created_at=now_utc,
            is_trailing=True,
        )
    )

    return result
