# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Test fixtures for the TurnoverCal integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.calendar import CalendarEvent

if TYPE_CHECKING:
    from datetime import datetime


@pytest.fixture
def mock_calendar_entity() -> MagicMock:
    """Create a mock Rental Control calendar entity."""
    entity = MagicMock()
    entity.entity_id = "calendar.rental_control"
    entity.state = "off"
    entity.async_get_events = AsyncMock(side_effect=lambda *_a, **_k: [])
    return entity


@pytest.fixture
def mock_keymaster_event() -> dict[str, Any]:
    """Create a mock keymaster event payload with default values."""
    return {
        "code_slot_num": 4,
        "entity_id": "lock.front_door",
        "state": "locked",
    }


def build_calendar_event(
    start: datetime,
    end: datetime,
    summary: str,
    description: str = "",
) -> CalendarEvent:
    """Create a CalendarEvent with the given parameters."""
    return CalendarEvent(
        start=start,
        end=end,
        summary=summary,
        description=description,
    )
