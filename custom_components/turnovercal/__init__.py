# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""TurnoverCal Home Assistant integration."""

from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from custom_components.turnovercal.cleanliness import CleanlinessStateMachine
from custom_components.turnovercal.cleanliness_store import CleanlinessStateStore
from custom_components.turnovercal.const import (
    CONF_CALENDAR_ENTITY,
    CONF_CLEANING_CODE_SLOT,
    CONF_CLEANING_DURATION_HOURS,
    CONF_EARLY_UNLOCK_GRACE_HOURS,
    CONF_KEYMASTER_DEVICE,
    CONF_LOCK_MONITORING,
    CONF_PROPERTY_NAME,
    CONF_RETENTION_WEEKS,
    CONF_SUMMARY_PREFIX,
    CONF_TRAILING_DURATION_HOURS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CLEANING_DURATION_HOURS,
    DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
    DEFAULT_LOCK_MONITORING,
    DEFAULT_RETENTION_WEEKS,
    DEFAULT_SUMMARY_PREFIX,
    DEFAULT_TRAILING_DURATION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    EVENT_KEYMASTER,
    EVENT_RC_CHECKIN,
    EVENT_RC_CHECKOUT,
    KEYMASTER_DOMAIN,
    KM_LOCK_ENTITY_KEY,
    PHASE_OCCUPIED,
    RC_STATE_AWAITING_CHECKIN,
    RC_STATE_CHECKED_IN,
    RC_STATE_CHECKED_OUT,
    RC_STATE_NO_RESERVATION,
)
from custom_components.turnovercal.coordinator import TurnoverCoordinator
from custom_components.turnovercal.event_cache import EventCache
from custom_components.turnovercal.http_view import TurnoverCalView
from custom_components.turnovercal.models import TurnoverEvent
from custom_components.turnovercal.services import (
    async_setup_services,
    async_unload_services,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import Event, EventStateChangedData, HomeAssistant
    from homeassistant.helpers.entity_component import EntityComponent

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CALENDAR,
    Platform.SENSOR,
]


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


class _NaiveDatetimeError(Exception):
    """Raised when a naive datetime is encountered."""


def _coerce_event_dt(
    value: date | datetime,
    tz: ZoneInfo,
) -> datetime:
    """Normalize a CalendarEvent start/end to a tz-aware datetime.

    Args:
        value: Calendar event start or end (date or datetime).
        tz: Target timezone for all-day (date) events.

    Returns:
        A tz-aware datetime.

    Raises:
        _NaiveDatetimeError: If *value* is a naive datetime.
        TypeError: If *value* is neither ``date`` nor ``datetime``.

    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise _NaiveDatetimeError
        return value
    if isinstance(value, date):
        return datetime(
            value.year,
            value.month,
            value.day,
            tzinfo=tz,
        )
    msg = f"Expected date or datetime, got {type(value).__name__}"
    raise TypeError(msg)


async def _async_reconcile_active_stay(  # noqa: C901
    hass: HomeAssistant,
    coordinator: TurnoverCoordinator,
    state_machine: CleanlinessStateMachine,
    timezone_str: str,
) -> None:
    """Detect an active guest stay and reconcile cleanliness state.

    Queries the RC calendar entity for events spanning the current
    time.  If a guest stay is found where check-in (start) has
    passed but check-out (end) has not, triggers
    ``async_handle_checkin`` to recover from missed events (FR-008).

    After calendar-based checks, consults the RC check-in sensor:

    - If sensor is ``checked_in`` and state is not occupied,
      triggers checkin.
    - If sensor is ``checked_out`` or ``no_reservation`` and
      state is ``occupied``, triggers checkout.

    If no active stay is found and no sensor overrides apply,
    but the state machine is in the ``occupied`` phase, triggers
    ``async_handle_checkout`` to recover from missed checkout
    events.

    Args:
        hass: Home Assistant instance.
        coordinator: The turnover coordinator (provides calendar
            entity access).
        state_machine: The cleanliness state machine.
        timezone_str: IANA timezone string for the property.

    """
    now = datetime.now(tz=ZoneInfo(timezone_str))
    start = now - timedelta(days=1)
    end = now + timedelta(days=1)

    try:
        rc_events = await coordinator.calendar_entity.async_get_events(
            hass,
            start,
            end,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "RC calendar unavailable during startup reconciliation",
            exc_info=True,
        )
        return

    tz = ZoneInfo(timezone_str)

    calendar_has_active = False
    for event in rc_events:
        try:
            evt_start = _coerce_event_dt(event.start, tz)
            evt_end = _coerce_event_dt(event.end, tz)
        except TypeError:
            continue
        except _NaiveDatetimeError:
            _LOGGER.warning(
                "Skipping startup reconciliation due to naive RC event start=%s end=%s",
                event.start,
                event.end,
            )
            return

        if evt_start <= now < evt_end:
            if state_machine.phase == PHASE_OCCUPIED:
                # Already occupied; let the sensor check below
                # decide whether the guest actually checked out.
                calendar_has_active = True
                break
            await state_machine.async_handle_checkin(evt_end)
            return

    # Check RC check-in sensor for additional reconciliation
    sensor_id = _derive_rc_checkin_sensor_id(
        coordinator.calendar_entity.entity_id,
    )
    sensor_state = hass.states.get(sensor_id)
    if sensor_state is not None:
        sensor_val = sensor_state.state
        if sensor_val == RC_STATE_CHECKED_IN and state_machine.phase != PHASE_OCCUPIED:
            checkout_time = await _async_extract_checkout_time(
                sensor_state,
                hass,
                coordinator,
                timezone_str,
            )
            if checkout_time is not None:
                _LOGGER.info(
                    "Startup reconciliation: RC sensor "
                    "'%s' is checked_in; "
                    "triggering checkin",
                    sensor_id,
                )
                await state_machine.async_handle_checkin(
                    checkout_time,
                )
                return

        if (
            sensor_val
            in (
                RC_STATE_CHECKED_OUT,
                RC_STATE_NO_RESERVATION,
            )
            and state_machine.phase == PHASE_OCCUPIED
        ):
            _LOGGER.info(
                "Startup reconciliation: RC sensor "
                "'%s' is %s with occupied state; "
                "triggering checkout",
                sensor_id,
                sensor_val,
            )
            await state_machine.async_handle_checkout()
            return

    # No active stay found; if state machine is occupied,
    # the booking ended or disappeared — trigger checkout.
    if state_machine.phase == PHASE_OCCUPIED and not calendar_has_active:
        _LOGGER.info(
            "Startup reconciliation: occupied state with no "
            "active RC booking; triggering checkout",
        )
        await state_machine.async_handle_checkout()


def _build_coverage_delegates(  # noqa: PLR0913
    coordinator: TurnoverCoordinator,
    cache: EventCache,
    summary_prefix: str,
    property_name: str,
    tz_str: str,
    cleaning_duration: float,
) -> tuple[
    Callable[[datetime], Awaitable[bool]],
    Callable[[datetime], Awaitable[str | None]],
]:
    """Build coverage-checker and fallback-creator callables.

    Returns a pair of async callables that check whether a turnover
    event covers a given checkout time and, if not, create a fallback
    trailing event.

    Args:
        coordinator: The turnover coordinator with cached events.
        cache: The event cache for persisting fallback events.
        summary_prefix: Prefix for event summaries.
        property_name: Property name for event summaries.
        tz_str: IANA timezone string for the property.
        cleaning_duration: Cleaning duration in hours.

    Returns:
        Tuple of (coverage_checker, fallback_creator).

    """

    async def _check(checkout_time: datetime) -> bool:
        """Check if a turnover event covers the checkout time."""
        for event in coordinator.cache_events.values():
            if event.dtstart <= checkout_time <= event.dtend:
                return True
        return False

    async def _create(checkout_time: datetime) -> str:
        """Create a fallback turnover event and return its UID."""
        tz = ZoneInfo(tz_str)
        local_checkout = checkout_time.astimezone(tz)
        uid = f"{secrets.token_hex(8)}@turnovercal.homeassistant"
        fallback = TurnoverEvent(
            uid=uid,
            summary=f"{summary_prefix} {property_name}",
            dtstart=local_checkout,
            dtend=local_checkout
            + timedelta(
                hours=cleaning_duration,
            ),
            timezone=tz_str,
            source_checkout_id=uid,
            source_checkin_id=None,
            created_at=datetime.now(tz=ZoneInfo("UTC")),
            is_trailing=True,
            preserve=True,
        )
        await cache.async_add_event(fallback)
        return uid

    return _check, _create


def _register_rc_listeners(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entity_id: str,
    state_machine: CleanlinessStateMachine,
) -> None:
    """Subscribe to RC check-in / check-out bus events.

    Filters events to only those matching the configured calendar
    entity ID and delegates to the state machine.

    Args:
        hass: Home Assistant instance.
        entry: Config entry for unload tracking.
        entity_id: The RC calendar entity ID to filter on.
        state_machine: The cleanliness state machine.

    """

    async def _handle_rc_checkin(event: Event) -> None:
        """Handle RC check-in bus event."""
        data = event.data or {}
        if data.get("entity_id", "") != entity_id:
            return
        raw_checkout = data.get("checkout_time")
        if raw_checkout is None:
            return
        try:
            checkout_dt = (
                datetime.fromisoformat(raw_checkout)
                if isinstance(raw_checkout, str)
                else raw_checkout
            )
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Ignoring RC check-in: malformed checkout_time %r",
                raw_checkout,
            )
            return
        if not isinstance(checkout_dt, datetime) or checkout_dt.tzinfo is None:
            _LOGGER.warning(
                "Ignoring RC check-in: checkout_time is not tz-aware datetime: %r",
                checkout_dt,
            )
            return
        await state_machine.async_handle_checkin(checkout_dt)

    async def _handle_rc_checkout(event: Event) -> None:
        """Handle RC check-out bus event."""
        data = event.data or {}
        if data.get("entity_id", "") != entity_id:
            return
        await state_machine.async_handle_checkout()

    unsub_checkin = hass.bus.async_listen(
        EVENT_RC_CHECKIN,
        _handle_rc_checkin,
    )
    unsub_checkout = hass.bus.async_listen(
        EVENT_RC_CHECKOUT,
        _handle_rc_checkout,
    )
    entry.async_on_unload(unsub_checkin)
    entry.async_on_unload(unsub_checkout)


def _derive_rc_checkin_sensor_id(calendar_entity_id: str) -> str:
    """Derive the RC check-in sensor entity ID from the calendar.

    Args:
        calendar_entity_id: The RC calendar entity ID
            (e.g. ``calendar.rental_control_myplace``).

    Returns:
        The derived sensor entity ID
        (e.g. ``sensor.rental_control_myplace_checkin``).

    """
    name = calendar_entity_id.removeprefix("calendar.")
    return f"sensor.{name}_checkin"


def _register_rc_sensor_listener(  # noqa: PLR0913
    hass: HomeAssistant,
    entry: ConfigEntry,
    calendar_entity_id: str,
    state_machine: CleanlinessStateMachine,
    coordinator: TurnoverCoordinator,
    timezone_str: str,
) -> bool:
    """Subscribe to the RC check-in sensor state changes.

    Monitors the Rental Control check-in sensor as the primary
    detection mechanism for guest check-in / check-out
    transitions.  Falls back gracefully if the sensor entity
    does not exist.

    Args:
        hass: Home Assistant instance.
        entry: Config entry for unload tracking.
        calendar_entity_id: The RC calendar entity ID.
        state_machine: The cleanliness state machine.
        coordinator: The turnover coordinator.
        timezone_str: IANA timezone string for the property.

    Returns:
        True if the listener was registered, False otherwise.

    """
    sensor_id = _derive_rc_checkin_sensor_id(calendar_entity_id)

    if hass.states.get(sensor_id) is None:
        _LOGGER.info(
            "RC check-in sensor '%s' has no current state; "
            "listener registered and will activate when "
            "the entity becomes available",
            sensor_id,
        )

    async def _handle_sensor_change(
        event: Event[EventStateChangedData],
    ) -> None:
        """Handle RC check-in sensor state changes."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None:
            return

        new_val = new_state.state
        old_val = old_state.state if old_state else None

        if new_val == RC_STATE_CHECKED_IN and old_val != RC_STATE_CHECKED_IN:
            checkout_time = await _async_extract_checkout_time(
                new_state,
                hass,
                coordinator,
                timezone_str,
            )
            if checkout_time is not None:
                _LOGGER.info(
                    "RC sensor '%s': %s -> %s; triggering checkin",
                    sensor_id,
                    old_val,
                    new_val,
                )
                await state_machine.async_handle_checkin(
                    checkout_time,
                )
            else:
                _LOGGER.warning(
                    "RC sensor '%s': %s -> %s "
                    "but no checkout_time available; "
                    "skipping checkin",
                    sensor_id,
                    old_val,
                    new_val,
                )
            return

        if old_val == RC_STATE_CHECKED_IN and new_val in (
            RC_STATE_CHECKED_OUT,
            RC_STATE_NO_RESERVATION,
            RC_STATE_AWAITING_CHECKIN,
        ):
            _LOGGER.info(
                "RC sensor '%s': %s -> %s; triggering checkout",
                sensor_id,
                old_val,
                new_val,
            )
            await state_machine.async_handle_checkout()

    unsub = async_track_state_change_event(
        hass,
        sensor_id,
        _handle_sensor_change,
    )
    entry.async_on_unload(unsub)

    _LOGGER.debug(
        "Registered RC check-in sensor listener for '%s'",
        sensor_id,
    )
    return True


async def _async_extract_checkout_time(
    sensor_state: object,
    hass: HomeAssistant,
    coordinator: TurnoverCoordinator,
    timezone_str: str,
) -> datetime | None:
    """Extract checkout_time from the RC sensor or calendar.

    Tries the sensor's ``checkout_time`` attribute first, then
    falls back to querying the RC calendar for an active booking.

    Args:
        sensor_state: The HA State object for the RC sensor.
        hass: Home Assistant instance.
        coordinator: The turnover coordinator.
        timezone_str: IANA timezone string for the property.

    Returns:
        A timezone-aware checkout datetime, or None.

    """
    attrs = getattr(sensor_state, "attributes", {}) or {}
    raw = attrs.get("checkout_time")
    if raw is not None:
        try:
            checkout_dt = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            checkout_dt = None
        if isinstance(checkout_dt, datetime) and checkout_dt.tzinfo is not None:
            return checkout_dt

    # Fallback: query calendar for active booking
    now = datetime.now(tz=ZoneInfo(timezone_str))
    tz = ZoneInfo(timezone_str)
    start = now - timedelta(days=1)
    end = now + timedelta(days=1)
    try:
        rc_events = await coordinator.calendar_entity.async_get_events(
            hass,
            start,
            end,
        )
    except Exception:  # noqa: BLE001
        return None

    for event in rc_events:
        try:
            evt_start = _coerce_event_dt(event.start, tz)
            evt_end = _coerce_event_dt(event.end, tz)
        except (TypeError, _NaiveDatetimeError):
            continue

        if evt_start <= now < evt_end:
            return evt_end

    return None


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
        config_entry_id=entry.entry_id,
    )

    cleaning_duration = options.get(
        CONF_CLEANING_DURATION_HOURS,
        DEFAULT_CLEANING_DURATION_HOURS,
    )
    cleanliness_store = CleanlinessStateStore(hass, entry.entry_id)

    coverage_checker, fallback_creator = _build_coverage_delegates(
        coordinator,
        cache,
        summary_prefix,
        property_name,
        tz_str,
        cleaning_duration,
    )

    state_machine = CleanlinessStateMachine(
        hass=hass,
        entry_id=entry.entry_id,
        store=cleanliness_store,
        cleaning_duration_hours=cleaning_duration,
        coverage_checker=coverage_checker,
        fallback_creator=fallback_creator,
    )
    await state_machine.async_initialize()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "cache": cache,
        "cleanliness": state_machine,
        "feed_token": feed_token,
        "timezone_str": tz_str,
        "summary_prefix": summary_prefix,
        "property_name": property_name,
    }

    # Register device for this config entry
    device_reg = dr.async_get(hass)
    device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"TurnoverCal {property_name}",
        manufacturer="TurnoverCal",
        entry_type=dr.DeviceEntryType.SERVICE,
    )

    # Register HTTP view (idempotent)
    hass.http.register_view(TurnoverCalView())

    # Start coordinator
    await coordinator.async_config_entry_first_refresh()

    # Startup reconciliation: detect active guest stay (FR-008)
    await _async_reconcile_active_stay(
        hass,
        coordinator,
        state_machine,
        tz_str,
    )

    # Register services (idempotent)
    await async_setup_services(hass)

    # Forward platform setup (calendar + sensor entities)
    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    # Register Keymaster listener if lock monitoring is enabled
    if lock_monitoring and lock_entity_id:
        unsub_lock = hass.bus.async_listen(
            EVENT_KEYMASTER,
            coordinator.handle_lock_event,
        )
        entry.async_on_unload(unsub_lock)

    # Register RC check-in / check-out event listeners (fallback)
    _register_rc_listeners(hass, entry, entity_id, state_machine)

    # Register RC check-in sensor listener (primary detection)
    _register_rc_sensor_listener(
        hass,
        entry,
        entity_id,
        state_machine,
        coordinator,
        tz_str,
    )

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
    if not unload_ok:
        return False

    domain_data = hass.data.get(DOMAIN)
    if domain_data is None:
        return True
    cleanliness = domain_data.get(entry.entry_id, {}).get(
        "cleanliness",
    )
    if cleanliness is not None:
        await cleanliness.async_shutdown()
    coordinator = domain_data.get(entry.entry_id, {}).get(
        "coordinator",
    )
    if coordinator is not None:
        await coordinator.async_shutdown()
    domain_data.pop(entry.entry_id, None)

    # Unregister services when last entry is unloaded
    if not domain_data:
        await async_unload_services(hass)

    return True
