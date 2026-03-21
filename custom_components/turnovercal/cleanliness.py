# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Cleanliness state tracking for the TurnoverCal integration.

Provides the CleanlinessState model for per-property state and the
CleanlinessStateMachine that manages phase lifecycle transitions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from homeassistant.helpers.event import async_track_point_in_time

from custom_components.turnovercal.const import (
    PHASE_AWAITING_CLEANING,
    PHASE_BEING_CLEANED,
    PHASE_CLEAN,
    PHASE_OCCUPIED,
    REASON_CLEANING_DURATION_ELAPSED,
    REASON_GUEST_CHECKIN,
    REASON_GUEST_CHECKOUT,
    REASON_MID_STAY_CANCELLATION,
    REASON_STARTUP_RECONCILIATION,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

    from custom_components.turnovercal.cleanliness_store import (
        CleanlinessStateStore,
    )

_LOGGER = logging.getLogger(__name__)

_UTC = ZoneInfo("UTC")

VALID_PHASES: frozenset[str] = frozenset(
    {
        PHASE_CLEAN,
        PHASE_OCCUPIED,
        PHASE_AWAITING_CLEANING,
        PHASE_BEING_CLEANED,
    }
)


def _validate_tz_aware(dt: datetime, field_name: str) -> None:
    """Raise ValueError if *dt* is a naive (tzinfo-less) datetime.

    Args:
        dt: The datetime value to check.
        field_name: Name of the field, used in the error message.

    Raises:
        ValueError: If *dt* has no tzinfo.

    """
    if dt.tzinfo is None:
        msg = f"'{field_name}' must be a timezone-aware datetime, got naive"
        raise ValueError(msg)


class CleanlinessState:
    """Per-property cleanliness state managed by the state machine.

    Tracks the current dirty/clean status, lifecycle phase, transition
    timestamps, and optional timer information for the ``being_cleaned``
    phase.
    """

    is_dirty: bool
    phase: str
    last_transition_at: datetime
    last_transition_reason: str
    timer_target: datetime | None
    dirty_since: datetime | None
    associated_checkout_time: datetime | None
    config_entry_id: str

    def __init__(  # noqa: PLR0913
        self,
        *,
        is_dirty: bool,
        phase: str,
        last_transition_at: datetime,
        last_transition_reason: str,
        timer_target: datetime | None = None,
        dirty_since: datetime | None = None,
        associated_checkout_time: datetime | None = None,
        config_entry_id: str,
    ) -> None:
        """Initialize a CleanlinessState with validation.

        Args:
            is_dirty: Whether the property is currently dirty.
            phase: Current lifecycle phase (must be a valid phase).
            last_transition_at: When the last transition occurred (UTC).
            last_transition_reason: Why the last transition occurred.
            timer_target: Cleaning timer target (UTC), for being_cleaned.
            dirty_since: Start of the current dirty period (UTC).
            associated_checkout_time: Checkout time for fallback (UTC).
            config_entry_id: Config entry this state belongs to.

        Raises:
            ValueError: If *phase* is not one of the four valid phases
                or any datetime argument is naive (missing tzinfo).

        """
        if phase not in VALID_PHASES:
            msg = f"Invalid phase '{phase}', must be one of {sorted(VALID_PHASES)}"
            raise ValueError(msg)

        _validate_tz_aware(last_transition_at, "last_transition_at")
        if timer_target is not None:
            _validate_tz_aware(timer_target, "timer_target")
        if dirty_since is not None:
            _validate_tz_aware(dirty_since, "dirty_since")
        if associated_checkout_time is not None:
            _validate_tz_aware(
                associated_checkout_time,
                "associated_checkout_time",
            )

        self.is_dirty = is_dirty
        self.phase = phase
        self.last_transition_at = last_transition_at
        self.last_transition_reason = last_transition_reason
        self.timer_target = timer_target
        self.dirty_since = dirty_since
        self.associated_checkout_time = associated_checkout_time
        self.config_entry_id = config_entry_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize this state to a JSON-compatible dict.

        All datetime fields are stored as ISO 8601 strings with UTC
        ``+00:00`` offset.  Optional ``None`` fields are stored as
        JSON ``null``.

        Returns:
            A JSON-serializable dictionary.

        """
        return {
            "is_dirty": self.is_dirty,
            "phase": self.phase,
            "last_transition_at": (
                self.last_transition_at.astimezone(_UTC).isoformat()
            ),
            "last_transition_reason": self.last_transition_reason,
            "timer_target": (
                self.timer_target.astimezone(_UTC).isoformat()
                if self.timer_target is not None
                else None
            ),
            "dirty_since": (
                self.dirty_since.astimezone(_UTC).isoformat()
                if self.dirty_since is not None
                else None
            ),
            "associated_checkout_time": (
                self.associated_checkout_time.astimezone(_UTC).isoformat()
                if self.associated_checkout_time is not None
                else None
            ),
            "config_entry_id": self.config_entry_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CleanlinessState:
        """Deserialize a CleanlinessState from a dict.

        Parses ISO 8601 datetime strings back into timezone-aware
        datetime objects.

        Args:
            data: Dictionary previously produced by ``to_dict()``.

        Returns:
            A new CleanlinessState instance.

        """
        last_transition_at = datetime.fromisoformat(
            data["last_transition_at"],
        )

        timer_target = None
        if data.get("timer_target") is not None:
            timer_target = datetime.fromisoformat(data["timer_target"])

        dirty_since = None
        if data.get("dirty_since") is not None:
            dirty_since = datetime.fromisoformat(data["dirty_since"])

        associated_checkout_time = None
        if data.get("associated_checkout_time") is not None:
            associated_checkout_time = datetime.fromisoformat(
                data["associated_checkout_time"],
            )

        return cls(
            is_dirty=data["is_dirty"],
            phase=data["phase"],
            last_transition_at=last_transition_at,
            last_transition_reason=data["last_transition_reason"],
            timer_target=timer_target,
            dirty_since=dirty_since,
            associated_checkout_time=associated_checkout_time,
            config_entry_id=data["config_entry_id"],
        )


class CleanlinessStateMachine:
    """State machine managing the cleanliness lifecycle for a property.

    Owns the current ``CleanlinessState`` and provides property
    accessors, persistence via a ``CleanlinessStateStore``, and a
    callback pattern for entity listeners.  Transition methods are
    added in later phases per user story.
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        store: CleanlinessStateStore,
        cleaning_duration_hours: float,
        coverage_checker: Callable[[datetime], Awaitable[bool]] | None = None,
        fallback_creator: Callable[[datetime], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the cleanliness state machine.

        Args:
            hass: Home Assistant instance.
            entry_id: Config entry ID this machine belongs to.
            store: Persistent storage for the cleanliness state.
            cleaning_duration_hours: Cleaning timer duration in hours.
            coverage_checker: Optional async callable that checks
                whether a turnover event covers a given checkout time.
            fallback_creator: Optional async callable that creates a
                fallback turnover event for a given checkout time.

        """
        self._hass = hass
        self._entry_id = entry_id
        self._store = store
        self._cleaning_duration_hours = cleaning_duration_hours
        self._coverage_checker = coverage_checker
        self._fallback_creator = fallback_creator
        self._state: CleanlinessState | None = None
        self._timer_unsub: CALLBACK_TYPE | None = None
        self._callbacks: list[Callable[[], None]] = []

    @property
    def state(self) -> CleanlinessState:
        """Return the current cleanliness state.

        Raises:
            RuntimeError: If ``async_initialize()`` has not been called.

        Returns:
            The current CleanlinessState.

        """
        if self._state is None:
            msg = "State machine not initialized. Call async_initialize() first."
            raise RuntimeError(msg)
        return self._state

    @property
    def is_dirty(self) -> bool:
        """Return whether the property is currently dirty.

        Returns:
            True if the property is dirty, False if clean.

        """
        return self.state.is_dirty

    @property
    def phase(self) -> str:
        """Return the current cleanliness phase.

        Returns:
            The current phase string constant.

        """
        return self.state.phase

    async def async_initialize(self) -> None:
        """Load state from store or create default clean state.

        If a persisted state exists in the store it is used directly.
        Otherwise a default *clean* state is created and its
        persistence is scheduled via the store.

        When the loaded state has ``phase=PHASE_BEING_CLEANED`` with a
        ``timer_target``, the timer is reconstituted:
        - If the target time has already passed the state transitions
          to clean immediately.
        - Otherwise a timer is scheduled for the remaining duration.
        """
        loaded = await self._store.async_load()
        if loaded is not None:
            self._state = loaded
            await self._async_reconstitute_timer()
        else:
            now = datetime.now(tz=_UTC)
            self._state = CleanlinessState(
                is_dirty=False,
                phase=PHASE_CLEAN,
                last_transition_at=now,
                last_transition_reason=REASON_STARTUP_RECONCILIATION,
                config_entry_id=self._entry_id,
            )
            self._persist()

    async def async_shutdown(self) -> None:
        """Cancel any active timer and clean up resources."""
        if self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None

    def register_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback invoked on state changes.

        Args:
            callback: A no-argument callable to invoke on transitions.

        Returns:
            A callable that, when called, unregisters the callback.

        """
        self._callbacks.append(callback)

        def _unregister() -> None:
            """Remove the registered callback."""
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return _unregister

    def unregister_callback(self, callback: Callable[[], None]) -> None:
        """Remove a previously registered state change callback.

        No-op if the callback is not currently registered.

        Args:
            callback: The callback to remove.

        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _persist(self) -> None:
        """Schedule a batched save of the current state to the store."""
        if self._state is not None:
            self._store.schedule_save(self._state)

    def _fire_callbacks(self) -> None:
        """Invoke all registered state-change callbacks."""
        for callback in list(self._callbacks):
            try:
                callback()
            except Exception:
                _LOGGER.exception(
                    "Error in cleanliness callback: %r",
                    callback,
                )

    async def async_handle_checkin(
        self,
        checkout_time: datetime,
    ) -> None:
        """Handle a guest check-in event.

        Transitions the property to dirty with phase ``occupied``.
        If the property is already occupied this is a no-op.  If the
        property is in ``being_cleaned`` phase the cleaning timer is
        cancelled and the phase moves to ``occupied`` (FR-017).

        After transitioning, validates that a turnover event covers the
        upcoming checkout via the ``coverage_checker`` / ``fallback_creator``
        delegates.

        Args:
            checkout_time: The expected checkout time for this stay.

        """
        assert self._state is not None  # noqa: S101

        if self._state.phase == PHASE_OCCUPIED:
            return

        if not isinstance(checkout_time, datetime) or checkout_time.tzinfo is None:
            msg = f"checkout_time must be a tz-aware datetime, got {checkout_time!r}"
            raise ValueError(msg)

        # Cancel cleaning timer if being_cleaned (FR-017)
        if self._state.phase == PHASE_BEING_CLEANED and self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None

        now = datetime.now(tz=_UTC)
        self._state = CleanlinessState(
            is_dirty=True,
            phase=PHASE_OCCUPIED,
            last_transition_at=now,
            last_transition_reason=REASON_GUEST_CHECKIN,
            dirty_since=self._state.dirty_since or now,
            associated_checkout_time=checkout_time,
            config_entry_id=self._entry_id,
        )
        self._persist()
        self._fire_callbacks()

        try:
            await self._validate_cleaning_coverage(checkout_time)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to validate cleaning coverage after "
                "check-in; continuing with occupied state",
                exc_info=True,
            )

    async def async_handle_checkout(self) -> None:
        """Handle a guest check-out event.

        Transitions from ``occupied`` to ``awaiting_cleaning``.
        No-op if not currently in the ``occupied`` phase.
        """
        assert self._state is not None  # noqa: S101

        if self._state.phase != PHASE_OCCUPIED:
            return

        now = datetime.now(tz=_UTC)
        self._state = CleanlinessState(
            is_dirty=True,
            phase=PHASE_AWAITING_CLEANING,
            last_transition_at=now,
            last_transition_reason=REASON_GUEST_CHECKOUT,
            dirty_since=self._state.dirty_since or now,
            associated_checkout_time=(self._state.associated_checkout_time),
            config_entry_id=self._entry_id,
        )
        self._persist()
        self._fire_callbacks()

    async def async_handle_midstay_cancellation(
        self,
        check_in_time: datetime,
    ) -> None:
        """Handle a mid-stay reservation cancellation.

        Transitions the property to dirty with
        ``phase=PHASE_AWAITING_CLEANING`` and
        ``reason=REASON_MID_STAY_CANCELLATION``.  Creates an immediate
        cleaning event via the ``fallback_creator`` delegate.

        No-op when the check-in time has not yet passed (pre-arrival
        cancellation per FR-011) or when the property is already in
        ``PHASE_AWAITING_CLEANING`` or ``PHASE_BEING_CLEANED``.
        Occupied properties transition to awaiting cleaning.

        Args:
            check_in_time: The original check-in time of the cancelled
                reservation.

        """
        assert self._state is not None  # noqa: S101

        if not isinstance(check_in_time, datetime) or check_in_time.tzinfo is None:
            msg = f"check_in_time must be a tz-aware datetime, got {check_in_time!r}"
            raise ValueError(msg)

        now = datetime.now(tz=_UTC)

        # FR-011: pre-arrival cancellation -- check-in not yet passed
        if check_in_time > now:
            return

        # FR-025: already awaiting or undergoing cleaning -- skip
        if self._state.phase in (
            PHASE_AWAITING_CLEANING,
            PHASE_BEING_CLEANED,
        ):
            return

        # Cancel cleaning timer if transitioning from being_cleaned
        if self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None

        self._state = CleanlinessState(
            is_dirty=True,
            phase=PHASE_AWAITING_CLEANING,
            last_transition_at=now,
            last_transition_reason=REASON_MID_STAY_CANCELLATION,
            dirty_since=now,
            config_entry_id=self._entry_id,
        )

        if self._fallback_creator is not None:
            await self._fallback_creator(now)

        self._persist()
        self._fire_callbacks()

    async def _validate_cleaning_coverage(
        self,
        checkout_time: datetime,
    ) -> None:
        """Ensure a turnover event covers the checkout time.

        Uses the injected ``coverage_checker`` delegate to determine
        whether an existing turnover event already covers the period.
        If not, the ``fallback_creator`` delegate is called to
        synthesise a fallback event.

        Args:
            checkout_time: The checkout time to validate coverage for.

        """
        if self._coverage_checker is None or self._fallback_creator is None:
            return

        covered = await self._coverage_checker(checkout_time)
        if not covered:
            await self._fallback_creator(checkout_time)

    async def _async_reconstitute_timer(self) -> None:
        """Reconstitute a cleaning timer after restart if needed.

        Called during ``async_initialize()`` when a persisted state is
        loaded.  If the state has ``phase=PHASE_BEING_CLEANED`` with a
        ``timer_target``, either:
        - transitions to clean immediately when the target has passed,
          or
        - schedules a new timer for the remaining duration.
        """
        assert self._state is not None  # noqa: S101
        if self._state.phase != PHASE_BEING_CLEANED or self._state.timer_target is None:
            return

        # Cancel any existing timer before reconstituting
        if self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None

        target = self._state.timer_target
        now = datetime.now(tz=_UTC)
        if target <= now:
            self._state = CleanlinessState(
                is_dirty=False,
                phase=PHASE_CLEAN,
                last_transition_at=now,
                last_transition_reason=REASON_CLEANING_DURATION_ELAPSED,
                config_entry_id=self._entry_id,
            )
            self._persist()
            self._fire_callbacks()
        else:
            self._timer_unsub = async_track_point_in_time(
                self._hass,
                self._async_timer_expired,
                target,
            )

    async def _async_timer_expired(self, _now: datetime) -> None:
        """Handle cleaning timer expiry.

        Transitions the state to clean, clears the timer, persists
        the state, and fires registered callbacks.

        Args:
            _now: The datetime at which the timer fired.

        """
        self._state = CleanlinessState(
            is_dirty=False,
            phase=PHASE_CLEAN,
            last_transition_at=_now,
            last_transition_reason=REASON_CLEANING_DURATION_ELAPSED,
            config_entry_id=self._entry_id,
        )
        self._timer_unsub = None
        self._persist()
        self._fire_callbacks()
