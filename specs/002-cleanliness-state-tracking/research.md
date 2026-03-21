<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Research: Property Cleanliness State Tracking

**Feature**: 002-cleanliness-state-tracking
**Date**: 2025-07-18

## R-001: State Persistence Mechanism

**Question**: How should cleanliness state be persisted across HA restarts
— extend the existing `CachedEventStore` or use a separate HA Store?

**Decision**: Use a **separate** HA Store (`CleanlinessStateStore`) dedicated
to cleanliness state.

**Rationale**: Cleanliness state has a different lifecycle and schema from
turnover events. Events are computed/recomputed on each polling cycle and
merged into cache; cleanliness state is driven by discrete transitions
(check-in, check-out, lock code, service calls). Mixing the two in one
store creates coupling between event merging and state management. A
separate store keeps each concern independent, allows independent
versioning, and avoids serialization/migration complexity when either
schema evolves.

**Alternatives Considered**:

- **Extend CachedEventStore**: Simpler single-store approach, but couples
  event cache schema evolution with state management. Event cache already
  has complex merge/cleanup logic; adding state transitions would increase
  the surface for bugs.
- **RestoreEntity only**: HA's `RestoreEntity` provides last-state
  restoration via `async_get_last_state()` and `async_get_last_extra_data()`.
  However, RestoreEntity data is best-effort — HA may discard it during
  upgrades or if entity IDs change. Using it as the *sole* persistence
  mechanism is unreliable for state that must survive 100% of restarts
  (SC-005). RestoreEntity will be used as a *secondary* fast-path to
  avoid waiting for store I/O during entity initialization.
- **Config entry data**: Too limited for dynamic state with timestamps.

## R-002: Cleaning Duration Timer Implementation

**Question**: How should the configurable cleaning duration timer be
implemented and survive restarts?

**Decision**: Use `homeassistant.helpers.event.async_track_point_in_time`
for the one-shot timer, with target completion time persisted in the
`CleanlinessStateStore`.

**Rationale**: `async_track_point_in_time` is the idiomatic HA way to
schedule a callback at a specific wall-clock time. It returns an
unsubscribe callable for cancellation. Persisting the target time (not
remaining duration) in the store means restart reconstitution is trivial:
if target time has passed → transition clean immediately; otherwise →
re-register timer for remaining duration.

**Alternatives Considered**:

- **`async_call_later(delay)`**: Simpler API but uses relative delay, making
  restart reconstitution harder (must persist start time + duration and
  recalculate). Also drifts if HA restart takes time.
- **`asyncio.call_later`**: Bypasses HA's event loop management; not
  shutdown-safe.
- **Polling-based check**: Check timer target in each coordinator update
  cycle. Would work but adds 0–5 minute latency to clean transitions
  (depending on poll interval). Timer-based is immediate.

## R-003: RC (Rental Control) Check-In/Check-Out Event Detection

**Question**: How should TurnoverCal detect Rental Control guest check-in
and check-out events during normal operation and on startup?

**Decision**: Dual detection strategy:

1. **Real-time**: Subscribe to RC-published HA bus events for check-in/
   check-out. Event names TBD pending RC feature delivery — use
   constants that can be updated.
2. **Startup reconciliation**: On integration load, query RC entity
   states to detect any check-ins/check-outs that occurred during
   downtime. Compare current RC state against persisted cleanliness
   state to identify missed transitions.

**Rationale**: Real-time listeners provide immediate detection (within one
event processing cycle per SC-001). Startup reconciliation catches
events missed during downtime (FR-008). This dual approach is consistent
with the spec requirement for both mechanisms.

**Alternatives Considered**:

- **Polling-only**: Already in place via coordinator update cycle, but adds
  up to 5 minutes of latency for dirty transitions. Not acceptable for
  SC-001 (within one event processing cycle).
- **State change listener on RC calendar entity**: RC calendar entity
  state changes on any event update, not just check-in/out. Too noisy
  and doesn't distinguish the specific transition type.
- **Real-time only**: Misses events during HA downtime.

## R-004: Mid-Stay Cancellation Detection

**Question**: How should TurnoverCal detect when a booking is removed
while the guest is mid-stay?

**Decision**: Compare active reservations between polling cycles in the
coordinator's `_async_update_data`. Track the set of "currently active"
bookings (check-in past, check-out future) and detect removals.

**Rationale**: This is explicitly called out in FR-009. The coordinator
already polls RC events on each cycle. Adding a comparison of active
bookings between cycles is a natural extension of the existing flow.
The comparison must account for "now" falling within a booking's
check-in to check-out window.

**Alternatives Considered**:

- **RC bus event for cancellations**: RC may not publish cancellation
  events — bookings simply disappear from the calendar. Polling-based
  detection is the reliable approach.
- **State change on booking entity**: RC calendar doesn't expose individual
  booking entities — it's a single calendar entity with multiple events.

## R-005: Binary Sensor Entity Architecture

**Question**: Should the binary sensor be a `CoordinatorEntity` tied to the
existing `TurnoverCoordinator`, or a standalone entity with its own
update mechanism?

**Decision**: The binary sensor will be a **standalone entity** that
receives state updates from a new `CleanlinessStateMachine` (which is
owned by the coordinator). The binary sensor subscribes to state
machine transitions via a callback, not via `CoordinatorEntity` data
updates.

**Rationale**: The coordinator's data is `dict[str, TurnoverEvent]` — the
event cache. Cleanliness state is orthogonal to this data structure.
Making the binary sensor a `CoordinatorEntity` would require overriding
`_handle_coordinator_update` to ignore the event data and check
cleanliness state instead, which is a code smell. A direct callback
from the state machine is cleaner and provides immediate updates without
waiting for the next coordinator cycle.

The binary sensor will still use `RestoreEntity` for fast startup
restoration and reference the same device for entity grouping.

**Alternatives Considered**:

- **CoordinatorEntity subclass**: Conceptually mismatched — coordinator data
  is events, not cleanliness state. Would require awkward data plumbing.
- **Second DataUpdateCoordinator**: Over-engineered for a simple state
  machine that only changes on discrete events.

## R-006: State Machine Design

**Question**: Should the phase lifecycle be implemented as an explicit
state machine or as ad-hoc state transitions in the coordinator?

**Decision**: Implement an explicit `CleanlinessStateMachine` class with
defined states, transitions, and guards.

**Rationale**: The spec defines a 4-phase lifecycle with specific rules
about which transitions are valid from which states, what side effects
each transition produces (timer start/cancel, event generation), and
edge cases (check-in during being_cleaned). An explicit state machine
makes these rules testable in isolation, documents the allowed
transitions, and prevents invalid state combinations. This aligns with
the constitution's requirement for low cyclomatic complexity — a state
machine distributes complexity across small, focused methods rather than
one large conditional block.

**Alternatives Considered**:

- **Ad-hoc if/elif in coordinator methods**: Simpler initially, but
  transitions spread across multiple methods become hard to reason about.
  Edge cases (check-in during being_cleaned) would require complex
  conditionals.
- **Third-party state machine library**: Unnecessary dependency for 4
  states and ~8 transitions.

## R-007: Service Action Entity Targeting

**Question**: How should `mark_dirty` and `mark_clean` services accept
targeting by binary sensor entity, calendar entity, or config entry ID?

**Decision**: Extend the existing `_resolve_coordinators` function in
`services.py` to accept binary sensor entity IDs in addition to
calendar entity IDs. Use entity registry lookups (not string parsing)
to map entity IDs to config entries.

**Rationale**: The existing pattern resolves calendar entities by matching
`coord.calendar_entity_id`. For binary sensors, we can use the entity
registry to look up the entity's `config_entry_id` from its `unique_id`
(which contains the config entry ID by convention). This is more robust
than string-parsing entity IDs. The `services.yaml` target section
already supports multi-domain entity selectors.

**Alternatives Considered**:

- **String parsing entity IDs**: Fragile — breaks if entity ID naming
  conventions change.
- **Separate resolver per service**: Duplicates logic. One resolver for
  all services is DRY.

## R-008: Cleaning Event Generation Strategy

**Question**: Where should fallback cleaning event generation live — in
the state machine, the coordinator, or a separate module?

**Decision**: The state machine emits transition events (callbacks). The
coordinator subscribes to these and handles event generation in its
existing event management flow. Fallback event generation is a method
on the coordinator that checks for existing coverage and creates events
as needed.

**Rationale**: The coordinator already owns event creation/merging logic
and has access to the event cache. Having the state machine directly
create events would require it to know about the cache and turnover
computation — violating single responsibility. The state machine's job
is to manage phase transitions and side effects (timer start/cancel);
event generation is a coordinator concern.

**Alternatives Considered**:

- **State machine creates events directly**: Couples state management
  to event cache — harder to test, harder to evolve independently.
- **Separate event generator service**: Over-engineered; the coordinator
  already does this for computed events.

## R-009: Configuration Flow for cleaning_duration_hours

**Question**: Where should `cleaning_duration_hours` appear in the config
flow — the general options step or the lock step?

**Decision**: Add `cleaning_duration_hours` to the **general options step**
(`async_step_init`), not the lock step.

**Rationale**: The cleaning duration timer fires after a lock code entry.
The minimum is 0.05 hours (3 minutes), guaranteeing the property does
not transition directly to "clean" on lock code entry (FR-012).
It's a property-level setting, not a lock-specific setting.
Property managers may want to configure it even before enabling
lock monitoring (e.g., planning ahead).
Placing it in the general step keeps it visible and accessible. The lock
step remains focused on lock-specific settings (device, slot, grace hours).

**Alternatives Considered**:

- **Lock step only**: Would hide the option when lock monitoring is disabled,
  but the spec says it controls the delay after lock code entry — which
  only applies when lock monitoring is active. However, the timer also
  applies to the `mark_cleaning_started` service (which doesn't require
  lock monitoring). General step is more inclusive.
- **New dedicated step**: Over-engineered for one field.
