# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""TurnoverCal Home Assistant integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.turnovercal.const import (
    CONF_CALENDAR_ENTITY,
    CONF_PROPERTY_NAME,
    CONF_SUMMARY_PREFIX,
    CONF_TRAILING_DURATION_HOURS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_SUMMARY_PREFIX,
    DEFAULT_TRAILING_DURATION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.turnovercal.coordinator import TurnoverCoordinator
from custom_components.turnovercal.event_cache import EventCache
from custom_components.turnovercal.http_view import TurnoverCalView

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_component import EntityComponent


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up TurnoverCal from a config entry.

    Creates the EventCache, TurnoverCoordinator, and registers
    the HTTP view for the iCal feed.

    Args:
        hass: Home Assistant instance.
        entry: The config entry being set up.

    Returns:
        True if setup was successful.

    """
    hass.data.setdefault(DOMAIN, {})

    entity_id = entry.data[CONF_CALENDAR_ENTITY]
    feed_token = entry.data["feed_token"]
    tz_str = hass.config.time_zone

    options = entry.options
    summary_prefix = options.get(CONF_SUMMARY_PREFIX, DEFAULT_SUMMARY_PREFIX)
    property_name = options.get(CONF_PROPERTY_NAME, "") or entry.title
    trailing_hours = options.get(
        CONF_TRAILING_DURATION_HOURS,
        DEFAULT_TRAILING_DURATION_HOURS,
    )
    update_minutes = options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    cache = EventCache(hass, entry.entry_id, feed_token)
    await cache.async_load()

    # Get the calendar entity via EntityComponent API
    entity_component: EntityComponent | None = hass.data.get("calendar")
    if entity_component is None:
        msg = f"Calendar platform not yet loaded for {entity_id}"
        raise ConfigEntryNotReady(msg)
    calendar_entity = entity_component.get_entity(entity_id)
    if calendar_entity is None:
        msg = f"Calendar entity {entity_id} not ready yet"
        raise ConfigEntryNotReady(msg)

    coordinator = TurnoverCoordinator(
        hass=hass,
        calendar_entity=calendar_entity,  # type: ignore[arg-type]
        cache=cache,
        summary_prefix=summary_prefix,
        property_name=property_name,
        trailing_duration_hours=trailing_hours,
        timezone_str=tz_str,
        update_interval=timedelta(minutes=update_minutes),
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "cache": cache,
        "feed_token": feed_token,
        "timezone_str": tz_str,
        "summary_prefix": summary_prefix,
        "property_name": property_name,
    }

    # Register HTTP view (idempotent)
    hass.http.register_view(TurnoverCalView())

    # Start coordinator
    await coordinator.async_config_entry_first_refresh()

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a TurnoverCal config entry.

    Removes the coordinator and cache from hass.data.

    Args:
        hass: Home Assistant instance.
        entry: The config entry being unloaded.

    Returns:
        True if unload was successful.

    """
    coordinator = (
        hass.data[DOMAIN]
        .get(entry.entry_id, {})
        .get(
            "coordinator",
        )
    )
    if coordinator is not None:
        await coordinator.async_shutdown()
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
