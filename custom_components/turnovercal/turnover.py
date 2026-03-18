# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Turnover calculation and UID generation.

Stub module: implementation pending (Phase 2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.components.calendar import CalendarEvent

    from custom_components.turnovercal.models import TurnoverEvent


def generate_uid(checkout_id: str, checkin_id: str) -> str:
    """Generate a deterministic UID from checkout and checkin event IDs."""
    raise NotImplementedError


def generate_trailing_uid(checkout_id: str) -> str:
    """Generate a deterministic UID for a trailing turnover event."""
    raise NotImplementedError


def compute_turnover_events(
    events: list[CalendarEvent],
    summary_prefix: str,
    property_name: str,
    trailing_duration_hours: int,
    timezone_str: str,
) -> list[TurnoverEvent]:
    """Compute turnover events from a list of calendar events."""
    raise NotImplementedError
