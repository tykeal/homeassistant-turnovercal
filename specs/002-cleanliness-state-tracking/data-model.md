<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Data Model: Property Cleanliness State Tracking

**Feature**: 002-cleanliness-state-tracking
**Date**: 2025-07-18

## Entities

### CleanlinessPhase (Enum)

Represents the four-phase lifecycle of a property's cleanliness state.

| Value                | Description                                        |
|----------------------|----------------------------------------------------|
| `clean`              | Property is ready for guests (binary sensor: off)  |
| `occupied`           | Guest is actively staying (binary sensor: on)      |
| `awaiting_cleaning`  | Post-check-out or manual dirty, no cleaner started |
| `being_cleaned`      | Cleaner lock code used, timer running              |

**Constraints**:

- Exactly four values; no extensions without spec amendment.
- `clean` is the only phase where the binary sensor reports "off."
- Phases `occupied`, `awaiting_cleaning`, and `being_cleaned` all report
  the binary sensor as "on" (dirty).

### TransitionReason (Enum/Literal)

Documents why a state transition occurred. Stored as a string attribute
on the binary sensor and in the persisted state.

| Value                       | Trigger                         |
| --------------------------- | ------------------------------- |
| `guest_checkin`             | RC check-in event detected      |
| `guest_checkout`            | RC check-out event (phase only) |
| `mid_stay_cancellation`     | Booking removed mid-stay        |
| `lock_code_entry`           | Cleaning lock code used         |
| `cleaning_duration_elapsed` | Cleaning timer expired          |
| `service_call_mark_clean`   | `mark_clean` service called     |
| `service_call_mark_dirty`   | `mark_dirty` service called     |
| `startup_reconciliation`    | State corrected on HA restart   |

### CleanlinessState (Dataclass)

Persisted per-property state managed by the `CleanlinessStateMachine`.

```text
CleanlinessState
├── is_dirty: bool                        # True = dirty, False = clean
├── phase: CleanlinessPhase               # Current lifecycle phase
├── last_transition_at: datetime (UTC)    # When the last transition occurred
├── last_transition_reason: str           # TransitionReason value
├── timer_target: datetime | None (UTC)   # Cleaning timer target
├── dirty_since: datetime | None (UTC)    # Start of dirty period
└── associated_checkout_time: datetime | None (UTC)  # For fallback
```

**Validation Rules**:

- `timer_target` MUST be non-None only when `phase == being_cleaned`.
- `timer_target` MUST be None when `phase != being_cleaned`.
- `dirty_since` MUST be non-None when `is_dirty == True`.
- `dirty_since` MUST be None when `is_dirty == False`.
- `last_transition_at` MUST always be set (initialized to creation time).
- `phase` and `is_dirty` MUST be consistent: `is_dirty == False` implies
  `phase == clean`; `is_dirty == True` implies `phase in {occupied,
  awaiting_cleaning, being_cleaned}`.

**Serialization**:

```json
{
  "is_dirty": false,
  "phase": "clean",
  "last_transition_at": "2026-03-15T14:00:00+00:00",
  "last_transition_reason": "cleaning_duration_elapsed",
  "timer_target": null,
  "dirty_since": null,
  "associated_checkout_time": null
}
```

### CleanlinessStateStore

Persistent storage wrapper using HA's `Store` class. Separate from the
existing `EventCache` (see R-001 in research.md).

```text
Store key: turnovercal_{entry_id}_cleanliness
Version: 1

Schema:
{
  "version": 1,
  "state": { ... CleanlinessState serialized ... }
}
```

**Methods**:

- `async_load() → CleanlinessState | None`: Load persisted state, return
  None if no prior state exists.
- `async_save(state: CleanlinessState) → None`: Persist state immediately.
- `schedule_save(state: CleanlinessState) → None`: Batch-persist with
  5-second delay (consistent with EventCache pattern).
- `async_delete() → None`: Remove persisted state (for
  integration unload cleanup).

## State Transitions

### Valid Transitions

```text
                    guest_checkin
    ┌──────────────────────────────────────┐
    │                                      ▼
  ┌─────┐   mark_dirty / mid_stay   ┌──────────┐
  │clean│ ──────────────────────────>│ occupied  │
  └─────┘   cancellation / check-in  └──────────┘
    ▲                                      │
    │                                      │ guest_checkout /
    │                                      │ mid_stay_cancellation
    │                                      ▼
    │  timer_elapsed /             ┌──────────────────┐
    │  mark_clean                  │awaiting_cleaning  │
    │                              └──────────────────┘
    │                                      │
    │                                      │ lock_code_entry
    │                                      ▼
    │  timer_elapsed /             ┌──────────────────┐
    │  mark_clean                  │ being_cleaned     │
    │◄─────────────────────────────└──────────────────┘
    │                                      │
    │        guest_checkin                 │
    │        (cancels timer)               │
    │              │                       │
    │              ▼                       │
    │         ┌──────────┐                 │
    │         │ occupied  │◄───────────────┘
    │         └──────────┘   mark_dirty (cancels timer)
    │              │              → awaiting_cleaning
    │              ▼
    │     (continues normal flow)
    │
    │   mark_clean (from any dirty phase)
    └──────────────────────────────────────┘
```

### Transition Table

#### From `clean`

| Trigger                   | New Phase           | Side Effects            |
| ------------------------- | ------------------- | ----------------------- |
| `guest_checkin`           | `occupied`          | Set dirty_since,        |
|                           |                     | validate event coverage |
| `mid_stay_cancellation`   | `awaiting_cleaning` | Set dirty_since, create |
|                           |                     | fallback cleaning event |
| `service_call_mark_dirty` | `awaiting_cleaning` | Set dirty_since, create |
|                           |                     | immediate cleaning      |
|                           |                     | event (trailing dur.)   |

#### From `occupied`

| Trigger                   | New Phase           | Side Effects            |
| ------------------------- | ------------------- | ----------------------- |
| `guest_checkout`          | `awaiting_cleaning` | (event already          |
|                           |                     | validated at check-in)  |
| `mid_stay_cancellation`   | `awaiting_cleaning` | Validate event coverage |
| `service_call_mark_clean` | `clean`             | Clear dirty_since,      |
|                           |                     | cancel timer if any     |
| `service_call_mark_dirty` | `occupied` (no-op)  | No duplicate event      |

#### From `awaiting_cleaning`

| Trigger                   | New Phase       | Side Effects              |
| ------------------------- | --------------- | ------------------------- |
| `lock_code_entry`         | `being_cleaned` | Start timer, set target   |
| `guest_checkin`           | `occupied`      | Validate event coverage   |
|                           |                 | for new check-out         |
| `service_call_mark_clean` | `clean`         | Clear dirty_since         |
| `service_call_mark_dirty` | (no-op)         | No duplicate event        |

#### From `being_cleaned`

| Trigger                    | New Phase           | Side Effects          |
| -------------------------- | ------------------- | --------------------- |
| `cleaning_duration_elapsed`| `clean`             | Clear dirty_since,    |
|                            |                     | clear timer_target    |
| `service_call_mark_clean`  | `clean`             | Cancel timer, clear   |
|                            |                     | dirty_since + target  |
| `service_call_mark_dirty`  | `awaiting_cleaning` | Cancel timer, clear   |
|                            |                     | target, validate      |
| `guest_checkin`            | `occupied`          | Cancel timer, clear   |
|                            |                     | target, validate      |

### Invalid / No-Op Transitions

| Current Phase | Trigger                   | Result                |
| ------------- | ------------------------- | --------------------- |
| `clean`       | `service_call_mark_clean` | No-op: already clean  |
| `clean`       | `lock_code_entry`         | No-op for cleanliness |
| `clean`       | `guest_checkout`          | No-op: not dirty      |
| `occupied`    | `lock_code_entry`         | No-op for cleanliness |
| `occupied`    | `guest_checkin`           | No-op: already in use |

## Relationships

```text
ConfigEntry (1) ──── (1) TurnoverCoordinator
     │                         │
     │                         ├── owns ──── (1) EventCache
     │                         │                    └── dict[str, TurnoverEvent]
     │                         │
     │                         ├── owns ──── (1) CleanlinessStateMachine
     │                         │                    ├── CleanlinessState (persisted)
     │                         │                    ├── CleanlinessStateStore
     │                         │                    └── timer management
     │                         │
     │                         └── notifies ── (1) TurnoverCalCleanlinessSensor
     │
     ├── (1) TurnoverCalCalendarEntity (CoordinatorEntity)
     ├── (1) TurnoverCalFeedUrlSensor
     └── (1) TurnoverCalCleanlinessSensor (RestoreEntity + BinarySensorEntity)
```

## New Module Breakdown

| Module                  | Responsibility                |
| ----------------------- | ----------------------------- |
| `cleanliness.py`        | `CleanlinessPhase` enum,      |
|                         | `CleanlinessState` dataclass, |
|                         | `CleanlinessStateMachine`     |
| `cleanliness_store.py`  | HA Store wrapper              |
| `binary_sensor.py`      | `TurnoverCalCleanliness-`     |
|                         | `Sensor`                      |
| `services.py` (ext.)    | `mark_dirty`/`mark_clean` +   |
|                         | resolver extension            |
| `coordinator.py` (ext.) | State machine ownership, RC   |
|                         | event integration             |
| `__init__.py` (ext.)    | Binary sensor platform setup, |
|                         | RC listeners, store init      |
| `config_flow.py` (ext.) | `cleaning_duration_hours` opt |
| `const.py` (ext.)       | Phase/event/default constants |
| `strings.json` (ext.)   | Binary sensor + service i18n  |
| `services.yaml` (ext.)  | `mark_dirty`/`mark_clean`     |
|                         | definitions                   |
