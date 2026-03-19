<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Tasks: TurnoverCal iCal Export

**Input**: Design documents from
`/specs/001-ical-turnover-export/`
**Prerequisites**: plan.md, spec.md, research.md,
data-model.md, contracts/

**Tests**: Unit tests are REQUIRED per the project constitution
(TDD is NON-NEGOTIABLE). Every user story phase MUST include
unit test tasks written before implementation. Integration tests
are included where prerequisites exist within the same phase.

**Organization**: Tasks are grouped by user story to enable
independent implementation and testing of each story.

## Format: `ID [P?] [Story] Description`

- `ID`: Task identifier (T001, T002, etc.)
- **[P]**: Can run in parallel (different files, no deps)
- **[Story]**: Which user story (US1, US2, US3, US4);
  omitted for shared infrastructure tasks in Phases 1–2
- Exact file paths included in descriptions

## Path Conventions

- **Source**: `custom_components/turnovercal/`
- **Tests**: `tests/`
- **Contracts**: `specs/001-ical-turnover-export/contracts/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffold — manifest, constants, packaging

<!-- markdownlint-disable MD013 -->

- [X] T001 Create `custom_components/turnovercal/` directory and empty `__init__.py`
- [X] T002 Create `custom_components/turnovercal/manifest.json` with domain `turnovercal`, dependencies `["rental_control"]`, `iot_class: "local_polling"`, `icalendar` requirement, and HA version pin `2026.2.0`
- [X] T003 [P] Create `custom_components/turnovercal/const.py` with domain name, config keys (`CONF_CALENDAR_ENTITY`, `CONF_LOCK_ENTITY`, `CONF_CLEANING_CODE_SLOT`, `CONF_RETENTION_WEEKS`, `CONF_SUMMARY_PREFIX`, `CONF_PROPERTY_NAME`, `CONF_TRAILING_DURATION_HOURS`, `CONF_EARLY_UNLOCK_GRACE_HOURS`, `CONF_UPDATE_INTERVAL`, `CONF_LOCK_MONITORING`), defaults, and event constants (`EVENT_KEYMASTER`)
- [X] T004 [P] Create `custom_components/turnovercal/strings.json` and `custom_components/turnovercal/translations/en.json` with config flow UI strings for setup and options steps
- [X] T005 [P] Create `tests/conftest.py` with shared pytest fixtures: mock Rental Control calendar entity, mock Keymaster event payloads, helper to build `CalendarEvent` objects
- [X] T006 [P] Create `pyproject.toml` (or update if it already exists) to add `pytest-homeassistant-custom-component`, `pytest-aiohttp`, and `pytest-cov` as dev dependencies; run `uv sync`

<!-- markdownlint-enable MD013 -->

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data types and pure logic that ALL user stories
depend on. No HA runtime coupling here — just models and
turnover math.

<!-- markdownlint-disable MD013 -->

**⚠️ CRITICAL**: No user story work can begin until this phase
is complete.

### Tests for Foundational Phase (RED first)

- [X] T007 Write unit tests for `TurnoverEvent` dataclass in `tests/test_models.py` — construction, validation (dtstart < dtend), zero-duration promotion (dtend = dtstart + 1 min), UID stability, serialization round-trip (to_dict / from_dict), trailing event flag, `summary` PII exclusion
- [X] T008 Write unit tests for `CachedEventStore` dataclass in `tests/test_models.py` — construction, add/remove events, lookup by UID, version field, `feed_token` field, `last_cleanup` field
- [X] T009 Write unit tests for turnover calculation in `tests/test_turnover.py` — consecutive pair produces correct dtstart/dtend, multi-day gap, zero-gap (1-min promotion), negative overlap (no event + warning), single trailing event (configurable duration), trailing event replaced when new guest added, multiple consecutive guests produce N-1 events, empty calendar produces no events
- [X] T010 Write unit tests for UID generation in `tests/test_turnover.py` — deterministic SHA-256 hex (first 16 chars) with `@turnovercal.homeassistant` suffix, same inputs produce same UID, different inputs produce different UIDs, trailing UID uses sentinel, one-way (source IDs not recoverable)
- [X] T011 [P] Write unit tests for token generation and validation in `tests/test_token.py` — `generate_token()` returns 43-char URL-safe base64, `validate_token()` uses constant-time comparison, invalid tokens rejected, empty/None tokens rejected

### Implementation for Foundational Phase (GREEN)

- [X] T012 [P] Implement `TurnoverEvent` and `CachedEventStore` classes in `custom_components/turnovercal/models.py` with `to_dict()` / `from_dict()` serialization, naive-local-time storage convention for dtstart/dtend, UTC with offset for created_at/lock_unlock_time, all fields per data-model.md
- [X] T013 [P] Implement `generate_uid()`, `generate_trailing_uid()`, and `compute_turnover_events()` in `custom_components/turnovercal/turnover.py` — pure functions taking a sorted list of `CalendarEvent` objects and config (trailing duration, timezone), returning list of `TurnoverEvent`; handles zero-gap, negative overlap, trailing events per FR-002/FR-010/FR-011/FR-012/FR-016
- [X] T014 [P] Implement `generate_token()` and `validate_token()` in `custom_components/turnovercal/token.py` using `secrets.token_urlsafe(32)` and `hmac.compare_digest()`

<!-- markdownlint-enable MD013 -->

**Checkpoint**: All foundational tests pass. Pure logic is
verified independently of HA runtime.

---

## Phase 3: User Story 1 — Basic Turnover Calendar (P1) 🎯 MVP

**Goal**: Property manager configures TurnoverCal, cleaning
staff subscribe to the iCal feed URL and see turnover windows.

**Independent Test**: Configure a Rental Control calendar with
2+ consecutive guests, subscribe to the generated iCal URL, and
verify turnover events appear between guest events.

<!-- markdownlint-disable MD013 -->

### Tests for User Story 1 (RED first)

- [x] T015 [P] [US1] Write unit tests for `EventCache` (Store wrapper) in `tests/test_event_cache.py` — async load/save via `Store`, add event, remove event, get all events, initial empty state returns empty dict, `feed_token` persisted, version migration stub
- [x] T016 [P] [US1] Write unit tests for config flow setup step in `tests/test_config_flow.py` — user enters calendar entity ID, lock monitoring preference (lock_monitoring=True/False), token generated on setup, flow creates config entry, duplicate calendar rejected, invalid entity rejected
- [x] T017 [P] [US1] Write unit tests for `TurnoverCoordinator` in `tests/test_coordinator.py` — calls `async_get_events()` on Rental Control calendar, passes events to `compute_turnover_events()`, stores results in cache, periodic update via `DataUpdateCoordinator`, handles Rental Control unavailable (serves cached data, logs error per FR-013), handles modified guest events (recalculates per FR-010)
- [x] T018 [P] [US1] Write unit tests for iCal generation in `tests/test_calendar.py` — VCALENDAR properties (PRODID, VERSION, CALSCALE, METHOD, X-WR-CALNAME, X-WR-TIMEZONE), VEVENT properties (UID, DTSTAMP, DTSTART with TZID, DTEND with TZID, SUMMARY, DESCRIPTION, STATUS), VTIMEZONE auto-generated, empty calendar valid, multiple events, summary uses configured prefix per FR-014
- [x] T019 [P] [US1] Write unit tests for HTTP view in `tests/test_http_view.py` — valid token returns 200 with `text/calendar; charset=utf-8` content-type, invalid token returns 401, missing token returns 401, removed config entry returns 401, response body is valid RFC 5545, empty calendar returns valid VCALENDAR with no VEVENT
- [x] T020 [US1] Write contract test for iCal feed endpoint in `tests/test_http_view.py` — verify response matches `specs/001-ical-turnover-export/contracts/ical-feed.md` (Content-Type header, VCALENDAR structure, VEVENT field set, 401 for invalid tokens)

### Implementation for User Story 1

- [x] T021 [US1] Implement `EventCache` class in `custom_components/turnovercal/event_cache.py` wrapping `homeassistant.helpers.storage.Store` — async `load()`, `save()`, `add_event()`, `remove_event()`, `get_events()`, storage path `.storage/turnovercal_{entry_id}`, JSON schema per data-model.md serialization format, `async_delay_save(delay=5)` for batching
- [x] T022 [US1] Implement config flow setup step in `custom_components/turnovercal/config_flow.py` — `ConfigFlow` with `async_step_user()`: text field for calendar entity ID, lock monitoring preference toggle, derives default `property_name` by stripping "Rental Control " prefix from entity friendly name and stores it in ConfigEntryOptions, token generation via `generate_token()`, creates config entry; `OptionsFlow` stub for future options
- [x] T023 [US1] Implement `TurnoverCoordinator` in `custom_components/turnovercal/coordinator.py` — subclass `DataUpdateCoordinator`, `_async_update_data()` calls calendar entity `async_get_events()` with default query window (past 7 days to future 365 days), passes sorted events to `compute_turnover_events()`, diffs result against cache (add new, update changed, mark completed), writes to `EventCache`
- [x] T024 [US1] Implement iCal generation in `custom_components/turnovercal/calendar.py` — `generate_ical()` pure function using `icalendar.Calendar` and `icalendar.Event`, sets all VCALENDAR and VEVENT properties per contract, calls `cal.add_missing_timezones()` for VTIMEZONE, returns bytes
- [x] T025 [US1] Implement HTTP view in `custom_components/turnovercal/http_view.py` — `TurnoverCalView(HomeAssistantView)` with `url="/api/turnovercal/{token}/calendar.ics"`, `requires_auth=False`, `get()` validates token via `validate_token()` with `hmac.compare_digest()`, returns `web.Response` with `text/calendar; charset=utf-8` content-type or 401
- [x] T026 [US1] Implement integration setup in `custom_components/turnovercal/__init__.py` — `async_setup_entry()`: create `EventCache`, create `TurnoverCoordinator`, look up calendar entity via `EntityComponent.get_entity()`, register `TurnoverCalView`; `async_unload_entry()`: remove data from `hass.data`; store coordinator and cache in `hass.data[DOMAIN][entry.entry_id]` <!-- codespell:ignore hass -->

<!-- markdownlint-enable MD013 -->

**Checkpoint**: User Story 1 fully functional. Config flow
creates an entry, coordinator polls Rental Control, iCal feed
serves turnover events at the secret URL. All acceptance
scenarios 1-1 through 1-4 pass.

---

## Phase 4: User Story 2 — Historical Event Caching (P2)

**Goal**: Past turnover events persist in the feed after STR
platform removes source guest events, for the configured
retention period.

**Independent Test**: Generate turnover events, remove source
guest events from Rental Control, verify turnover events
persist for the retention period and are cleaned up after
expiry.

<!-- markdownlint-disable MD013 -->

### Tests for User Story 2 (RED first)

- [X] T027 [P] [US2] Write unit tests for cache retention and cleanup in `tests/test_event_cache.py` — events within retention period kept, events past retention period removed, events with future turnover windows never removed regardless of age, cleanup updates `last_cleanup` timestamp, hourly cleanup interval fires correctly
- [X] T028 [P] [US2] Write unit tests for options flow in `tests/test_config_flow.py` — user can change retention period (1–52 weeks), default is 6, validates range, changes persist to config entry options, summary prefix changeable, trailing duration hours changeable (1–24, default 4), update interval changeable (1–60 min), property name changeable, token regeneration (old token rejected after regen, new token accepted, CachedEventStore mirror updated)
- [X] T029 [P] [US2] Write unit tests for coordinator cache preservation in `tests/test_coordinator.py` — past/future split: when Rental Control removes a past guest event, cached turnover is preserved (only expired by cleanup); when a future guest event is cancelled, stale future turnovers are replaced by fresh computation; coordinator `_async_update_data()` merges using past/future reconciliation strategy

### Implementation for User Story 2

- [X] T030 [US2] Add `async_cleanup_expired()` method to `EventCache` in `custom_components/turnovercal/event_cache.py` — remove events where `created_at` is older than retention period AND turnover window is in the past, update `last_cleanup`, call via `async_track_time_interval(timedelta(hours=1))`
- [X] T031 [US2] Implement options flow in `custom_components/turnovercal/config_flow.py` — `OptionsFlow` with `async_step_init()`: retention weeks (int, 1–52, default 6), summary prefix (str, default "Turnover"), trailing duration hours (int, 1–24, default 4), update interval (int, 1–60, default 5), property name (str, default derived by stripping "Rental Control " prefix from RC entity friendly name, stored in ConfigEntryOptions), boolean selector to trigger token regeneration (if True, routes to `async_step_confirm_regen()` confirmation step that invalidates old token, updates ConfigEntryData and mirrors to CachedEventStore); on save, reload coordinator with new interval
- [X] T032 [US2] Update `TurnoverCoordinator` in `custom_components/turnovercal/coordinator.py` to preserve cached events during update — diff algorithm with past/future split: past turnovers (dtend in the past) preserved unconditionally, future turnovers always replaced by fresh computation from current source events, expiry cleanup handles final removal of aged past events; register hourly cleanup timer in `__init__.py`'s `async_setup_entry()`

<!-- markdownlint-enable MD013 -->

**Checkpoint**: User Stories 1 AND 2 both work. Turnover events
persist after source removal. Retention and cleanup verified.
Acceptance scenarios 2-1 through 2-4 pass.

---

## Phase 5: User Story 3 — Keymaster Lock Early Completion (P3)

**Goal**: When cleaning staff unlock the door with their
designated code during a turnover window (or within the
early-unlock grace period), the turnover event times are
adjusted to reflect actual cleaning activity.

**Independent Test**: Configure Keymaster lock, create a
multi-day turnover window, fire the designated unlock event,
and verify DTEND (or DTSTART for early unlock) is adjusted.

<!-- markdownlint-disable MD013 -->

### Tests for User Story 3 (RED first)

- [X] T033 [P] [US3] Write unit tests for cleaning signal handler in `tests/test_coordinator.py` — `apply_cleaning_signal()`: during active window shortens DTEND to 00:00 next day (different-day check-in), same-day check-in leaves DTEND unchanged, sets `adjusted_by_lock=True`, sets `lock_unlock_time`, sets `adjustment_source="keymaster"`, preserves `original_dtend`/`original_dtstart`, idempotent (second call is no-op on already-adjusted event)
- [X] T034 [US3] Write unit tests for early-unlock grace period in `tests/test_coordinator.py` — unlock within grace period moves DTSTART to unlock time, unlock outside grace period ignored, grace period of 0 disables feature, preserves `original_dtstart`
- [X] T035 [US3] Write unit tests for Keymaster event listener in `tests/test_coordinator.py` — filters by `entity_id` (wrong lock ignored), filters by `state=="unlocked"` (lock events ignored), filters by `code_slot_num` matching configured slot (guest codes ignored, RF ignored, manual ignored), correct unlock triggers `apply_cleaning_signal()`
- [X] T036 [P] [US3] Write unit tests for options flow lock settings in `tests/test_config_flow.py` — lock monitoring toggle (on/off), cleaning code slot changeable, early-unlock grace period changeable (0–12 hours, default 2)

### Implementation for User Story 3

- [X] T037 [US3] Implement `apply_cleaning_signal()` method in `custom_components/turnovercal/coordinator.py` — find active or upcoming-within-grace turnover event, apply DTEND shortening per FR-009 (00:00 next day if different-day check-in; no change if same day), apply DTSTART move per FR-017 (within grace period), set status to `adjusted`, set `adjusted_by_lock`, `lock_unlock_time`, `adjustment_source`, preserve originals, save to cache; "same day" determined by calendar date in HA local timezone
- [X] T038 [US3] Implement Keymaster event listener in `custom_components/turnovercal/coordinator.py` — `hass.bus.async_listen(EVENT_KEYMASTER, _handle_lock_event)`, filter by `entity_id`, `state=="unlocked"`, `code_slot_num==configured_cleaning_code_slot`, call `apply_cleaning_signal(now=dt_util.utcnow())` on match; register listener in `async_setup_entry()`, unregister on unload <!-- codespell:ignore hass -->
- [X] T039 [US3] Update config flow setup step in `custom_components/turnovercal/config_flow.py` to add Keymaster fields — if `has_keymaster`, show lock entity selector and cleaning code slot number input; update options flow to include lock monitoring toggle, code slot, and early-unlock grace period (0–12 hours, default 2)
- [X] T040 [US3] Update `custom_components/turnovercal/__init__.py` — conditionally register Keymaster listener when `lock_monitoring` is enabled and `lock_entity_id` is set; pass grace period config to coordinator

<!-- markdownlint-enable MD013 -->

**Checkpoint**: Keymaster unlock adjusts turnover events. Both
DTEND shortening and early-unlock DTSTART moves work. All
acceptance scenarios 3-1 through 3-6 pass.

---

## Phase 6: User Story 4 — Manual Cleaning Signal (P3)

**Goal**: Service call `turnovercal.mark_cleaning_started`
provides the same adjustment as a Keymaster unlock, for
properties without smart locks or when lock events fail.

**Independent Test**: Create a turnover window, call the
service, and verify event times adjust identically to a
Keymaster unlock scenario.

<!-- markdownlint-disable MD013 -->

### Tests for User Story 4 (RED first)

- [X] T041 [P] [US4] Write unit tests for service handler in `tests/test_services.py` — entity target resolves to correct coordinator, `config_entry_id` target resolves to correct coordinator, both provided raises `ServiceValidationError`, neither provided raises `ServiceValidationError`, invalid entity raises `ServiceValidationError`, calls `apply_cleaning_signal()` with `adjustment_source="service_call"`, optional `timestamp` override interpreted in HA timezone, default timestamp is current time
- [X] T042 [US4] Write contract tests for service in `tests/test_services.py` — verify service schema matches `specs/001-ical-turnover-export/contracts/service-mark-cleaning.md` (target entity integration/domain, fields config_entry_id and timestamp, selector types), idempotency (second call is no-op)

### Implementation for User Story 4

- [X] T043 [US4] Create `custom_components/turnovercal/services.yaml` with `mark_cleaning_started` service definition matching contract — name, description, target (entity integration: turnovercal, domain: calendar), fields (config_entry_id with config_entry selector, timestamp with datetime selector)
- [X] T044 [US4] Implement service handler in `custom_components/turnovercal/services.py` — `async_setup_services(hass)`: register `mark_cleaning_started` handler, resolve target (entity OR config_entry_id, not both, not neither), get coordinator from `hass.data`, call `apply_cleaning_signal()` with `adjustment_source="service_call"` and optional timestamp override <!-- codespell:ignore hass -->
- [X] T045 [US4] Register service in `custom_components/turnovercal/__init__.py` — call `async_setup_services(hass)` from `async_setup_entry()`, unregister on last entry unload <!-- codespell:ignore hass -->

<!-- markdownlint-enable MD013 -->

**Checkpoint**: All 4 user stories work independently. Service
call adjusts turnover events identically to Keymaster unlock.
Acceptance scenarios 4-1 through 4-4 pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quality, performance, and documentation

<!-- markdownlint-disable MD013 -->

- [X] T046 [P] Run `uv run ruff check custom_components/ tests/` and fix all linting issues
- [X] T047 [P] Run `uv run mypy custom_components/turnovercal/` and fix all type errors (full type annotations required)
- [X] T048 [P] Run `uv run interrogate -vv --fail-under=100 custom_components/turnovercal/` and add missing docstrings
- [X] T049 [P] Run full test suite with coverage: `uv run pytest tests/ --cov=custom_components/turnovercal --cov-report=term-missing` and verify all tests pass
- [X] T050 Validate iCal output against RFC 5545 by subscribing to feed in Google Calendar, Apple Calendar, and Outlook per SC-003 — **partial**: round-trip parse tests added; client subscription requires running HA
- [X] T051 Performance check: verify iCal feed responds within 2 seconds with 52 weeks of cached events per SC-008 — **partial**: iCal generation benchmarks pass; end-to-end HTTP latency requires running HA
- [X] T052 Security review: verify token is redacted from logs/diagnostics, `hmac.compare_digest()` used for all token comparisons, no PII in summaries per FR-014
- [X] T053 Run `uv run pre-commit run --all-files` to validate all hooks pass
- [X] T054 Validate quickstart.md against actual repository state — confirm all commands work

<!-- markdownlint-enable MD013 -->

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all
  user stories
- **US1 (Phase 3)**: Depends on Foundational — MVP delivery
- **US2 (Phase 4)**: Depends on US1 (cache builds on
  coordinator and event cache from US1)
- **US3 (Phase 5)**: Depends on US1 coordinator (T023) in
  practice — shares coordinator.py and requires EventCache
- **US4 (Phase 6)**: Depends on US3 (shares
  `apply_cleaning_signal()` method)
- **Polish (Phase 7)**: Depends on all desired stories complete

### User Story Dependencies

- **US1 (P1)**: After Foundational — no other story deps
- **US2 (P2)**: After US1 — extends EventCache and coordinator
- **US3 (P3)**: After US1 — adds lock listener to
  coordinator; depends on TurnoverCoordinator from T023
- **US4 (P3)**: After US3 — reuses `apply_cleaning_signal()`

### Within Each User Story

1. Tests MUST be written and FAIL before implementation
2. Models / pure logic before HA-coupled code
3. Core implementation before integration wiring
4. Story complete before moving to next priority

### Parallel Opportunities

- All Phase 1 tasks T003–T006 can run in parallel
- All Phase 2 test tasks T007–T011 can run in parallel
- All Phase 2 implementation tasks T012–T014 can run in
  parallel (different files)
- Within each US phase, all test tasks marked [P] can run
  in parallel
- US3 and US1/US2 could overlap if coordinator interface is
  stable

---

## Parallel Example: Foundational Phase

```text
# Launch all foundational tests in parallel:
T007: test_models.py (TurnoverEvent)
T008: test_models.py (CachedEventStore)
T009: test_turnover.py (calculation)
T010: test_turnover.py (UID generation)
T011: test_token.py (token gen/validate)

# Then launch all implementations in parallel:
T012: models.py (dataclasses)
T013: turnover.py (calculation + UID)
T014: token.py (generation + validation)
```

## Parallel Example: User Story 1

```text
# Launch all US1 tests in parallel:
T015–T020: all different test files

# Then launch implementations (some sequential):
T021 + T022 + T024 + T025 in parallel (different files)
T023 after T021 (coordinator needs EventCache)
T026 after T023 + T025 (init wires coordinator + view)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: iCal feed serves turnover events
5. Deploy/demo — cleaning staff can subscribe immediately

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 → Test → Deploy (MVP! Cleaning staff see turnovers)
3. US2 → Test → Deploy (History survives STR removal)
4. US3 → Test → Deploy (Lock-adjusted turnovers)
5. US4 → Test → Deploy (Manual fallback)
6. Each story adds value without breaking previous stories

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Each user story is independently testable at its checkpoint
- TDD is mandatory: write failing tests, then implement
- Commit after each task or logical group
- Stop at any checkpoint to validate independently
- Total tasks: 54
  - Phase 1 (Setup): 6
  - Phase 2 (Foundational): 8
  - Phase 3 (US1): 12
  - Phase 4 (US2): 6
  - Phase 5 (US3): 8
  - Phase 6 (US4): 5
  - Phase 7 (Polish): 9
- Suggested MVP scope: Phases 1–3 (US1) = 26 tasks
