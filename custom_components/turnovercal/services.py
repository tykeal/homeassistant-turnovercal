# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Service handlers for the TurnoverCal integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from custom_components.turnovercal.const import DOMAIN

if TYPE_CHECKING:
    from typing import Any

    from homeassistant.core import HomeAssistant, ServiceCall

    from custom_components.turnovercal.coordinator import (
        TurnoverCoordinator,
    )

_LOGGER = logging.getLogger(__name__)

SERVICE_MARK_CLEANING = "mark_cleaning_started"
SERVICE_MARK_CLEAN = "mark_clean"
SERVICE_MARK_DIRTY = "mark_dirty"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_TIMESTAMP = "timestamp"


def _find_coordinator_by_entity(
    domain_data: dict[str, Any],
    entity_id: str,
) -> TurnoverCoordinator:
    """Find a coordinator matching the given entity ID.

    Args:
        domain_data: The hass.data[DOMAIN] dictionary.
        entity_id: The calendar entity ID to match.

    Returns:
        The matching TurnoverCoordinator.

    Raises:
        ServiceValidationError: If no match is found.

    """
    for entry_data in domain_data.values():
        if not isinstance(entry_data, dict):
            continue
        coord: TurnoverCoordinator | None = entry_data.get(
            "coordinator",
        )
        if coord is None:
            continue
        if coord.calendar_entity_id == entity_id:
            return coord

    msg = f"No TurnoverCal entry found for entity {entity_id}"
    raise ServiceValidationError(
        msg,
        translation_domain=DOMAIN,
        translation_key="entity_not_found",
    )


def _find_entry_data_by_entity(
    domain_data: dict[str, Any],
    entity_id: str,
) -> dict[str, Any]:
    """Find entry data matching the given entity ID.

    Matches by calendar entity or binary_sensor entity ID.

    Args:
        domain_data: The hass.data[DOMAIN] dictionary.
        entity_id: The entity ID to match.

    Returns:
        The matching entry data dictionary.

    Raises:
        ServiceValidationError: If no match is found.

    """
    for entry_data in domain_data.values():
        if not isinstance(entry_data, dict):
            continue
        coord: TurnoverCoordinator | None = entry_data.get(
            "coordinator",
        )
        if coord is not None and coord.calendar_entity_id == entity_id:
            return entry_data
        if entry_data.get("binary_sensor_entity_id") == entity_id:
            return entry_data

    msg = f"No TurnoverCal entry found for entity {entity_id}"
    raise ServiceValidationError(
        msg,
        translation_domain=DOMAIN,
        translation_key="entity_not_found",
    )


def _resolve_coordinators(
    hass: HomeAssistant,
    call: ServiceCall,
) -> list[TurnoverCoordinator]:
    """Resolve targets to TurnoverCoordinators.

    Exactly one of entity target or config_entry_id must be
    provided. Returns matching coordinators or raises
    ServiceValidationError.

    Args:
        hass: Home Assistant instance.
        call: The service call with target and data.

    Returns:
        List of resolved TurnoverCoordinators.

    Raises:
        ServiceValidationError: If targeting is invalid.

    """
    entity_ids: list[str] = cv.ensure_list(
        call.data.get("entity_id", []),
    )

    config_entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)

    if entity_ids and config_entry_id:
        msg = "Provide either an entity target or config_entry_id, not both"
        raise ServiceValidationError(
            msg,
            translation_domain=DOMAIN,
            translation_key="ambiguous_target",
        )

    if not entity_ids and not config_entry_id:
        msg = "Provide either an entity target or config_entry_id"
        raise ServiceValidationError(
            msg,
            translation_domain=DOMAIN,
            translation_key="missing_target",
        )

    domain_data: dict[str, Any] = hass.data.get(DOMAIN, {})

    if config_entry_id:
        entry_data = domain_data.get(config_entry_id)
        if entry_data is None:
            msg = f"Config entry {config_entry_id} not found or not loaded"
            raise ServiceValidationError(
                msg,
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
            )
        return [entry_data["coordinator"]]

    return [_find_coordinator_by_entity(domain_data, eid) for eid in entity_ids]


def _parse_timestamp(
    hass: HomeAssistant,
    ts_raw: datetime | str | None,
) -> datetime:
    """Parse a timestamp into a UTC datetime.

    If None, returns current UTC time. If provided, interprets
    naive datetimes in the HA-configured timezone; aware
    datetimes are converted directly.

    Args:
        hass: Home Assistant instance for timezone config.
        ts_raw: Raw timestamp value from service data.

    Returns:
        UTC-aware datetime.

    """
    if ts_raw is None:
        return datetime.now(tz=ZoneInfo("UTC"))

    try:
        tz_str = hass.config.time_zone or "UTC"
        tz = ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, KeyError) as err:
        msg = f"Invalid HA timezone: {hass.config.time_zone}"
        raise ServiceValidationError(
            msg,
            translation_domain=DOMAIN,
            translation_key="invalid_timezone",
        ) from err

    try:
        if isinstance(ts_raw, datetime):
            parsed = ts_raw
        else:
            result = dt_util.parse_datetime(str(ts_raw))
            if result is None:
                msg = f"Invalid timestamp: {ts_raw}"
                raise ServiceValidationError(  # noqa: TRY301
                    msg,
                    translation_domain=DOMAIN,
                    translation_key="invalid_timestamp",
                )
            parsed = result
    except ServiceValidationError:
        raise
    except (ValueError, TypeError) as err:
        msg = f"Invalid timestamp: {ts_raw}"
        raise ServiceValidationError(
            msg,
            translation_domain=DOMAIN,
            translation_key="invalid_timestamp",
        ) from err

    if parsed.tzinfo is not None:
        return parsed.astimezone(ZoneInfo("UTC"))
    return parsed.replace(tzinfo=tz).astimezone(ZoneInfo("UTC"))


async def _handle_mark_cleaning(call: ServiceCall) -> None:
    """Handle the mark_cleaning_started service call.

    Resolves all target coordinators, parses the optional
    timestamp, and applies the cleaning signal to each.

    Args:
        call: The service call.

    """
    hass = call.hass
    coordinators = _resolve_coordinators(hass, call)
    now = _parse_timestamp(hass, call.data.get(ATTR_TIMESTAMP))

    for coordinator in coordinators:
        adjusted = await coordinator.apply_cleaning_signal(
            now,
            source="service_call",
        )
        if adjusted:
            coordinator.async_set_updated_data(
                coordinator.cache_events,
            )
        else:
            _LOGGER.warning(
                "No active turnover window for %s",
                coordinator.calendar_entity_id,
            )


def _resolve_cleanliness_machines(
    hass: HomeAssistant,
    call: ServiceCall,
) -> list[Any]:
    """Resolve targets to cleanliness state machines.

    Supports targeting by calendar entity, binary_sensor entity,
    or config_entry_id.

    Args:
        hass: Home Assistant instance.
        call: The service call with target and data.

    Returns:
        List of resolved CleanlinessStateMachine instances.

    Raises:
        ServiceValidationError: If targeting is invalid.

    """
    entity_ids: list[str] = cv.ensure_list(
        call.data.get("entity_id", []),
    )
    config_entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)

    if entity_ids and config_entry_id:
        msg = "Provide either an entity target or config_entry_id, not both"
        raise ServiceValidationError(
            msg,
            translation_domain=DOMAIN,
            translation_key="ambiguous_target",
        )

    if not entity_ids and not config_entry_id:
        msg = "Provide either an entity target or config_entry_id"
        raise ServiceValidationError(
            msg,
            translation_domain=DOMAIN,
            translation_key="missing_target",
        )

    domain_data: dict[str, Any] = hass.data.get(DOMAIN, {})

    if config_entry_id:
        entry_data = domain_data.get(config_entry_id)
        if entry_data is None:
            msg = f"Config entry {config_entry_id} not found or not loaded"
            raise ServiceValidationError(
                msg,
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
            )
        return [entry_data["cleanliness"]]

    machines = []
    for eid in entity_ids:
        entry_data = _find_entry_data_by_entity(domain_data, eid)
        machines.append(entry_data["cleanliness"])
    return machines


async def _handle_mark_clean(call: ServiceCall) -> None:
    """Handle the mark_clean service call.

    Resolves all target cleanliness state machines and
    marks each as clean immediately.

    Args:
        call: The service call.

    """
    hass = call.hass
    machines = _resolve_cleanliness_machines(hass, call)

    for machine in machines:
        await machine.async_mark_clean()


async def _handle_mark_dirty(call: ServiceCall) -> None:
    """Handle the mark_dirty service call.

    Resolves all target cleanliness state machines and
    requests a transition to the dirty state.  Properties
    that are currently occupied remain in the occupied phase.

    Args:
        call: The service call.

    """
    hass = call.hass
    machines = _resolve_cleanliness_machines(hass, call)

    for machine in machines:
        await machine.async_mark_dirty()


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register TurnoverCal services.

    Guarded to be idempotent — skips registration when
    the service is already registered.

    Args:
        hass: Home Assistant instance.

    """
    if not hass.services.has_service(DOMAIN, SERVICE_MARK_CLEANING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_MARK_CLEANING,
            _handle_mark_cleaning,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_MARK_CLEAN):
        hass.services.async_register(
            DOMAIN,
            SERVICE_MARK_CLEAN,
            _handle_mark_clean,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_MARK_DIRTY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_MARK_DIRTY,
            _handle_mark_dirty,
        )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister TurnoverCal services.

    Only removes services when the last config entry is
    unloaded.

    Args:
        hass: Home Assistant instance.

    """
    hass.services.async_remove(DOMAIN, SERVICE_MARK_CLEANING)
    hass.services.async_remove(DOMAIN, SERVICE_MARK_CLEAN)
    hass.services.async_remove(DOMAIN, SERVICE_MARK_DIRTY)
