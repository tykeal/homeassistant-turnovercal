# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""TurnoverCal Home Assistant integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from custom_components.turnovercal.const import (
    CONF_CALENDAR_ENTITY,
    CONF_CLEANING_CODE_SLOT,
    CONF_EARLY_UNLOCK_GRACE_HOURS,
    CONF_KEYMASTER_DEVICE,
    CONF_LOCK_MONITORING,
    CONF_PROPERTY_NAME,
    CONF_RETENTION_WEEKS,
    CONF_SUMMARY_PREFIX,
    CONF_TRAILING_DURATION_HOURS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
    DEFAULT_LOCK_MONITORING,
    DEFAULT_RETENTION_WEEKS,
    DEFAULT_SUMMARY_PREFIX,
    DEFAULT_TRAILING_DURATION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    EVENT_KEYMASTER,
    KEYMASTER_DOMAIN,
    KM_LOCK_ENTITY_KEY,
)
from custom_components.turnovercal.coordinator import TurnoverCoordinator
from custom_components.turnovercal.event_cache import EventCache
from custom_components.turnovercal.http_view import TurnoverCalView
from custom_components.turnovercal.services import (
    async_setup_services,
    async_unload_services,
)

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_component import EntityComponent

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _resolve_lock_entity(
    hass: HomeAssistant,
    device_id: str,
) -> str | None:
    """Resolve a keymaster device ID to its managed lock entity.

    Looks up the device in the device registry, finds the
    associated keymaster config entry, and returns the lock
    entity ID from that entry's data.

    Args:
        hass: Home Assistant instance.
        device_id: The keymaster device ID.

    Returns:
        The lock entity ID or None if not resolvable.

    """
    device_reg = dr.async_get(hass)
    device = device_reg.async_get(device_id)
    if device is None:
        return None

    for ce_id in device.config_entries:
        ce = hass.config_entries.async_get_entry(ce_id)
        if ce and ce.domain == KEYMASTER_DOMAIN:
            entity_id = ce.data.get(KM_LOCK_ENTITY_KEY)
            if isinstance(entity_id, str) and entity_id.startswith(
                "lock.",
            ):
                return entity_id

    return None


def _resolve_lock_monitoring(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> tuple[bool, str | None, int, int]:
    """Resolve lock monitoring settings from entry config.

    Reads lock monitoring options, resolves the keymaster device
    to a lock entity, and disables monitoring if unresolvable.

    Args:
        hass: Home Assistant instance.
        entry: The config entry to read settings from.

    Returns:
        Tuple of (enabled, lock_entity_id, slot, grace_hours).

    """
    options = entry.options
    enabled = options.get(
        CONF_LOCK_MONITORING,
        entry.data.get(CONF_LOCK_MONITORING, DEFAULT_LOCK_MONITORING),
    )
    device_id = options.get(
        CONF_KEYMASTER_DEVICE,
        entry.data.get(CONF_KEYMASTER_DEVICE),
    )
    slot = options.get(
        CONF_CLEANING_CODE_SLOT,
        entry.data.get(CONF_CLEANING_CODE_SLOT, 0),
    )
    grace = options.get(
        CONF_EARLY_UNLOCK_GRACE_HOURS,
        DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
    )

    lock_entity_id: str | None = None
    if enabled and device_id:
        lock_entity_id = _resolve_lock_entity(hass, device_id)
        if lock_entity_id is None:
            _LOGGER.warning(
                "Lock monitoring enabled for '%s' but Keymaster "
                "device '%s' could not be resolved to a lock "
                "entity. Lock monitoring will be disabled",
                entry.title,
                device_id,
            )
            enabled = False
    elif enabled:
        _LOGGER.warning(
            "Lock monitoring enabled for '%s' but no Keymaster "
            "device configured. Lock monitoring will be disabled",
            entry.title,
        )
        enabled = False

    return enabled, lock_entity_id, slot, grace


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
    tz_str = hass.config.time_zone or "UTC"

    options = entry.options
    summary_prefix = options.get(CONF_SUMMARY_PREFIX, DEFAULT_SUMMARY_PREFIX)
    property_name = options.get(CONF_PROPERTY_NAME, "") or entry.title
    trailing_hours = options.get(
        CONF_TRAILING_DURATION_HOURS,
        DEFAULT_TRAILING_DURATION_HOURS,
    )
    update_minutes = options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    lock_monitoring, lock_entity_id, cleaning_code_slot, grace_hours = (
        _resolve_lock_monitoring(hass, entry)
    )

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
        lock_entity_id=lock_entity_id if lock_monitoring else None,
        cleaning_code_slot=cleaning_code_slot,
        grace_hours=grace_hours,
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

    # Register services (idempotent)
    await async_setup_services(hass)

    # Forward platform setup (sensor for feed URL)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register Keymaster listener if lock monitoring is enabled
    if lock_monitoring and lock_entity_id:
        unsub_lock = hass.bus.async_listen(
            EVENT_KEYMASTER,
            coordinator.handle_lock_event,
        )
        entry.async_on_unload(unsub_lock)

    async def _async_hourly_cleanup(_now: datetime) -> None:
        """Run hourly cleanup of expired events."""
        retention = entry.options.get(
            CONF_RETENTION_WEEKS,
            DEFAULT_RETENTION_WEEKS,
        )
        removed = await cache.async_cleanup_expired(retention)
        if removed > 0:
            _LOGGER.info(
                "Cleaned up %d expired turnover events",
                removed,
            )

    unsub_cleanup = async_track_time_interval(
        hass, _async_hourly_cleanup, timedelta(hours=1)
    )
    entry.async_on_unload(unsub_cleanup)
    entry.async_on_unload(
        entry.add_update_listener(_async_options_updated),
    )

    return True


async def _async_options_updated(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Reload entry when options change.

    Args:
        hass: Home Assistant instance.
        entry: The config entry whose options changed.

    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a TurnoverCal config entry.

    Removes the coordinator, cache, and platform entities
    from hass.data.

    Args:
        hass: Home Assistant instance.
        entry: The config entry being unloaded.

    Returns:
        True if unload was successful.

    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    domain_data = hass.data.get(DOMAIN)
    if domain_data is None:
        return unload_ok
    coordinator = domain_data.get(entry.entry_id, {}).get(
        "coordinator",
    )
    if coordinator is not None:
        await coordinator.async_shutdown()
    domain_data.pop(entry.entry_id, None)

    # Unregister services when last entry is unloaded
    if not domain_data:
        await async_unload_services(hass)

    return unload_ok
