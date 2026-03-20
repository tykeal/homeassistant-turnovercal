# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""HTTP view for TurnoverCal iCal feed endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from homeassistant.components.http import (  # type: ignore[attr-defined]
    HomeAssistantView,
)

from custom_components.turnovercal.calendar import generate_ical
from custom_components.turnovercal.const import DOMAIN, FEED_URL_PATH
from custom_components.turnovercal.token import validate_token

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class TurnoverCalView(HomeAssistantView):
    """Serve the iCal feed at a secret URL."""

    url = FEED_URL_PATH
    name = "api:turnovercal:calendar"
    requires_auth = False

    async def get(
        self,
        request: web.Request,
        token: str,
    ) -> web.Response:
        """Handle GET request for the iCal feed.

        Validates the token against all registered config entries.
        Returns 401 for invalid tokens, 200 with iCal data for valid.

        Args:
            request: The incoming HTTP request.
            token: The URL token from the path.

        Returns:
            HTTP response with iCal data or 401.

        """
        hass: HomeAssistant = request.app["hass"]
        entries = hass.data.get(DOMAIN, {})

        # Find the entry matching this token
        for entry_data in entries.values():
            stored_token = entry_data.get("feed_token")
            if validate_token(stored_token, token):
                cache = entry_data["cache"]
                events = list(cache.get_events().values())
                ical_data = generate_ical(
                    events=events,
                    timezone_str=entry_data["timezone_str"],
                    summary_prefix=entry_data["summary_prefix"],
                    property_name=entry_data["property_name"],
                )
                return web.Response(
                    body=ical_data,
                    content_type="text/calendar",
                    charset="utf-8",
                )

        return web.Response(status=401)
