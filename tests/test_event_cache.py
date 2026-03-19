# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for EventCache (Store wrapper)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import patch
from zoneinfo import ZoneInfo

from custom_components.turnovercal.event_cache import EventCache
from custom_components.turnovercal.models import TurnoverEvent

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")
VALID_UID = "0123456789abcdef@turnovercal.homeassistant"
VALID_UID_2 = "abcdef0123456789@turnovercal.homeassistant"
_TEST_TOKEN = "test-token-abc"  # noqa: S105
_SECRET_TOKEN = "my-secret-token"  # noqa: S105
_OLD_TOKEN = "old-token"  # noqa: S105
_NEW_TOKEN = "new-token"  # noqa: S105
_TEST_TOKEN_SHORT = "test-token"  # noqa: S105


def _make_event(
    uid: str = VALID_UID,
    *,
    is_trailing: bool = False,
) -> TurnoverEvent:
    """Create a TurnoverEvent for testing."""
    return TurnoverEvent(
        uid=uid,
        summary="Turnover - Beach House",
        dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
        dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
        timezone="America/New_York",
        source_checkout_id="src-co-001",
        source_checkin_id=None if is_trailing else "src-ci-002",
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        is_trailing=is_trailing,
    )


# ---------------------------------------------------------------------------
# EventCache - async load / save
# ---------------------------------------------------------------------------


class TestEventCacheLoadSave:
    """Tests for EventCache async load and save operations."""

    async def test_load_returns_empty_store_when_no_data(
        self, hass: HomeAssistant
    ) -> None:
        """Load with no stored data returns empty CachedEventStore."""
        cache = EventCache(hass, "test_entry_id", _TEST_TOKEN)
        store = await cache.async_load()
        assert store.events == {}
        assert store.version == 1
        assert store.feed_token == _TEST_TOKEN

    async def test_save_and_load_round_trip(self, hass: HomeAssistant) -> None:
        """Save then load preserves all event data."""
        cache = EventCache(hass, "test_entry_id", _TEST_TOKEN)
        evt = _make_event()
        await cache.async_add_event(evt)
        await cache.async_save()

        # Create new cache instance pointing to same store
        cache2 = EventCache(hass, "test_entry_id", _TEST_TOKEN)
        store = await cache2.async_load()
        assert VALID_UID in store.events
        assert store.events[VALID_UID].summary == "Turnover - Beach House"

    async def test_save_uses_delay_save(self, hass: HomeAssistant) -> None:
        """Save uses async_delay_save for batching writes."""
        cache = EventCache(hass, "test_entry_id", _TEST_TOKEN)
        evt = _make_event()

        with patch.object(
            cache._store,  # noqa: SLF001
            "async_delay_save",
            wraps=cache._store.async_delay_save,  # noqa: SLF001
        ) as mock_delay:
            await cache.async_add_event(evt)
            mock_delay.assert_called_once()


# ---------------------------------------------------------------------------
# EventCache - add / remove / get events
# ---------------------------------------------------------------------------


class TestEventCacheOperations:
    """Tests for EventCache add, remove, and get operations."""

    async def test_add_event(self, hass: HomeAssistant) -> None:
        """Add an event and retrieve it."""
        cache = EventCache(hass, "test_entry_id", _TEST_TOKEN)
        evt = _make_event()
        await cache.async_add_event(evt)
        events = cache.get_events()
        assert VALID_UID in events
        assert events[VALID_UID].uid == VALID_UID

    async def test_remove_event(self, hass: HomeAssistant) -> None:
        """Remove an event by UID."""
        cache = EventCache(hass, "test_entry_id", _TEST_TOKEN)
        evt = _make_event()
        await cache.async_add_event(evt)
        await cache.async_remove_event(VALID_UID)
        events = cache.get_events()
        assert VALID_UID not in events

    async def test_get_events_returns_all(self, hass: HomeAssistant) -> None:
        """Get events returns all stored events."""
        cache = EventCache(hass, "test_entry_id", _TEST_TOKEN)
        evt1 = _make_event(VALID_UID)
        evt2 = _make_event(VALID_UID_2)
        await cache.async_add_event(evt1)
        await cache.async_add_event(evt2)
        events = cache.get_events()
        assert len(events) == 2

    async def test_initial_empty_state(self, hass: HomeAssistant) -> None:
        """New cache with no stored data returns empty dict."""
        cache = EventCache(hass, "test_entry_id", _TEST_TOKEN)
        await cache.async_load()
        events = cache.get_events()
        assert events == {}

    async def test_remove_nonexistent_event_is_noop(self, hass: HomeAssistant) -> None:
        """Removing a UID that doesn't exist is a no-op."""
        cache = EventCache(hass, "test_entry_id", _TEST_TOKEN)
        await cache.async_load()
        await cache.async_remove_event("nonexistent@turnovercal.ha")
        assert cache.get_events() == {}


# ---------------------------------------------------------------------------
# EventCache - feed_token persistence
# ---------------------------------------------------------------------------


class TestEventCacheFeedToken:
    """Tests for feed token persistence in EventCache."""

    async def test_feed_token_persisted(self, hass: HomeAssistant) -> None:
        """Feed token is persisted in the store data."""
        cache = EventCache(hass, "test_entry_id", _SECRET_TOKEN)
        await cache.async_load()
        await cache.async_save()

        cache2 = EventCache(hass, "test_entry_id", _SECRET_TOKEN)
        store = await cache2.async_load()
        assert store.feed_token == _SECRET_TOKEN

    async def test_feed_token_updated_on_load(self, hass: HomeAssistant) -> None:
        """Feed token from constructor overrides stored token."""
        # Save with old token
        cache = EventCache(hass, "test_entry_id", _OLD_TOKEN)
        await cache.async_load()
        await cache.async_save()

        # Load with new token - should override
        cache2 = EventCache(hass, "test_entry_id", _NEW_TOKEN)
        store = await cache2.async_load()
        assert store.feed_token == _NEW_TOKEN


# ---------------------------------------------------------------------------
# EventCache - version migration
# ---------------------------------------------------------------------------


class TestEventCacheVersion:
    """Tests for EventCache version and migration."""

    async def test_version_is_one(self, hass: HomeAssistant) -> None:
        """New store has version 1."""
        cache = EventCache(hass, "test_entry_id", _TEST_TOKEN_SHORT)
        store = await cache.async_load()
        assert store.version == 1
