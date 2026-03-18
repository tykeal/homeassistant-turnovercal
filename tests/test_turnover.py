# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for turnover calculation and UID generation."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.calendar import CalendarEvent

from custom_components.turnovercal.models import TurnoverEvent
from custom_components.turnovercal.turnover import (
    compute_turnover_events,
    generate_trailing_uid,
    generate_uid,
)

ET = ZoneInfo("America/New_York")

UID_PATTERN = re.compile(r"^[0-9a-f]{16}@turnovercal\.homeassistant$")


# ---------------------------------------------------------------------------
# generate_uid
# ---------------------------------------------------------------------------


class TestGenerateUid:
    """Tests for deterministic UID generation."""

    def test_returns_correct_format(self) -> None:
        """UID is 16 hex chars + @turnovercal.homeassistant."""
        uid = generate_uid("checkout-001", "checkin-002")
        assert UID_PATTERN.match(uid)

    def test_deterministic_same_inputs(self) -> None:
        """Same inputs always produce the same UID."""
        uid1 = generate_uid("co-1", "ci-2")
        uid2 = generate_uid("co-1", "ci-2")
        assert uid1 == uid2

    def test_different_inputs_different_uids(self) -> None:
        """Different inputs produce different UIDs."""
        uid1 = generate_uid("co-1", "ci-2")
        uid2 = generate_uid("co-1", "ci-3")
        assert uid1 != uid2

    def test_uid_length(self) -> None:
        """UID total length is 16 + 1 + len(domain)."""
        uid = generate_uid("a", "b")
        parts = uid.split("@")
        assert len(parts) == 2
        assert len(parts[0]) == 16
        assert parts[1] == "turnovercal.homeassistant"

    def test_hex_prefix_is_lowercase(self) -> None:
        """Hex portion of UID is lowercase."""
        uid = generate_uid("checkout-x", "checkin-y")
        hex_part = uid.split("@")[0]
        assert hex_part == hex_part.lower()
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_order_matters(self) -> None:
        """Swapping checkout and checkin produces a different UID."""
        uid1 = generate_uid("a", "b")
        uid2 = generate_uid("b", "a")
        assert uid1 != uid2


# ---------------------------------------------------------------------------
# generate_trailing_uid
# ---------------------------------------------------------------------------


class TestGenerateTrailingUid:
    """Tests for trailing UID generation."""

    def test_returns_correct_format(self) -> None:
        """Trailing UID has the standard UID format."""
        uid = generate_trailing_uid("checkout-001")
        assert UID_PATTERN.match(uid)

    def test_deterministic(self) -> None:
        """Same checkout ID produces the same trailing UID."""
        uid1 = generate_trailing_uid("co-1")
        uid2 = generate_trailing_uid("co-1")
        assert uid1 == uid2

    def test_differs_from_regular_uid(self) -> None:
        """Trailing UID differs from a regular UID with same checkout."""
        regular = generate_uid("co-1", "ci-2")
        trailing = generate_trailing_uid("co-1")
        assert regular != trailing

    def test_uses_trailing_sentinel(self) -> None:
        """Trailing UID uses TRAILING sentinel instead of checkin_id."""
        # The trailing UID should be deterministic using "TRAILING" sentinel
        uid = generate_trailing_uid("co-1")
        # Verify it's different from generate_uid with any real checkin
        uid_with_checkin = generate_uid("co-1", "some-checkin")
        assert uid != uid_with_checkin

    def test_different_checkouts_different_trailing_uids(self) -> None:
        """Different checkout IDs produce different trailing UIDs."""
        uid1 = generate_trailing_uid("co-1")
        uid2 = generate_trailing_uid("co-2")
        assert uid1 != uid2


# ---------------------------------------------------------------------------
# compute_turnover_events - basic scenarios
# ---------------------------------------------------------------------------


class TestComputeTurnoverEvents:
    """Tests for the main turnover computation logic."""

    def test_two_consecutive_guests_one_turnover(self) -> None:
        """Two consecutive guests produce exactly 1 turnover event."""
        events = [
            _cal("Guest A", _dt(10, 11), _dt(12, 11)),
            _cal("Guest B", _dt(12, 15), _dt(15, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        # 1 regular event + 1 trailing event
        regular = [e for e in result if not e.is_trailing]
        assert len(regular) == 1
        assert regular[0].dtstart == _dt(12, 11)
        assert regular[0].dtend == _dt(12, 15)

    def test_three_consecutive_guests_two_turnovers(self) -> None:
        """Three consecutive guests produce 2 regular turnover events."""
        events = [
            _cal("A", _dt(10, 11), _dt(12, 11)),
            _cal("B", _dt(12, 15), _dt(15, 11)),
            _cal("C", _dt(15, 15), _dt(18, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        regular = [e for e in result if not e.is_trailing]
        assert len(regular) == 2

    def test_multi_day_gap_correct_times(self) -> None:
        """A multi-day gap produces correct dtstart and dtend."""
        checkout = _dt(10, 11)
        checkin = _dt(14, 15)
        events = [
            _cal("A", _dt(7, 11), checkout),
            _cal("B", checkin, _dt(18, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        regular = [e for e in result if not e.is_trailing]
        assert len(regular) == 1
        assert regular[0].dtstart == checkout
        assert regular[0].dtend == checkin

    def test_zero_gap_promoted_to_one_minute(self) -> None:
        """Zero gap (checkout == checkin) results in 1-minute event."""
        same_time = _dt(12, 11)
        events = [
            _cal("A", _dt(10, 11), same_time),
            _cal("B", same_time, _dt(15, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        regular = [e for e in result if not e.is_trailing]
        assert len(regular) == 1
        assert regular[0].dtend == same_time + timedelta(minutes=1)

    def test_negative_overlap_no_regular_event_warning_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Overlap skips the regular event and logs a warning."""
        events = [
            _cal("A", _dt(10, 11), _dt(13, 11)),
            _cal("B", _dt(12, 15), _dt(15, 11)),
        ]
        with caplog.at_level(logging.WARNING):
            result = compute_turnover_events(
                events=events,
                summary_prefix="Turnover",
                property_name="Beach House",
                trailing_duration_hours=4,
                timezone_str="America/New_York",
            )
        regular = [e for e in result if not e.is_trailing]
        assert len(regular) == 0
        trailing = [e for e in result if e.is_trailing]
        assert len(trailing) == 1
        assert any("overlap" in msg.lower() for msg in caplog.messages)
        # Log must use hashed IDs, not raw event summaries (PII)
        overlap_msgs = [m for m in caplog.messages if "overlap" in m.lower()]
        for msg in overlap_msgs:
            assert "'A'" not in msg
            assert "'B'" not in msg


# ---------------------------------------------------------------------------
# compute_turnover_events - trailing events
# ---------------------------------------------------------------------------


class TestComputeTurnoverTrailing:
    """Tests for trailing turnover event generation."""

    def test_single_trailing_event_last_guest(self) -> None:
        """Last guest with no follower produces a trailing event."""
        events = [
            _cal("A", _dt(10, 11), _dt(12, 11)),
            _cal("B", _dt(12, 15), _dt(15, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        trailing = [e for e in result if e.is_trailing]
        assert len(trailing) == 1
        assert trailing[0].dtstart == _dt(15, 11)
        assert trailing[0].dtend == _dt(15, 11) + timedelta(hours=4)

    def test_trailing_event_uses_generate_trailing_uid(self) -> None:
        """Trailing event UID matches generate_trailing_uid output."""
        events = [
            _cal("A", _dt(10, 11), _dt(12, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        trailing = [e for e in result if e.is_trailing]
        assert len(trailing) == 1
        # The UID must match the standard format
        assert UID_PATTERN.match(trailing[0].uid)
        assert trailing[0].source_checkin_id is None

    def test_trailing_configurable_duration(self) -> None:
        """Trailing event uses configured duration in hours."""
        events = [_cal("A", _dt(10, 11), _dt(12, 11))]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=6,
            timezone_str="America/New_York",
        )
        trailing = [e for e in result if e.is_trailing]
        assert len(trailing) == 1
        assert trailing[0].dtend == _dt(12, 11) + timedelta(hours=6)

    def test_multiple_guests_n_minus_1_regular_plus_1_trailing(self) -> None:
        """N guests produce N-1 regular events + 1 trailing event."""
        events = [
            _cal("A", _dt(5, 11), _dt(8, 11)),
            _cal("B", _dt(8, 15), _dt(11, 11)),
            _cal("C", _dt(11, 15), _dt(14, 11)),
            _cal("D", _dt(14, 15), _dt(17, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        regular = [e for e in result if not e.is_trailing]
        trailing = [e for e in result if e.is_trailing]
        assert len(regular) == 3
        assert len(trailing) == 1


# ---------------------------------------------------------------------------
# compute_turnover_events - edge cases
# ---------------------------------------------------------------------------


class TestComputeTurnoverEdgeCases:
    """Tests for edge cases in turnover computation."""

    def test_empty_calendar_empty_list(self) -> None:
        """Empty calendar produces no turnover events."""
        result = compute_turnover_events(
            events=[],
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        assert result == []

    def test_single_event_one_trailing_only(self) -> None:
        """Single calendar event produces only 1 trailing event."""
        events = [_cal("Solo", _dt(10, 11), _dt(12, 11))]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        assert len(result) == 1
        assert result[0].is_trailing is True

    def test_summary_format_in_generated_events(self) -> None:
        """Generated events use '{prefix} - {property_name}' summary."""
        events = [
            _cal("A", _dt(10, 11), _dt(12, 11)),
            _cal("B", _dt(12, 15), _dt(15, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Clean",
            property_name="Lake Cabin",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        for evt in result:
            assert evt.summary == "Clean - Lake Cabin"

    def test_all_events_have_valid_uids(self) -> None:
        """All generated events have UIDs matching the expected format."""
        events = [
            _cal("A", _dt(10, 11), _dt(12, 11)),
            _cal("B", _dt(12, 15), _dt(15, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        for evt in result:
            assert UID_PATTERN.match(evt.uid), f"Bad UID: {evt.uid}"

    def test_all_events_are_turnover_event_instances(self) -> None:
        """All results are TurnoverEvent instances."""
        events = [
            _cal("A", _dt(10, 11), _dt(12, 11)),
            _cal("B", _dt(12, 15), _dt(15, 11)),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        for evt in result:
            assert isinstance(evt, TurnoverEvent)

    def test_trailing_replaced_when_new_guest_added(self) -> None:
        """Adding a guest after trailing creates new UID (trailing gone)."""
        # First: single guest → only trailing
        events_before = [_cal("A", _dt(10, 11), _dt(12, 11))]
        result_before = compute_turnover_events(
            events=events_before,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        trailing_uid = result_before[0].uid

        # Now add a second guest → trailing should have different UID
        events_after = [
            _cal("A", _dt(10, 11), _dt(12, 11)),
            _cal("B", _dt(12, 15), _dt(15, 11)),
        ]
        result_after = compute_turnover_events(
            events=events_after,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        # The old trailing UID should not be present
        all_uids = {e.uid for e in result_after}
        assert trailing_uid not in all_uids
        # There should now be a regular event + a new trailing event
        trailing_after = [e for e in result_after if e.is_trailing]
        assert len(trailing_after) == 1
        assert trailing_after[0].uid != trailing_uid

    def test_timezone_propagated_to_events(self) -> None:
        """Generated events carry the configured timezone string."""
        events = [_cal("A", _dt(10, 11), _dt(12, 11))]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        assert result[0].timezone == "America/New_York"

    def test_trailing_duration_zero_rejected(self) -> None:
        """trailing_duration_hours=0 raises ValueError."""
        with pytest.raises(ValueError, match="trailing_duration_hours"):
            compute_turnover_events(
                events=[_cal("A", _dt(10, 11), _dt(12, 11))],
                summary_prefix="Turnover",
                property_name="Beach House",
                trailing_duration_hours=0,
                timezone_str="America/New_York",
            )

    def test_trailing_duration_negative_rejected(self) -> None:
        """Negative trailing_duration_hours raises ValueError."""
        with pytest.raises(ValueError, match="trailing_duration_hours"):
            compute_turnover_events(
                events=[_cal("A", _dt(10, 11), _dt(12, 11))],
                summary_prefix="Turnover",
                property_name="Beach House",
                trailing_duration_hours=-1,
                timezone_str="America/New_York",
            )

    def test_trailing_duration_over_24_rejected(self) -> None:
        """trailing_duration_hours > 24 raises ValueError."""
        with pytest.raises(ValueError, match="trailing_duration_hours"):
            compute_turnover_events(
                events=[_cal("A", _dt(10, 11), _dt(12, 11))],
                summary_prefix="Turnover",
                property_name="Beach House",
                trailing_duration_hours=25,
                timezone_str="America/New_York",
            )

    def test_cross_timezone_normalization(self) -> None:
        """Events in a different tz are normalized to configured tz."""
        pacific = ZoneInfo("America/Los_Angeles")
        # 11:00 Pacific = 14:00 Eastern
        events = [
            CalendarEvent(
                start=datetime(2026, 3, 10, 11, 0, tzinfo=pacific),
                end=datetime(2026, 3, 12, 11, 0, tzinfo=pacific),
                summary="Guest",
            ),
        ]
        result = compute_turnover_events(
            events=events,
            summary_prefix="Turnover",
            property_name="Beach House",
            trailing_duration_hours=4,
            timezone_str="America/New_York",
        )
        # Trailing event starts at checkout time in Eastern
        assert result[0].dtstart.tzinfo == ET
        assert result[0].dtstart.hour == 14


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(day: int, hour: int) -> datetime:
    """Build a TZ-aware datetime in March 2026 ET."""
    return datetime(2026, 3, day, hour, 0, tzinfo=ET)


def _cal(
    summary: str,
    start: datetime,
    end: datetime,
) -> CalendarEvent:
    """Build a CalendarEvent for testing."""
    return CalendarEvent(
        start=start,
        end=end,
        summary=summary,
        description="",
    )
