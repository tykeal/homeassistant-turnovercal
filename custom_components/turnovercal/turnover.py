# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Turnover calculation and UID generation."""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, cast
from zoneinfo import ZoneInfo

from custom_components.turnovercal.models import TurnoverEvent

if TYPE_CHECKING:
    from homeassistant.components.calendar import CalendarEvent

_LOGGER = logging.getLogger(__name__)
_TRAILING_SENTINEL = "TRAILING"


def _as_datetime(value: date | datetime) -> datetime:
    """Ensure a date-or-datetime value is a datetime.

    CalendarEvent.start/end may be date or datetime; this helper
    narrows the type for use in turnover calculations.
    """
    return cast("datetime", value)


def generate_uid(checkout_id: str, checkin_id: str) -> str:
    """Generate a deterministic UID from checkout and checkin event IDs.

    Produces a 16-character hex digest followed by the domain suffix.
    """
    digest = hashlib.sha256(f"{checkout_id}{checkin_id}".encode()).hexdigest()[:16]
    return f"{digest}@turnovercal.homeassistant"


def generate_trailing_uid(checkout_id: str) -> str:
    """Generate a deterministic UID for a trailing turnover event.

    Uses a TRAILING sentinel as the checkin identifier.
    """
    return generate_uid(checkout_id, _TRAILING_SENTINEL)


def _source_id(event: CalendarEvent) -> str:
    """Derive a stable source identifier from a CalendarEvent."""
    return f"{event.summary}|{event.start.isoformat()}"


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
    """
    if not events:
        return []

    sorted_events = sorted(events, key=lambda e: e.start)
    summary = f"{summary_prefix} - {property_name}"
    result: list[TurnoverEvent] = []
    now_utc = datetime.now(tz=ZoneInfo("UTC"))

    for i in range(len(sorted_events) - 1):
        checkout_event = sorted_events[i]
        checkin_event = sorted_events[i + 1]
        checkout_time = _as_datetime(checkout_event.end)
        checkin_time = _as_datetime(checkin_event.start)

        if checkout_time > checkin_time:
            _LOGGER.warning(
                "Overlap detected between '%s' and '%s'; skipping pair",
                checkout_event.summary,
                checkin_event.summary,
            )
            continue

        src_checkout = _source_id(checkout_event)
        src_checkin = _source_id(checkin_event)

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
    src_last = _source_id(last_event)
    last_end = _as_datetime(last_event.end)
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
