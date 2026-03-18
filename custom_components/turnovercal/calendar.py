# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""TurnoverCalendar entity and iCal feed generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import icalendar

if TYPE_CHECKING:
    from custom_components.turnovercal.models import TurnoverEvent


def generate_ical(
    events: list[TurnoverEvent],
    timezone_str: str,
    summary_prefix: str,
    property_name: str,
) -> bytes:
    """Generate an RFC 5545 iCal feed from turnover events.

    Builds a VCALENDAR with proper properties and one VEVENT per
    turnover event. Adds VTIMEZONE automatically via the icalendar
    library.

    Args:
        events: List of TurnoverEvent instances to export.
        timezone_str: IANA timezone string for the property.
        summary_prefix: Prefix for the calendar name.
        property_name: Name of the property.

    Returns:
        RFC 5545 iCal data as bytes.

    """
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Home Assistant//TurnoverCal//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"{summary_prefix} - {property_name}")
    cal.add("x-wr-timezone", timezone_str)

    for evt in events:
        vevent = icalendar.Event()
        vevent.add("uid", evt.uid)
        vevent.add("dtstamp", evt.created_at)
        vevent.add("dtstart", evt.dtstart)
        vevent.add("dtend", evt.dtend)
        vevent.add("summary", evt.summary)
        vevent.add("description", "Cleaning window between guests")
        vevent.add("status", "CONFIRMED")
        cal.add_component(vevent)

    cal.add_missing_timezones()
    return cal.to_ical()
