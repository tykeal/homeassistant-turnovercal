<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Quickstart: Property Cleanliness State Tracking

**Feature**: 002-cleanliness-state-tracking
**Branch**: `002-cleanliness-state-tracking`

## Developer Setup

```bash
# Clone and checkout feature branch
git checkout 002-cleanliness-state-tracking

# Install dependencies
uv sync --group dev

# Run tests
uv run pytest tests/

# Run linting
uv run ruff check custom_components/ tests/
uv run mypy custom_components/turnovercal/
```

## Architecture Overview

### New Modules

| File                   | Purpose                          |
| ---------------------- | -------------------------------- |
| `cleanliness.py`       | State machine: phases, state,    |
|                        | `CleanlinessStateMachine`        |
| `cleanliness_store.py` | HA Store wrapper for persisting  |
|                        | cleanliness state                |
| `binary_sensor.py`     | `CleanlinessBinarySensor` entity |

### Modified Modules

| File                   | Changes                            |
| ---------------------- | ---------------------------------- |
| `__init__.py`          | +BINARY_SENSOR platform, +store,   |
|                        | +RC (Rental Control) listeners     |
| `coordinator.py`       | +state machine, +mid-stay, +events |
| `config_flow.py`       | +`cleaning_duration_hours` option  |
| `const.py`             | +phase/event/default/config consts |
| `services.py`          | +`mark_dirty`/`mark_clean`,        |
|                        | +resolver extension                |
| `services.yaml`        | +new service definitions           |
| `strings.json`         | +binary sensor + service strings   |
| `translations/en.json` | +matching English translations     |

### Data Flow

```text
RC Check-In Event ──► Coordinator ──► CleanlinessStateMachine
                                              │
Keymaster Unlock ──► Coordinator ──────────►  │
                                              │
mark_dirty/clean ──► Services ──► Coord ───►  │
                                              │
                                              ▼
                                     State Transition
                                       │         │
                                       │         ▼
                                       │   CleanlinessStateStore
                                       │   (persistence)
                                       ▼
                                 CleanlinessBinarySensor
                                 (entity update callback)
```

### Phase Lifecycle

```text
clean → occupied → awaiting_cleaning → being_cleaned → clean
  │                                                       │
  └────────── mark_dirty ──► awaiting_cleaning ───────────┘
                                                   │
                                            mark_clean (any phase)
```

## Key Design Decisions

1. **Separate store** for cleanliness state (not in EventCache)
   — see research.md R-001
2. **Explicit state machine** in `cleanliness.py`
   — see research.md R-006
3. **`async_track_point_in_time`** for cleaning timer
   — see research.md R-002
4. **Dual detection** (real-time events + startup reconciliation)
   — see research.md R-003
5. **`cleaning_duration_hours`** in general options step
   — see research.md R-009

## Testing Strategy

### TDD Flow

All tests follow Red-Green-Refactor per the constitution:

1. **State machine unit tests** (`test_cleanliness.py`): Test all
   transitions, guards, edge cases in isolation.
2. **Store tests** (`test_cleanliness_store.py`): Persistence round-trips.
3. **Binary sensor tests** (`test_binary_sensor.py`): State mapping,
   attributes, RestoreEntity behavior.
4. **Service tests** (`test_services.py` extended): mark_dirty/mark_clean
   targeting and behavior.
5. **Coordinator integration** (`test_coordinator.py` extended): Mid-stay
   detection, event generation, timer management.
6. **Config flow tests** (`test_config_flow.py` extended): New option field.
7. **Integration tests**: Full lifecycle from check-in to clean.

### Running Specific Test Suites

```bash
# State machine tests only
uv run pytest tests/test_cleanliness.py -v

# Binary sensor tests
uv run pytest tests/test_binary_sensor.py -v

# All tests with coverage
uv run pytest tests/ --cov=custom_components.turnovercal --cov-report=term-missing
```

## Implementation Phases

### Phase 1: Core State Machine + Persistence

- `CleanlinessPhase`, `CleanlinessState`, `CleanlinessStateMachine`
- `CleanlinessStateStore`
- Unit tests for all transitions and persistence

### Phase 2: Binary Sensor Entity

- `CleanlinessBinarySensor` with RestoreEntity
- Device registration under existing device
- Entity attributes (phase, timestamps, reason)

### Phase 3: Service Actions

- `mark_dirty`, `mark_clean` service handlers
- Extended entity resolver (binary_sensor + calendar targeting)
- Service YAML definitions and strings

### Phase 4: Coordinator Integration

- State machine ownership in coordinator
- Lock code → being_cleaned transition (extend handle_lock_event)
- Cleaning duration timer (start/cancel/reconstitute)
- Fallback cleaning event generation

### Phase 5: RC Event Integration + Mid-Stay Detection

- RC check-in/check-out event listeners
- Startup entity state reconciliation
- Mid-stay cancellation detection in polling cycle

### Phase 6: Config Flow + Final Integration

- `cleaning_duration_hours` option
- Platform setup in **init**.py
- End-to-end lifecycle tests
