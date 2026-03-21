<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Service Contracts: Property Cleanliness State Tracking

**Feature**: 002-cleanliness-state-tracking
**Date**: 2025-07-18

## Overview

TurnoverCal exposes three user-facing service contracts for this feature:

1. `turnovercal.mark_dirty` — Force a property to the dirty state
2. `turnovercal.mark_clean` — Force a property to the clean state
3. `turnovercal.mark_cleaning_started` — (existing) Signal cleaning has begun

All services follow the same targeting pattern established by
`mark_cleaning_started`.

---

## Service: `turnovercal.mark_dirty`

### Purpose

Forces a property into the "dirty" state with `phase = awaiting_cleaning`,
regardless of current state. Creates a fallback cleaning event if none
exists.

### Target

```yaml
target:
  entity:
    integration: turnovercal
    domain:
      - calendar
      - binary_sensor
```

### Fields

| Field             | Type         | Req   | Default | Description        |
| ----------------- | ------------ | ----- | ------- | ------------------ |
| `config_entry_id` | config_entry | false | —       | Alt. entity target |

### Responses

| Condition          | Response                             |
| ------------------ | ------------------------------------ |
| Success            | Void. State updated.                 |
| No matching entity | `ServiceValidationError`             |
|                    | key: `entity_not_found`              |
| Ambiguous target   | `ServiceValidationError`             |
|                    | key: `ambiguous_target`              |

### Example

```yaml
service: turnovercal.mark_dirty
target:
  entity_id: binary_sensor.turnovercal_beach_house_dirty
```

```yaml
service: turnovercal.mark_dirty
data:
  config_entry_id: "a1b2c3d4e5f6"
```

---

## Service: `turnovercal.mark_clean`

### Purpose (mark_clean)

Forces a property into the "clean" state immediately, regardless of
current phase. Cancels any active cleaning duration timer.

### Target (mark_clean)

```yaml
target:
  entity:
    integration: turnovercal
    domain:
      - calendar
      - binary_sensor
```

### Fields (mark_clean)

| Field             | Type         | Req   | Default | Description        |
| ----------------- | ------------ | ----- | ------- | ------------------ |
| `config_entry_id` | config_entry | false | —       | Alt. entity target |

### Behavior

| Current State       | Result                              |
| ------------------- | ----------------------------------- |
| `clean`             | No-op. Already clean.               |
| `occupied`          | → clean. Binary sensor off.         |
| `awaiting_cleaning` | → clean. Binary sensor off.         |
| `being_cleaned`     | → clean. Cancels timer. Sensor off. |

### Responses (mark_clean)

| Condition          | Response                             |
| ------------------ | ------------------------------------ |
| Success            | Void. State updated.                 |
| No matching entity | `ServiceValidationError`             |
|                    | key: `entity_not_found`              |
| Ambiguous target   | `ServiceValidationError`             |
|                    | key: `ambiguous_target`              |

### Example (mark_clean)

```yaml
service: turnovercal.mark_clean
target:
  entity_id: binary_sensor.turnovercal_beach_house_dirty
```

---

## Binary Sensor Entity Contract

### Entity ID Pattern

```text
binary_sensor.<config_entry_title_slug>_dirty
```

Where `<config_entry_title_slug>` is derived by HA from the config entry
title and translation key (e.g., `binary_sensor.beach_house_dirty`).

### Device Class

`BinarySensorDeviceClass.PROBLEM`

### State Mapping

| Property State | Binary Sensor State | `is_on` |
|----------------|---------------------|---------|
| Clean          | `off`               | `False` |
| Dirty          | `on`                | `True`  |

### Extra State Attributes

| Attribute                | Type     | Description                 |
| ------------------------ | -------- | --------------------------- |
| `phase`                  | string   | `clean`, `occupied`,        |
|                          |          | `awaiting_cleaning`, or     |
|                          |          | `being_cleaned`             |
| `last_transition_at`     | ISO 8601 | When last transition        |
|                          |          | occurred                    |
| `last_transition_reason` | string   | Reason for last transition  |
| `dirty_since`            | ISO 8601 | Dirty period start (or      |
|                          |          | null)                       |
| `timer_target`           | ISO 8601 | Auto-clean time (or null)   |

### State Change Events

The binary sensor fires standard HA `state_changed` events. Automations
can trigger on:

- `binary_sensor.<config_entry_title_slug>_dirty` → `on` (property became dirty)
- `binary_sensor.<config_entry_title_slug>_dirty` → `off` (property became clean)
- Attribute change on `phase` (e.g., `awaiting_cleaning` → `being_cleaned`)

---

## Configuration Contract

### New Options Flow Field

| Field                     | Type  | Default | Range     | Step | Location    |
| ------------------------- | ----- | ------- | --------- | ---- | ----------- |
| `cleaning_duration_hours` | float | 3.0     | 0.05 – 24 | 0.5  | Options init|

**Behavior**:

- Minimum 0.05 hours (3 minutes) — guarantees the property does not
  transition directly to "clean" on lock code entry (consistent with FR-012)
- Default 3.0 hours — delayed transition after lock code entry
- Changes take effect on next lock code entry (do not retroactively adjust
  running timers)

---

## Event Bus Contracts

### Inbound Events (Consumed)

| Event                          | Source    | Action                |
| ------------------------------ | --------- | --------------------- |
| `keymaster_lock_state_changed` | Keymaster | Lock code →           |
|                                |           | being_cleaned phase   |
|                                |           | (filter: entity_id,   |
|                                |           | state=unlocked, slot) |
| RC check-in event (TBD)        | RC        | → dirty/occupied      |
| RC check-out event (TBD)       | RC        | → awaiting_cleaning   |

### Outbound Behavior

No custom bus events emitted. State changes are reflected through the
binary sensor's standard `state_changed` events, which HA emits
automatically when entity state or attributes change.
