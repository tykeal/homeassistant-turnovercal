# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for TurnoverEvent and CachedEventStore data models."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.turnovercal.models import CachedEventStore, TurnoverEvent

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")
VALID_UID = "0123456789abcdef@turnovercal.homeassistant"


# ---------------------------------------------------------------------------
# TurnoverEvent - construction & defaults
# ---------------------------------------------------------------------------


class TestTurnoverEventConstruction:
    """Tests for TurnoverEvent construction and default values."""

    def test_construct_with_required_fields(self) -> None:
        """TurnoverEvent can be constructed with all required fields."""
        evt = TurnoverEvent(
            uid="abcdef0123456789@turnovercal.homeassistant",
            summary="Turnover - Beach House",
            dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
            dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
            timezone="America/New_York",
            source_checkout_id="rc-event-001",
            source_checkin_id="rc-event-002",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )
        assert evt.uid == "abcdef0123456789@turnovercal.homeassistant"
        assert evt.summary == "Turnover - Beach House"
        assert evt.dtstart == datetime(2026, 3, 10, 11, 0, tzinfo=ET)
        assert evt.dtend == datetime(2026, 3, 10, 15, 0, tzinfo=ET)
        assert evt.timezone == "America/New_York"
        assert evt.source_checkout_id == "rc-event-001"
        assert evt.source_checkin_id == "rc-event-002"
        assert evt.created_at == datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    def test_default_status_is_scheduled(self) -> None:
        """Default status must be 'scheduled'."""
        evt = _make_event()
        assert evt.status == "scheduled"

    def test_default_is_trailing_false(self) -> None:
        """Default is_trailing must be False."""
        evt = _make_event()
        assert evt.is_trailing is False

    def test_default_adjusted_by_lock_false(self) -> None:
        """Default adjusted_by_lock must be False."""
        evt = _make_event()
        assert evt.adjusted_by_lock is False

    def test_default_lock_unlock_time_none(self) -> None:
        """Default lock_unlock_time must be None."""
        evt = _make_event()
        assert evt.lock_unlock_time is None

    def test_default_adjustment_source_none(self) -> None:
        """Default adjustment_source must be None."""
        evt = _make_event()
        assert evt.adjustment_source is None

    def test_default_original_dtend_none(self) -> None:
        """Default original_dtend must be None."""
        evt = _make_event()
        assert evt.original_dtend is None

    def test_default_original_dtstart_none(self) -> None:
        """Default original_dtstart must be None."""
        evt = _make_event()
        assert evt.original_dtstart is None


# ---------------------------------------------------------------------------
# TurnoverEvent - validation
# ---------------------------------------------------------------------------


class TestTurnoverEventValidation:
    """Tests for TurnoverEvent validation rules."""

    def test_dtstart_must_be_before_dtend(self) -> None:
        """Raise ValueError when dtstart is after dtend."""
        with pytest.raises(ValueError, match="dtstart must be before dtend"):
            TurnoverEvent(
                uid="abcdef0123456789@turnovercal.homeassistant",
                summary="Turnover - Beach House",
                dtstart=datetime(2026, 3, 10, 16, 0, tzinfo=ET),
                dtend=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
                timezone="America/New_York",
                source_checkout_id="rc-001",
                source_checkin_id="rc-002",
                created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            )

    def test_zero_duration_promoted_to_one_minute(self) -> None:
        """When dtstart == dtend, dtend is promoted to dtstart + 1 minute."""
        start = datetime(2026, 3, 10, 11, 0, tzinfo=ET)
        evt = TurnoverEvent(
            uid="abcdef0123456789@turnovercal.homeassistant",
            summary="Turnover - Beach House",
            dtstart=start,
            dtend=start,
            timezone="America/New_York",
            source_checkout_id="rc-001",
            source_checkin_id="rc-002",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )
        assert evt.dtend == start + timedelta(minutes=1)

    def test_uid_must_end_with_domain(self) -> None:
        """UID must end with @turnovercal.homeassistant."""
        with pytest.raises(ValueError, match="pattern"):
            TurnoverEvent(
                uid="bad-uid-no-domain",
                summary="Turnover - Beach House",
                dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
                dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
                timezone="America/New_York",
                source_checkout_id="rc-001",
                source_checkin_id="rc-002",
                created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            )

    def test_uid_rejects_non_hex_prefix(self) -> None:
        """UID prefix must be exactly 16 hex characters."""
        with pytest.raises(ValueError, match="pattern"):
            TurnoverEvent(
                uid="ZZZZZZZZZZZZZZZZ@turnovercal.homeassistant",
                summary="Turnover - Beach House",
                dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
                dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
                timezone="America/New_York",
                source_checkout_id="rc-001",
                source_checkin_id="rc-002",
                created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            )

    def test_trailing_must_have_no_checkin(self) -> None:
        """Trailing events must have source_checkin_id=None."""
        with pytest.raises(ValueError, match="source_checkin_id=None"):
            TurnoverEvent(
                uid=VALID_UID,
                summary="Turnover - Beach House",
                dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
                dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
                timezone="America/New_York",
                source_checkout_id="rc-001",
                source_checkin_id="rc-002",
                created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                is_trailing=True,
            )

    def test_non_trailing_must_have_checkin(self) -> None:
        """Non-trailing events must have source_checkin_id set."""
        with pytest.raises(ValueError, match="must have source_checkin_id"):
            TurnoverEvent(
                uid=VALID_UID,
                summary="Turnover - Beach House",
                dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
                dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
                timezone="America/New_York",
                source_checkout_id="rc-001",
                source_checkin_id=None,
                created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                is_trailing=False,
            )

    def test_to_dict_normalizes_utc(self) -> None:
        """to_dict normalizes created_at to UTC."""
        event = TurnoverEvent(
            uid=VALID_UID,
            summary="Turnover - Beach House",
            dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
            dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
            timezone="America/New_York",
            source_checkout_id="rc-001",
            source_checkin_id="rc-002",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=ET),
        )
        d = event.to_dict()
        assert "+00:00" in d["created_at"]


# ---------------------------------------------------------------------------
# TurnoverEvent - serialization round-trip
# ---------------------------------------------------------------------------


class TestTurnoverEventSerialization:
    """Tests for TurnoverEvent to_dict / from_dict serialization."""

    def test_round_trip_produces_equal_object(self) -> None:
        """to_dict() then from_dict() must produce an equal TurnoverEvent."""
        original = _make_event()
        data = original.to_dict()
        restored = TurnoverEvent.from_dict(data)
        assert restored.uid == original.uid
        assert restored.summary == original.summary
        assert restored.dtstart == original.dtstart
        assert restored.dtend == original.dtend
        assert restored.timezone == original.timezone
        assert restored.source_checkout_id == original.source_checkout_id
        assert restored.source_checkin_id == original.source_checkin_id
        assert restored.created_at == original.created_at
        assert restored.status == original.status
        assert restored.is_trailing == original.is_trailing
        assert restored.adjusted_by_lock == original.adjusted_by_lock
        assert restored.lock_unlock_time == original.lock_unlock_time
        assert restored.adjustment_source == original.adjustment_source
        assert restored.original_dtend == original.original_dtend
        assert restored.original_dtstart == original.original_dtstart

    def test_dtstart_stored_as_naive_local_iso(self) -> None:
        """to_dict() stores dtstart as naive local ISO (no offset, no Z)."""
        evt = _make_event()
        data = evt.to_dict()
        dtstart_str = data["dtstart"]
        assert isinstance(dtstart_str, str)
        # Must not contain offset or Z
        assert "+" not in dtstart_str
        assert "Z" not in dtstart_str
        # Must be valid ISO 8601 naive
        assert dtstart_str == "2026-03-10T11:00:00"

    def test_dtend_stored_as_naive_local_iso(self) -> None:
        """to_dict() stores dtend as naive local ISO (no offset, no Z)."""
        evt = _make_event()
        data = evt.to_dict()
        dtend_str = data["dtend"]
        assert isinstance(dtend_str, str)
        assert "+" not in dtend_str
        assert "Z" not in dtend_str
        assert dtend_str == "2026-03-10T15:00:00"

    def test_created_at_stored_as_utc_with_offset(self) -> None:
        """to_dict() stores created_at as UTC with +00:00 offset."""
        evt = _make_event()
        data = evt.to_dict()
        created_str = data["created_at"]
        assert isinstance(created_str, str)
        assert "+00:00" in created_str

    def test_round_trip_with_all_optional_fields(self) -> None:
        """Round-trip preserves all optional fields when set."""
        evt = TurnoverEvent(
            uid="abcdef0123456789@turnovercal.homeassistant",
            summary="Turnover - Beach House",
            dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
            dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
            timezone="America/New_York",
            source_checkout_id="rc-001",
            source_checkin_id="rc-002",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            status="adjusted",
            is_trailing=False,
            adjusted_by_lock=True,
            lock_unlock_time=datetime(2026, 3, 10, 12, 30, tzinfo=UTC),
            adjustment_source="keymaster",
            original_dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
            original_dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
        )
        data = evt.to_dict()
        restored = TurnoverEvent.from_dict(data)
        assert restored.status == "adjusted"
        assert restored.adjusted_by_lock is True
        assert restored.lock_unlock_time == datetime(2026, 3, 10, 12, 30, tzinfo=UTC)
        assert restored.adjustment_source == "keymaster"
        assert restored.original_dtend == datetime(2026, 3, 10, 15, 0, tzinfo=ET)
        assert restored.original_dtstart == datetime(2026, 3, 10, 11, 0, tzinfo=ET)

    def test_none_checkin_id_round_trip(self) -> None:
        """Trailing event with source_checkin_id=None survives round-trip."""
        evt = _make_event(source_checkin_id=None, is_trailing=True)
        data = evt.to_dict()
        restored = TurnoverEvent.from_dict(data)
        assert restored.source_checkin_id is None
        assert restored.is_trailing is True


# ---------------------------------------------------------------------------
# TurnoverEvent - trailing flag
# ---------------------------------------------------------------------------


class TestTurnoverEventTrailing:
    """Tests for trailing event flag semantics."""

    def test_trailing_event_has_none_checkin_id(self) -> None:
        """Trailing events have source_checkin_id=None."""
        evt = _make_event(source_checkin_id=None, is_trailing=True)
        assert evt.is_trailing is True
        assert evt.source_checkin_id is None


# ---------------------------------------------------------------------------
# TurnoverEvent - summary PII check
# ---------------------------------------------------------------------------


class TestTurnoverEventSummary:
    """Tests for summary format (no PII)."""

    def test_summary_format_prefix_property(self) -> None:
        """Summary must follow '{prefix} - {property_name}' format."""
        evt = _make_event()
        assert evt.summary == "Turnover - Beach House"

    def test_summary_does_not_contain_guest_pii(self) -> None:
        """Summary must not contain guest PII like names or booking refs."""
        evt = _make_event()
        # The summary should only contain the prefix and property name
        assert "guest" not in evt.summary.lower()
        assert "booking" not in evt.summary.lower()
        assert "phone" not in evt.summary.lower()


# ---------------------------------------------------------------------------
# CachedEventStore - construction & basic ops
# ---------------------------------------------------------------------------


class TestCachedEventStoreConstruction:
    """Tests for CachedEventStore construction."""

    def test_construct_with_defaults(self) -> None:
        """CachedEventStore can be constructed with required fields."""
        token = "test-token-abc"  # noqa: S105
        store = CachedEventStore(
            version=1,
            events={},
            feed_token=token,
            last_cleanup=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
        )
        assert store.version == 1
        assert store.events == {}
        assert store.feed_token == token
        assert store.last_cleanup == datetime(2026, 3, 1, 0, 0, tzinfo=UTC)

    def test_add_event(self) -> None:
        """Can add an event to the store by UID."""
        store = _make_store()
        evt = _make_event()
        store.events[evt.uid] = evt
        assert evt.uid in store.events

    def test_remove_event(self) -> None:
        """Can remove an event from the store by UID."""
        store = _make_store()
        evt = _make_event()
        store.events[evt.uid] = evt
        del store.events[evt.uid]
        assert evt.uid not in store.events

    def test_lookup_by_uid(self) -> None:
        """Can look up an event by UID using .get()."""
        store = _make_store()
        evt = _make_event()
        store.events[evt.uid] = evt
        found = store.events.get(evt.uid)
        assert found is evt

    def test_lookup_missing_uid_returns_none(self) -> None:
        """Looking up a missing UID returns None."""
        store = _make_store()
        assert store.events.get("nonexistent") is None


# ---------------------------------------------------------------------------
# CachedEventStore - serialization
# ---------------------------------------------------------------------------


class TestCachedEventStoreSerialization:
    """Tests for CachedEventStore to_dict / from_dict serialization."""

    def test_round_trip_empty_store(self) -> None:
        """Empty store round-trips through to_dict / from_dict."""
        store = _make_store()
        data = store.to_dict()
        restored = CachedEventStore.from_dict(data)
        assert restored.version == store.version
        assert restored.events == {}
        assert restored.feed_token == store.feed_token
        assert restored.last_cleanup == store.last_cleanup

    def test_round_trip_with_events(self) -> None:
        """Store with events round-trips correctly."""
        store = _make_store()
        evt = _make_event()
        store.events[evt.uid] = evt
        data = store.to_dict()
        restored = CachedEventStore.from_dict(data)
        assert evt.uid in restored.events
        restored_evt = restored.events[evt.uid]
        assert restored_evt.uid == evt.uid
        assert restored_evt.summary == evt.summary

    def test_feed_token_preserved(self) -> None:
        """Feed_token is preserved through serialization."""
        store = _make_store()
        token = "my-special-token-xyz"  # noqa: S105
        store.feed_token = token
        data = store.to_dict()
        restored = CachedEventStore.from_dict(data)
        assert restored.feed_token == token

    def test_last_cleanup_preserved(self) -> None:
        """last_cleanup is preserved through serialization."""
        cleanup_time = datetime(2026, 6, 15, 8, 30, tzinfo=UTC)
        store = CachedEventStore(
            version=1,
            events={},
            feed_token="tok",  # noqa: S106
            last_cleanup=cleanup_time,
        )
        data = store.to_dict()
        restored = CachedEventStore.from_dict(data)
        assert restored.last_cleanup == cleanup_time

    def test_version_field_preserved(self) -> None:
        """Version field is preserved through serialization."""
        store = _make_store()
        data = store.to_dict()
        restored = CachedEventStore.from_dict(data)
        assert restored.version == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(  # noqa: PLR0913
    *,
    uid: str = "abcdef0123456789@turnovercal.homeassistant",
    summary: str = "Turnover - Beach House",
    dtstart: datetime | None = None,
    dtend: datetime | None = None,
    timezone: str = "America/New_York",
    source_checkout_id: str = "rc-event-001",
    source_checkin_id: str | None = "rc-event-002",
    created_at: datetime | None = None,
    status: str = "scheduled",
    is_trailing: bool = False,
    adjusted_by_lock: bool = False,
) -> TurnoverEvent:
    """Build a TurnoverEvent with sensible defaults for testing."""
    return TurnoverEvent(
        uid=uid,
        summary=summary,
        dtstart=dtstart or datetime(2026, 3, 10, 11, 0, tzinfo=ET),
        dtend=dtend or datetime(2026, 3, 10, 15, 0, tzinfo=ET),
        timezone=timezone,
        source_checkout_id=source_checkout_id,
        source_checkin_id=source_checkin_id,
        created_at=created_at or datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        status=status,
        is_trailing=is_trailing,
        adjusted_by_lock=adjusted_by_lock,
    )


def _make_store() -> CachedEventStore:
    """Build a CachedEventStore with sensible defaults for testing."""
    return CachedEventStore(
        version=1,
        events={},
        feed_token="test-feed-token-abc123",  # noqa: S106
        last_cleanup=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
    )
