# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for TurnoverCal HTTP view (iCal feed endpoint)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.setup import async_setup_component

from custom_components.turnovercal.const import DOMAIN
from custom_components.turnovercal.http_view import TurnoverCalView
from custom_components.turnovercal.models import TurnoverEvent

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.typing import (
        ClientSessionGenerator,
    )

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")
VALID_UID = "0123456789abcdef@turnovercal.homeassistant"
TEST_TOKEN = "test-token-43chars-aaabbbccc111222333444"  # noqa: S105


def _make_event(uid: str = VALID_UID) -> TurnoverEvent:
    """Create a TurnoverEvent for testing."""
    return TurnoverEvent(
        uid=uid,
        summary="Turnover - Beach House",
        dtstart=datetime(2026, 3, 10, 11, 0, tzinfo=ET),
        dtend=datetime(2026, 3, 10, 15, 0, tzinfo=ET),
        timezone="America/New_York",
        source_checkout_id="src-co-001",
        source_checkin_id="src-ci-002",
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    )


@pytest.fixture(autouse=True)
async def _setup_http(hass: HomeAssistant) -> None:
    """Set up the HTTP component for view testing."""
    await async_setup_component(hass, "http", {"http": {}})


def _setup_entry_data(
    hass: HomeAssistant,
    *,
    events: dict[str, TurnoverEvent] | None = None,
) -> None:
    """Set up hass.data with mock entry data."""
    hass.data.setdefault(DOMAIN, {})
    mock_cache = MagicMock()
    mock_cache.get_events.return_value = events or {}
    hass.data[DOMAIN]["test_entry"] = {
        "cache": mock_cache,
        "feed_token": TEST_TOKEN,
        "timezone_str": "America/New_York",
        "summary_prefix": "Turnover",
        "property_name": "Beach House",
    }


# ---------------------------------------------------------------------------
# HTTP view - valid token
# ---------------------------------------------------------------------------


class TestHttpViewValidToken:
    """Tests for HTTP view with valid token."""

    async def test_valid_token_returns_200(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Valid token returns 200 status."""
        _setup_entry_data(hass)
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get(f"/api/turnovercal/{TEST_TOKEN}/calendar.ics")
        assert resp.status == 200

    async def test_valid_token_returns_text_calendar(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Valid token returns text/calendar content-type."""
        _setup_entry_data(hass)
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get(f"/api/turnovercal/{TEST_TOKEN}/calendar.ics")
        assert resp.content_type == "text/calendar"

    async def test_response_body_valid_rfc5545(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Response body is valid RFC 5545 (starts/ends properly)."""
        evt = _make_event()
        _setup_entry_data(hass, events={evt.uid: evt})
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get(f"/api/turnovercal/{TEST_TOKEN}/calendar.ics")
        body = await resp.text()
        assert body.startswith("BEGIN:VCALENDAR")
        assert body.strip().endswith("END:VCALENDAR")
        assert "BEGIN:VEVENT" in body
        assert f"UID:{VALID_UID}" in body


# ---------------------------------------------------------------------------
# HTTP view - invalid / missing token
# ---------------------------------------------------------------------------


class TestHttpViewInvalidToken:
    """Tests for HTTP view with invalid or missing token."""

    async def test_invalid_token_returns_401(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Invalid token returns 401."""
        _setup_entry_data(hass)
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get("/api/turnovercal/wrong-token/calendar.ics")
        assert resp.status == 401

    async def test_missing_token_returns_401(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Request with nonexistent token returns 401."""
        hass.data.setdefault(DOMAIN, {})
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get("/api/turnovercal/nonexistent-token/calendar.ics")
        assert resp.status == 401

    async def test_removed_entry_returns_401(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Removed config entry token returns 401."""
        hass.data.setdefault(DOMAIN, {})
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get(f"/api/turnovercal/{TEST_TOKEN}/calendar.ics")
        assert resp.status == 401


# ---------------------------------------------------------------------------
# HTTP view - empty calendar
# ---------------------------------------------------------------------------


class TestHttpViewEmptyCalendar:
    """Tests for HTTP view with empty calendar."""

    async def test_empty_calendar_valid_vcalendar(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Empty calendar returns valid VCALENDAR with no VEVENT."""
        _setup_entry_data(hass)
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get(f"/api/turnovercal/{TEST_TOKEN}/calendar.ics")
        body = await resp.text()
        assert resp.status == 200
        assert "BEGIN:VCALENDAR" in body
        assert "END:VCALENDAR" in body
        assert "BEGIN:VEVENT" not in body


# ---------------------------------------------------------------------------
# Contract test: iCal feed endpoint (T020)
# ---------------------------------------------------------------------------


class TestICalFeedContract:
    """Contract tests per ical-feed.md."""

    async def test_content_type_header(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Response Content-Type is text/calendar; charset=utf-8."""
        _setup_entry_data(hass)
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get(f"/api/turnovercal/{TEST_TOKEN}/calendar.ics")
        ct = resp.headers.get("Content-Type", "")
        assert "text/calendar" in ct
        assert "charset=utf-8" in ct.lower()

    async def test_vcalendar_structure(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Response body matches VCALENDAR structure from contract."""
        evt = _make_event()
        _setup_entry_data(hass, events={evt.uid: evt})
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get(f"/api/turnovercal/{TEST_TOKEN}/calendar.ics")
        body = await resp.text()

        # Contract: VCALENDAR properties
        assert "VERSION:2.0" in body
        assert "PRODID:-//Home Assistant//TurnoverCal//EN" in body
        assert "CALSCALE:GREGORIAN" in body
        assert "METHOD:PUBLISH" in body

        # Contract: VEVENT field set
        assert f"UID:{VALID_UID}" in body
        assert "DTSTAMP:" in body
        assert "DTSTART;" in body
        assert "DTEND;" in body
        assert "SUMMARY:" in body
        assert "DESCRIPTION:" in body
        assert "STATUS:" in body

    async def test_401_for_invalid_token(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
    ) -> None:
        """Contract: 401 for invalid tokens."""
        hass.data.setdefault(DOMAIN, {})
        hass.http.register_view(TurnoverCalView())
        client = await hass_client()

        resp = await client.get("/api/turnovercal/bad-token/calendar.ics")
        assert resp.status == 401
