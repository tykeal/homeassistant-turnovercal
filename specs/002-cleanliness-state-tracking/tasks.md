<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Tasks: Property Cleanliness State Tracking

**Input**: Design documents from `/specs/002-cleanliness-state-tracking/`
**Prerequisites**: spec.md (user stories US1–US6, FR-001–FR-034, edge cases)
**Existing Codebase**: `custom_components/turnovercal/` (coordinator, models,
event_cache, services, config_flow, calendar, sensor, `__init__`)

**Tests**: Unit tests are REQUIRED per the project constitution (TDD is
NON-NEGOTIABLE). Every user story phase MUST include unit test tasks written
before implementation. Integration tests are included where the user story
requires cross-component verification.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `ID [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `custom_components/turnovercal/`
- **Tests**: `tests/`
- **Specs**: `specs/002-cleanliness-state-tracking/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: New modules, constants, and data models needed across all user
stories. No behavioral logic yet — just the scaffolding.

- [ ] T001 Add cleanliness constants to `custom_components/turnovercal/const.py`
      — add `CONF_CLEANING_DURATION_HOURS`, `DEFAULT_CLEANING_DURATION_HOURS`
      (3), `MIN_CLEANING_DURATION_HOURS` (0.05), phase enum values
      (`PHASE_CLEAN`, `PHASE_OCCUPIED`, `PHASE_AWAITING_CLEANING`,
      `PHASE_BEING_CLEANED`), transition reason constants
      (`REASON_GUEST_CHECKIN`, `REASON_GUEST_CHECKOUT`,
      `REASON_MID_STAY_CANCELLATION`, `REASON_LOCK_CODE_ENTRY`,
      `REASON_CLEANING_DURATION_ELAPSED`, `REASON_SERVICE_CALL_MARK_CLEAN`,
      `REASON_SERVICE_CALL_MARK_DIRTY`, `REASON_STARTUP_RECONCILIATION`), and
      `CLEANLINESS_STORE_VERSION` (1)
- [ ] T002 Create `CleanlinessState` dataclass in
      `custom_components/turnovercal/cleanliness.py` — fields: `is_dirty`
      (bool), `phase` (str, one of the four phase constants),
      `last_transition_at` (datetime, UTC), `last_transition_reason` (str),
      `timer_target` (datetime | None, UTC, for `being_cleaned` timer
      reconstitution), `dirty_since` (datetime | None, UTC, start of dirty
      period), `associated_checkout_time` (datetime | None, UTC, for
      fallback), `config_entry_id` (str). Include `to_dict()` and
      `from_dict()` serialization matching the existing `TurnoverEvent`
      pattern (naive local for display times, UTC with offset for
      timestamps)
- [ ] T003 Create `CleanlinessStateStore` in
      `custom_components/turnovercal/cleanliness_store.py` — dedicated
      `homeassistant.helpers.storage.Store` (storage key:
      `turnovercal_{entry_id}_cleanliness`, version from
      `CLEANLINESS_STORE_VERSION`). Methods:
      `async_load() -> CleanlinessState | None`,
      `async_save(state: CleanlinessState)`,
      `schedule_save(state: CleanlinessState)` (batched
      5-second delay for performance), `async_delete()`.
      Follow the
      `EventCache` persistence pattern but simpler (single object,
      not a dict of events). Returns `None` when no persisted
      state exists (state machine handles default creation)
- [ ] T004 Create `CleanlinessStateMachine` class in
      `custom_components/turnovercal/cleanliness.py` — skeleton with `__init__`
      accepting `hass`, `entry_id`, `store` (CleanlinessStateStore),
      `cleaning_duration_hours` (float). Properties:
      `state -> CleanlinessState`, `is_dirty -> bool`, `phase -> str`. No
      transition methods yet (added per user story). Include
      `async_initialize()` that loads from store (or creates default clean
      state) and `async_shutdown()` that cancels any active timer

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can
be implemented. Wires the new cleanliness modules into the integration
lifecycle.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Unit tests for `CleanlinessState` dataclass in
      `tests/test_cleanliness.py`
      — test `to_dict()`/`from_dict()` round-trip for all fields, default clean
      state factory, phase value validation
- [X] T006 [P] Unit tests for `CleanlinessStateStore` in
      `tests/test_cleanliness_store.py` — test `async_load()` returns None when
      no file, `async_save()`/`async_load()` round-trip,
      `async_delete()` removes persisted data
- [X] T007 [P] Unit tests for `CleanlinessStateMachine` skeleton in
      `tests/test_cleanliness.py` — test `async_initialize()` loads persisted
      state, creates default clean state when none exists, `async_shutdown()` is
      safe to call when no timer active, properties `is_dirty`/`phase` reflect
      current state
- [X] T008 Add `Platform.BINARY_SENSOR` to `PLATFORMS` list in
      `custom_components/turnovercal/__init__.py` — update the `PLATFORMS`
      constant to include `Platform.BINARY_SENSOR` alongside existing
      `Platform.CALENDAR` and `Platform.SENSOR`
- [X] T009 Wire `CleanlinessStateMachine` into `async_setup_entry()` in
      `custom_components/turnovercal/__init__.py` — after coordinator creation,
      instantiate `CleanlinessStateStore`, create `CleanlinessStateMachine`,
      call `async_initialize()`, store in
      `hass.data[DOMAIN][entry.entry_id]["cleanliness"]`. On unload in
      `async_unload_entry()`, call `async_shutdown()` on the state machine
- [X] T010 Add `cleaning_duration_hours` to options flow in
      `custom_components/turnovercal/config_flow.py` — add a new numeric field
      to `async_step_init` in `TurnoverCalOptionsFlow` with range
      `MIN_CLEANING_DURATION_HOURS` (0.05) to 24, default
      `DEFAULT_CLEANING_DURATION_HOURS` (3). Add translation strings in
      `custom_components/turnovercal/strings.json` under
      `options.step.init.data` and
      `options.step.init.data_description`. Keep
      `translations/en.json` in sync
- [X] T011 [P] Unit tests for `cleaning_duration_hours` options flow in
      `tests/test_config_flow.py` — test default value (3), minimum boundary
      (0.05), maximum boundary (24), invalid values rejected, value persisted in
      entry options

**Checkpoint**: Foundation ready — cleanliness store, state machine skeleton,
and options wiring all in place. User story implementation can now begin.

---

## Phase 3: US3 — Binary Sensor on Dashboard (Priority: P1) 🎯 MVP

**Goal**: Expose a `binary_sensor` entity under each property's device showing
dirty/clean state with phase attribute. This is implemented first because all
other stories need the sensor to verify their behavior.

**Independent Test**: Load the integration and verify the binary sensor entity
appears under the existing device with correct on/off states matching the
property's cleanliness state, and the `phase` attribute reports `clean` for a
newly configured property.

### Tests for User Story 3 (unit tests REQUIRED)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T012 [P] [US3] Unit tests for `TurnoverCalCleanlinessSensor` in
      `tests/test_cleanliness_sensor.py` — test entity creation with correct
      unique_id (`{entry_id}_cleanliness`), device class
      `problem`, translation key `dirty`, reports `on`
      when dirty and `off` when clean, exposes extra state
      attributes: `phase`, `last_transition_at`,
      `last_transition_reason`, `dirty_since`,
      `timer_target`. Test the sensor
      updates when state machine state changes. Test that the entity belongs to
      the same device as existing calendar/sensor entities (device identifiers
      `(DOMAIN, entry_id)`)

### Implementation for User Story 3

- [ ] T013 [US3] Create `TurnoverCalCleanlinessSensor` binary sensor entity in
      `custom_components/turnovercal/binary_sensor.py` — extend
      `RestoreEntity, BinarySensorEntity`, use
      `device_class=BinarySensorDeviceClass.PROBLEM`,
      `translation_key="dirty"`. Unique ID:
      `{entry_id}_cleanliness`. Device info matches existing
      entities with identifiers `(DOMAIN, entry_id)`. The
      `is_on` property reads from the
      `CleanlinessStateMachine` (retrieved from
      `hass.data[DOMAIN][entry.entry_id]["cleanliness"]`).
      Implement restore behavior using
      `async_get_last_state()` (typically from
      `async_added_to_hass()`) to load the last known
      state and attributes from `RestoreEntity` on startup
      as a fast-path before the store loads. Only use
      `async_get_last_extra_data()` and an
      `ExtraStoredData` subclass if additional non-state
      data must be persisted. Extra state attributes:
      `phase` (from state machine),
      `last_transition_at` (ISO string of last transition),
      `last_transition_reason` (transition reason string),
      `dirty_since` (ISO string or null),
      `timer_target` (ISO string or null).
      Implement `async_setup_entry()` platform function
- [ ] T014 [US3] Add binary sensor translation keys to
      `custom_components/turnovercal/strings.json` — add
      `entity.binary_sensor.dirty.name` = "Cleanliness"
      under the entity section. Add phase attribute
      translation if needed.
      Keep `translations/en.json` in sync
- [ ] T015 [US3] Register callback in binary sensor to update on state machine
      changes in `custom_components/turnovercal/binary_sensor.py` — the state
      machine needs a listener/callback mechanism so the binary sensor calls
      `self.async_write_ha_state()` when the cleanliness state changes. Add
      `register_callback(callback)` and `unregister_callback(callback)` methods
      to `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py`, invoke callbacks on every
      state transition. The binary sensor registers on `async_added_to_hass` and
      unregisters on `async_will_remove_from_hass`

**Checkpoint**: Binary sensor entity exists and reports clean for new
properties. Dashboard visibility story is complete pending dirty-trigger
stories.

---

## Phase 4: User Story 6 — State Persistence Across Restarts (Priority: P2)

**Goal**: Ensure dirty/clean state survives HA restarts and integration reloads.
This is implemented early because all other stories depend on persistence
working correctly.

**Independent Test**: Set a property to dirty (directly via state machine),
reload the integration, and verify the binary sensor still reads "on" (dirty).

### Tests for User Story 6 (unit tests REQUIRED)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T016 [P] [US6] Unit tests for state persistence in
      `tests/test_cleanliness_store.py` — test: dirty state persists and reloads
      correctly, clean state persists and reloads correctly, `being_cleaned`
      phase with `timer_target` persists and reloads, `timer_target` in the past
      triggers immediate clean on reload, all `CleanlinessState` fields survive
      round-trip through store

### Implementation for User Story 6

- [ ] T017 [US6] Implement persistence-aware `async_initialize()` in
      `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py` — on load, if persisted
      state has `phase=PHASE_BEING_CLEANED` and `timer_target` is set: if target
      time has passed, transition to clean immediately; otherwise, reconstitute
      the timer for remaining duration using `async_track_point_in_time`. Save
      state to store on every transition via a private `_async_persist()` method
      called at the end of each state change
- [ ] T018 [US6] Implement `_async_persist()` in `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py` — calls
      `self._store.async_save(self._state)` after every state transition. Ensure
      all transition methods (to be added in subsequent stories) call this after
      mutating state
- [ ] T019 [US6] Integration test for restart persistence in
      `tests/test_cleanliness.py` — simulate full lifecycle: create state
      machine, set dirty, save, create new state machine instance with same
      store, verify it loads dirty state. Also test `being_cleaned` with future
      timer_target reconstitutes timer, and past timer_target transitions to
      clean immediately

**Checkpoint**: State persistence is verified. Any state set by future stories
will automatically survive restarts.

---

## Phase 5: US1 — Auto Dirty on Guest Check-In (Priority: P1) 🎯 MVP

**Goal**: Automatically transition property to dirty when a guest checks in (RC
check-in event). Validate cleaning event coverage and create fallback if needed.
Transition phase to `awaiting_cleaning` on check-out.

**Independent Test**: Configure a property with a single incoming reservation,
trigger a check-in event, verify the binary sensor shows "on" (dirty) with
`phase=occupied`, then trigger check-out and verify `phase=awaiting_cleaning`.

### Tests for User Story 1 (unit tests REQUIRED)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T020 [P] [US1] Unit tests for check-in transition in
      `tests/test_cleanliness.py` — test `async_handle_checkin(checkout_time)`:
      clean→dirty with `phase=occupied`, `reason=REASON_GUEST_CHECKIN`,
      `last_transition_at` updated, `is_dirty=True`. Test
      idempotency: calling checkin
      when already dirty/occupied is a no-op. Test checkin during
      `being_cleaned` phase cancels timer, stays dirty, phase→occupied
- [ ] T021 [P] [US1] Unit tests for check-out transition in
      `tests/test_cleanliness.py` — test `async_handle_checkout()`:
      dirty/occupied→dirty/awaiting_cleaning, `reason=REASON_GUEST_CHECKOUT`.
      Test: checkout when not in occupied phase is a no-op. Test: checkout when
      clean is a no-op
- [ ] T022 [P] [US1] Unit tests for cleaning event validation in
      `tests/test_cleanliness.py` — test that `async_handle_checkin` invokes a
      callback/method to validate cleaning event coverage for the checkout time.
      Test: when turnover event exists for checkout period, no fallback created.
      Test: when no turnover event exists, fallback created with
      `dtstart=checkout_time`, duration=`trailing_duration_hours`
- [ ] T023 [P] [US1] Unit tests for RC event listeners in
      `tests/test_cleanliness.py` — test that check-in HA events (bus events
      from RC) trigger `async_handle_checkin`. Test that check-out HA events
      trigger `async_handle_checkout`. Test event filtering (only events for the
      configured RC calendar entity)

### Implementation for User Story 1

- [ ] T024 [US1] Implement `async_handle_checkin(checkout_time: datetime)` in
      `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py` — transitions clean→dirty
      with `phase=PHASE_OCCUPIED`. If already dirty with
      `phase=PHASE_BEING_CLEANED`, cancels active timer and sets
      `phase=PHASE_OCCUPIED` (FR-017). If already dirty/occupied, no-op. Stores
      checkout_time for cleaning event validation. Calls `_async_persist()` and
      notifies callbacks
- [ ] T025 [US1] Implement `async_handle_checkout()` in
      `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py` — transitions `phase` from
      `PHASE_OCCUPIED` to `PHASE_AWAITING_CLEANING` with
      `reason=REASON_GUEST_CHECKOUT`. No-op if not in occupied phase. Calls
      `_async_persist()` and notifies callbacks
- [ ] T026 [US1] Implement cleaning event validation in
      `custom_components/turnovercal/cleanliness.py` — add
      `_async_validate_cleaning_coverage(checkout_time: datetime)` method called
      during `async_handle_checkin`. Checks coordinator's cached events for a
      turnover event covering the checkout period. If none found, creates a
      fallback `TurnoverEvent` with `dtstart=checkout_time`,
      `dtend=checkout_time + trailing_duration_hours`, and adds it to the event
      cache. Use a callback/delegate pattern to access the coordinator (injected
      during state machine creation, not a direct import)
- [ ] T027 [US1] Register RC check-in/check-out event listeners in
      `custom_components/turnovercal/__init__.py` — in `async_setup_entry()`,
      subscribe to RC-provided HA bus events for check-in and check-out. Filter
      events matching the configured `calendar_entity_id`. On check-in: call
      `cleanliness.async_handle_checkin(checkout_time)`. On check-out: call
      `cleanliness.async_handle_checkout()`. Store unsubscribe callbacks via
      `entry.async_on_unload()`
- [ ] T028 [US1] Implement startup entity state reconciliation in
      `custom_components/turnovercal/__init__.py` — after coordinator first
      refresh and cleanliness initialization, check the current state of
      RC-provided entities to detect if a guest is currently staying (check-in
      passed, check-out not yet). If so, trigger
      `async_handle_checkin(checkout_time)` to ensure the property is marked
      dirty. This handles missed events during downtime (FR-008)

**Checkpoint**: Guest check-in automatically marks property dirty, binary sensor
shows on/occupied, check-out transitions to awaiting_cleaning, fallback cleaning
events created when needed. State survives restarts.

---

## Phase 6: US2 — Clean via Lock Code or Service (Priority: P1) 🎯 MVP

**Goal**: Lock code entry transitions to `being_cleaned` phase, starts a
configurable duration timer, and auto-transitions to clean when timer fires.
`mark_clean` service provides immediate clean override.

**Independent Test**: Mark a property dirty, use a lock code entry (verify
`being_cleaned` phase and timer start), wait for timer (verify auto-transition
to clean). Alternatively, call `mark_clean` to verify immediate transition.

### Tests for User Story 2 (unit tests REQUIRED)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T029 [P] [US2] Unit tests for lock code → being_cleaned in
      `tests/test_cleanliness.py` — test `async_handle_lock_code()`:
      dirty/awaiting_cleaning→dirty/being_cleaned,
      `reason=REASON_LOCK_CODE_ENTRY`, timer started with
      `cleaning_duration_hours` delay. Test: lock code when phase is not
      `awaiting_cleaning` (e.g., `occupied`) does NOT change phase (FR-012).
      Test: lock code when clean is a no-op
- [ ] T030 [P] [US2] Unit tests for cleaning duration timer in
      `tests/test_cleanliness.py` — test timer fires after
      `cleaning_duration_hours`, transitions to clean (`phase=PHASE_CLEAN`,
      `is_dirty=False`, `reason=REASON_CLEANING_DURATION_ELAPSED`). Test
      `timer_target` is persisted in state. Test timer cancellation on shutdown.
      Test minimum duration (0.05 hours = 3 minutes)
- [ ] T031 [P] [US2] Unit tests for `mark_clean` service transition in
      `tests/test_cleanliness.py` — test `async_mark_clean()`: any dirty
      phase→clean immediately, cancels active timer if present,
      `reason=REASON_SERVICE_CALL_MARK_CLEAN`. Test: mark_clean when already
      clean is a silent no-op. Test: mark_clean during `being_cleaned` cancels
      timer (FR-015)
- [ ] T032 [P] [US2] Unit tests for `mark_clean` service handler
      in `tests/test_services.py` — test service registration
      for `turnovercal.mark_clean`. Test target resolution
      (entity_id or config_entry_id, same pattern as existing
      `mark_cleaning_started`). Test `mark_clean` calls
      `cleanliness.async_mark_clean()`. (Note: `mark_dirty`
      service registration and handler tests are deferred to
      Phase 8 alongside T046/T047)

### Implementation for User Story 2

- [ ] T033 [US2] Implement `async_handle_lock_code()` in
      `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py` — when
      `phase=PHASE_AWAITING_CLEANING`: set `phase=PHASE_BEING_CLEANED`,
      `reason=REASON_LOCK_CODE_ENTRY`, compute
      `timer_target = now + cleaning_duration_hours`,
      start timer via `async_track_point_in_time`
      (from `homeassistant.helpers.event`). Store
      the unsub callback. Persist state (including
      `timer_target`). When
      phase is not `awaiting_cleaning`, no-op on phase change (lock code still
      does its existing event-adjustment behavior via coordinator)
- [ ] T034 [US2] Implement `_async_timer_fired()` callback in
      `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py` — transitions to clean:
      `is_dirty=False`, `phase=PHASE_CLEAN`,
      `reason=REASON_CLEANING_DURATION_ELAPSED`, `timer_target=None`. Persist
      and notify callbacks
- [ ] T035 [US2] Implement `async_mark_clean()` in `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py` — immediately set
      `is_dirty=False`, `phase=PHASE_CLEAN`,
      `reason=REASON_SERVICE_CALL_MARK_CLEAN`, `timer_target=None`. Cancel
      active timer if present (FR-015, FR-019). Silent no-op if already clean.
      Persist and notify callbacks
- [ ] T036 [US2] Wire lock code events to cleanliness state machine in
      `custom_components/turnovercal/coordinator.py` — in `handle_lock_event()`,
      after existing `apply_cleaning_signal()` call, also call
      `cleanliness.async_handle_lock_code()` on the state machine (retrieved
      from `hass.data[DOMAIN][entry.entry_id]["cleanliness"]`).
      This connects the existing Keymaster integration with the
      new cleanliness tracking
- [ ] T037 [US2] Register `mark_clean` service action in
      `custom_components/turnovercal/services.py` — add
      `SERVICE_MARK_CLEAN = "mark_clean"` and
      `SERVICE_MARK_DIRTY = "mark_dirty"` constants. Create
      handler `_handle_mark_clean` that resolves target
      coordinators (reuse `_resolve_coordinators` pattern),
      then calls `cleanliness.async_mark_clean()`. Update
      `async_setup_services()` and `async_unload_services()`
      to register/unregister `mark_clean`. Accept targeting
      by entity (binary_sensor OR calendar) or
      config_entry_id (FR-022) — update
      `_find_coordinator_by_entity` to also check
      binary_sensor domain entities. (Note: `mark_dirty`
      service registration is deferred to T047 in Phase 8,
      after `async_mark_dirty()` is implemented in T046)
- [ ] T038 [US2] Add service YAML definitions for `mark_clean` and `mark_dirty`
      in `custom_components/turnovercal/services.yaml` — define both services
      with `target.entity` supporting both `calendar` and `binary_sensor`
      domains for the turnovercal integration, plus `config_entry_id` field
      (matching existing `mark_cleaning_started` pattern). No `timestamp` field
      needed for these services
- [ ] T039 [US2] Add service exception translation keys to
      `custom_components/turnovercal/strings.json` — add any new exception keys
      needed for mark_clean/mark_dirty service validation
      errors (reuse existing keys where possible). Keep
      `translations/en.json` in sync

**Checkpoint**: Full dirty→clean lifecycle works: check-in marks dirty, lock
code starts cleaning timer, timer auto-transitions to clean OR mark_clean
provides immediate override. Binary sensor reflects all phase changes.

---

## Phase 7: US4 — Mid-Stay Cancellation Dirty (Priority: P2)

**Goal**: Detect when a booking is removed mid-stay (guest was occupying the
property) and automatically mark the property dirty with
`phase=awaiting_cleaning`.

**Independent Test**: Simulate a booking removal while the guest's stay is
active, verify the property transitions to dirty with a cleaning event persisted
even after the source booking is gone.

### Tests for User Story 4 (unit tests REQUIRED)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T040 [P] [US4] Unit tests for mid-stay cancellation detection in
      `tests/test_cleanliness.py` — test `async_handle_midstay_cancellation()`:
      clean→dirty with `phase=PHASE_AWAITING_CLEANING`,
      `reason=REASON_MID_STAY_CANCELLATION`. Test: creates immediate cleaning
      event starting at current time with `trailing_duration_hours` duration.
      Test: already dirty property stays dirty, no duplicate cleaning event.
      Test: pre-arrival cancellation (check-in not yet passed) does NOT trigger
      dirty (FR-011)
- [ ] T041 [P] [US4] Unit tests for reservation comparison in
      `tests/test_coordinator.py` — test polling-cycle comparison logic: track
      set of active reservations, detect when a reservation disappears while its
      stay overlaps now, trigger mid-stay cancellation. Test: reservation
      removed before check-in does not trigger. Test: reservation removed after
      check-out does not trigger. Test: reservation removed during stay triggers
      cancellation

### Implementation for User Story 4

- [ ] T042 [US4] Implement `async_handle_midstay_cancellation()` in
      `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py` — transitions to dirty with
      `phase=PHASE_AWAITING_CLEANING`, `reason=REASON_MID_STAY_CANCELLATION`.
      Creates immediate cleaning event (dtstart=now,
      duration=trailing_duration_hours) via the coordinator callback delegate.
      No-op if already dirty with existing cleaning event (FR-025). Persist and
      notify callbacks
- [ ] T043 [US4] Implement reservation comparison in coordinator polling in
      `custom_components/turnovercal/coordinator.py` — in
      `_async_update_data()`, after fetching RC events, compare active
      reservations (stays overlapping now) against previously known set (stored
      as `_previous_active_stays`). If a reservation disappears while its stay
      period overlaps the current time, call
      `cleanliness.async_handle_midstay_cancellation()`. Store current active
      stays for next comparison cycle. Ensure pre-arrival cancellations
      (check-in > now) are excluded (FR-011)
- [ ] T044 [US4] Preserve mid-stay cancellation cleaning events across polling
      in `custom_components/turnovercal/coordinator.py` — in `_merge_events()`,
      do NOT remove cleaning events that were created from mid-stay
      cancellations even when the source booking disappears from RC (FR-028).
      Add a flag or UID pattern to distinguish mid-stay cancellation events from
      regular turnover events

**Checkpoint**: Mid-stay cancellations are detected via polling comparison,
property becomes dirty, cleaning events persist even after source booking
disappears.

---

## Phase 8: User Story 5 — Force Dirty via Service Action (Priority: P2)

**Goal**: Allow property managers to force any property to dirty state via the
`mark_dirty` service action, creating an immediate cleaning event.

**Independent Test**: Call `mark_dirty` on a clean property, verify binary
sensor changes to on/awaiting_cleaning and a cleaning event appears on the
calendar.

### Tests for User Story 5 (unit tests REQUIRED)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T045 [P] [US5] Unit tests for `async_mark_dirty()` in
      `tests/test_cleanliness.py` — test: clean→dirty with
      `phase=PHASE_AWAITING_CLEANING`, `reason=REASON_SERVICE_CALL_MARK_DIRTY`.
      Test: creates immediate cleaning event (dtstart=now,
      duration=trailing_duration_hours). Test: already dirty property stays
      dirty, no duplicate event if one exists (FR-025). Test: mark_dirty during
      `being_cleaned` cancels timer, sets `phase=PHASE_AWAITING_CLEANING`
      (FR-016). Test: mark_dirty during `occupied` phase stays dirty/occupied
      with no new event if one exists

### Implementation for User Story 5

- [ ] T046 [US5] Implement `async_mark_dirty()` in `CleanlinessStateMachine` in
      `custom_components/turnovercal/cleanliness.py` — if clean: set
      `is_dirty=True`, `phase=PHASE_AWAITING_CLEANING`,
      `reason=REASON_SERVICE_CALL_MARK_DIRTY`, create immediate cleaning event
      via coordinator delegate. If `being_cleaned`: cancel timer, set
      `phase=PHASE_AWAITING_CLEANING`, `reason=REASON_SERVICE_CALL_MARK_DIRTY`,
      validate cleaning coverage (FR-016). If already dirty and cleaning event
      exists, no-op on event creation. Persist and notify callbacks
- [ ] T047 [US5] Register `mark_dirty` service action and wire
      handler in `custom_components/turnovercal/services.py`
      — create handler `_handle_mark_dirty` that resolves the
      state machine from
      `hass.data[DOMAIN][entry.entry_id]["cleanliness"]`
      and calls `cleanliness.async_mark_dirty()`. Register
      the `mark_dirty` service in `async_setup_services()`
      and unregister in `async_unload_services()` (using
      the `SERVICE_MARK_DIRTY` constant defined in T037).
      Also add unit tests for `mark_dirty` service handler
      in `tests/test_services.py` — test registration, target
      resolution, and that it calls `async_mark_dirty()`.
      Handles the immediate cleaning event creation through
      the state machine's coordinator delegate

**Checkpoint**: Property managers can force-dirty any property, and immediate
cleaning events appear on the calendar.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories, final validation

- [ ] T048 [P] Add edge case tests to `tests/test_cleanliness.py` — test:
      back-to-back reservations (existing turnover covers cleaning, no
      fallback); mark_clean during active cleaning (timer cancelled, event
      preserved); two rapid dirty triggers (no duplicate events); reservation
      calendar unavailable (state preserved); first-configured property starts
      clean; mark_clean when already clean (silent no-op); mark_dirty when guest
      is actively staying (remains occupied)
- [ ] T049 [P] Add edge case tests for timer interactions in
      `tests/test_cleanliness.py` — test: guest check-in during `being_cleaned`
      cancels timer, phase→occupied (FR-017); mark_dirty during `being_cleaned`
      cancels timer, phase→awaiting_cleaning (FR-016); restart during
      `being_cleaned` with past timer_target transitions to clean immediately;
      restart during `being_cleaned` with future timer_target reconstitutes
      timer
- [ ] T050 [P] Update `custom_components/turnovercal/manifest.json` if needed —
      verify `iot_class` and `dependencies` are still correct with the new
      binary_sensor platform. No changes expected but validate
- [ ] T051 Validate all translation strings in
      `custom_components/turnovercal/strings.json` and corresponding
      `custom_components/turnovercal/translations/en.json` — ensure all new
      entity, service, and options translations are present and consistent
- [ ] T052 Run full test suite and verify all tests pass — execute
      `pytest tests/` from repo root, fix any regressions in existing tests
      caused by new code (particularly `__init__.py` changes, coordinator
      changes, services changes)
- [ ] T053 Run linting and type checking — execute `ruff check`,
      `ruff format --check`, and `mypy` against the codebase per project
      constitution requirements. Fix any issues. Also verify
      that state transition latency meets SC-003 and SC-004
      bounds (transitions within 5 seconds of trigger) by
      asserting timing in the relevant transition test tasks
      (T020, T029, T030)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) — BLOCKS all user
  stories
- **US3 Binary Sensor (Phase 3)**: Depends on Foundational (Phase 2) — provides
  the primary user-facing output that all other stories verify against
- **US6 Persistence (Phase 4)**: Depends on Foundational (Phase 2) — can run
  parallel with US3 but logically needed before testing other stories
- **US1 Check-In Detection (Phase 5)**: Depends on Phases 3 and 4 (needs sensor
  to verify, needs persistence)
- **US2 Clean Confirmation (Phase 6)**: Depends on Phase 5 (needs dirty state to
  exist for clean transitions)
- **US4 Mid-Stay Cancellation (Phase 7)**: Depends on Phase 5 (needs check-in
  infrastructure, coordinator changes)
- **US5 Force Dirty (Phase 8)**: Depends on Phase 6 (mark_dirty service
  registered alongside mark_clean)
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **US3 (Binary Sensor)**: No story dependencies — foundational entity
- **US6 (Persistence)**: No story dependencies — foundational infrastructure
- **US1 (Check-In Detection)**: Depends on US3 (sensor to display) and US6
  (state persistence)
- **US2 (Clean Confirmation)**: Depends on US1 (needs dirty state from check-in
  to confirm clean)
- **US4 (Mid-Stay Cancellation)**: Depends on US1 (shares check-in
  infrastructure)
- **US5 (Force Dirty)**: Depends on US2 (shares service registration code)

### Within Each User Story

- Unit tests MUST be written and FAIL before implementation
- Models / data structures before state machine methods
- State machine methods before integration wiring
- Core implementation before service/event registration
- Each story complete before moving to next priority

### Parallel Opportunities

- T005, T006, T007 can run in parallel (test different modules)
- T012 can run in parallel with T016 (different test files)
- T020, T021, T022, T023 can all run in parallel (different test cases)
- T029, T030, T031, T032 can all run in parallel (different test cases)
- T040, T041 can run in parallel
- T048, T049, T050, T051 can all run in parallel

---

## Parallel Example: User Story 1

```text
# Launch all tests for US1 together (they test different methods):
Task T020: "Unit tests for check-in transition in tests/test_cleanliness.py"
Task T021: "Unit tests for check-out transition in tests/test_cleanliness.py"
Task T022: "Unit tests for cleaning event validation in tests/test_cleanliness.py"
Task T023: "Unit tests for RC event listeners in tests/test_cleanliness.py"

# Then implement sequentially (dependencies between tasks):
Task T024: "Implement async_handle_checkin() in cleanliness.py"
Task T025: "Implement async_handle_checkout() in cleanliness.py"
Task T026: "Implement cleaning event validation in cleanliness.py"
Task T027: "Register RC event listeners in __init__.py"
Task T028: "Implement startup reconciliation in __init__.py"
```

## Parallel Example: User Story 2

```text
# Launch all tests for US2 together:
Task T029: "Unit tests for lock code → being_cleaned"
Task T030: "Unit tests for cleaning duration timer"
Task T031: "Unit tests for mark_clean service transition"
Task T032: "Unit tests for mark_clean/mark_dirty service handlers"

# Then implement sequentially:
Task T033: "Implement async_handle_lock_code()"
Task T034: "Implement _async_timer_fired()"
Task T035: "Implement async_mark_clean()"
Task T036: "Wire lock code events to state machine"
Task T037: "Register mark_clean/mark_dirty services"
Task T038: "Add service YAML definitions"
Task T039: "Add translation keys"
```

---

## Implementation Strategy

### MVP First (US3 + US6 + US1 + US2)

1. Complete Phase 1: Setup (scaffolding)
2. Complete Phase 2: Foundational (tests + wiring)
3. Complete Phase 3: US3 Binary Sensor (visible output)
4. Complete Phase 4: US6 Persistence (state survives restarts)
5. Complete Phase 5: US1 Check-In Detection (automatic dirty)
6. Complete Phase 6: US2 Clean Confirmation (complete lifecycle)
7. **STOP and VALIDATE**: Full clean→dirty→clean lifecycle works
8. Deploy/demo if ready — this covers all P1 stories

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US3 (Binary Sensor) → Sensor visible on dashboard
3. Add US6 (Persistence) → State survives restarts
4. Add US1 (Check-In Detection) → Auto-dirty on guest arrival (MVP!)
5. Add US2 (Clean Confirmation) → Full lifecycle (MVP complete!)
6. Add US4 (Mid-Stay Cancellation) → Edge case coverage
7. Add US5 (Force Dirty) → Manual override
8. Polish → Edge cases, validation, cleanup

### Key New Files

| File | Purpose |
| ------ | --------- |
| `cleanliness.py` | `CleanlinessStateMachine` — all state transition logic |
| `cleanliness_store.py` | `CleanlinessStateStore` — HA Store persistence |
| `binary_sensor.py` | `TurnoverCalCleanlinessSensor` — binary sensor entity |
| `tests/test_cleanliness.py` | Unit + integration tests for state machine |
| `tests/test_cleanliness_store.py` | Unit tests for cleanliness store |
| `tests/test_cleanliness_sensor.py` | Unit tests for binary sensor entity |

### Modified Files

| File | Changes |
| ------ | --------- |
| `const.py` | New constants (phases, reasons, config key) |
| `__init__.py` | Platform, state machine, events, reconciliation |
| `config_flow.py` | `cleaning_duration_hours` options field |
| `coordinator.py` | Lock event → cleanliness wiring, reservation comparison |
| `services.py` | `mark_clean` + `mark_dirty` service handlers |
| `services.yaml` | Service definitions for new services |
| `strings.json` | Translation keys for new entities, options, services |
| `tests/test_config_flow.py` | Tests for cleaning_duration_hours option |
| `tests/test_services.py` | Tests for new service handlers |
| `tests/test_coordinator.py` | Tests for reservation comparison logic |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (Red-Green-Refactor per constitution)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- The `CleanlinessStateMachine` is the central class — most stories add methods
  to it
- The binary sensor (US3) is implemented first because it is the verification
  mechanism for all other stories
- Persistence (US6) is implemented second because all other stories depend on
  state surviving restarts
- RC check-in/check-out event format is assumed to be HA bus events from the
  Rental Control integration; the exact event type/schema will need validation
  against the RC integration's implementation
