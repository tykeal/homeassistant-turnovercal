<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Implementation Plan: TurnoverCal iCal Export

**Branch**: `001-ical-turnover-export` | **Date**: 2026-03-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-ical-turnover-export/spec.md`

## Summary

TurnoverCal is a Home Assistant custom integration that reads guest
event data from the Rental Control integration's calendar entity,
computes turnover (cleaning) windows between consecutive guests, and
serves them as an RFC 5545 iCal feed over a publicly accessible HTTP
endpoint secured by a secret URL token. Events are cached in persistent
JSON storage to survive source data removal by STR platforms. Optional
Keymaster lock monitoring shortens multi-day turnover windows when
cleaning staff unlock the property.

## Technical Context

**Language/Version**: Python 3.13 (Home Assistant 2026.2+ target)
**Primary Dependencies**: `icalendar` ≥6.1.0 (RFC 5545 generation),
`homeassistant` core (calendar, http, storage, config flow APIs)
**Storage**: `homeassistant.helpers.storage.Store` — persistent JSON in
`.storage/turnovercal_{entry_id}` for cached turnover events
**Testing**: `pytest` with `pytest-homeassistant-custom-component`,
`pytest-aiohttp` for HTTP view tests
**Target Platform**: Home Assistant (Linux, any arch with Python 3.13+)
**Project Type**: Home Assistant custom component (integration)
**Performance Goals**: iCal feed response within 2 seconds for up to
1 year of cached events (SC-008)
**Constraints**: Must not block HA event loop; all I/O offloaded to
executor or async; memory footprint proportional to cached event count
**Scale/Scope**: Single property per instance; typical load is 1–50
turnover events cached at a time; feed polled every 15–60 minutes by
calendar clients

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1
design.*

<!-- markdownlint-disable MD013 -->

| Principle | Status | Notes |
| --- | --- | --- |
| I. Code Quality | ✅ PASS | ruff, mypy, interrogate enforced via pre-commit; C901 ≤10 to be configured in ruff |
| II. Test-Driven Development | ✅ PASS | Red-Green-Refactor mandated; pytest infrastructure planned |
| III. UX Consistency | ✅ PASS | RFC 5545 compliance explicit in FR-004; sensible defaults (6-week retention, auto-generated URL) |
| IV. Performance | ✅ PASS | 2-second response target (SC-008); async-only I/O; no event loop blocking |
| V. Atomic Commits | ✅ PASS | Pre-commit hooks active; DCO sign-off required; SPDX headers in REUSE.toml |
| VI. Phased Development | ✅ PASS | Four user stories map to P1→P2→P3 phases with independent test gates |
| Language & Runtime | ✅ PASS | Python 3.13+, full type annotations |
| Dependency Management | ✅ PASS | uv with uv.lock |
| License Compliance | ✅ PASS | REUSE spec; Apache-2.0 for source |
| Security | ✅ PASS | Token from CSPRNG; secrets never committed; token redacted from logs |
| HA Compatibility | ✅ PASS | Standard custom component conventions; manifest.json with HA version pin |
| Standards Compliance | ✅ PASS | RFC 5545 with VTIMEZONE, proper VEVENT properties |

<!-- markdownlint-enable MD013 -->

**Gate result**: ALL PASS — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/001-ical-turnover-export/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── ical-feed.md     # iCal HTTP endpoint contract
│   └── service-mark-cleaning.md  # Manual cleaning service
└── tasks.md             # Phase 2 output (NOT created by plan)
```

### Source Code (repository root)

```text
custom_components/turnovercal/
├── __init__.py          # Integration setup, coordinator, listeners
├── manifest.json        # HA integration manifest
├── config_flow.py       # Setup and options flows
├── const.py             # Domain constants, config keys
├── strings.json         # UI strings for config flow
├── translations/
│   └── en.json          # English translations
├── calendar.py          # TurnoverCalendar entity (iCal generation)
├── coordinator.py       # Data coordinator (event processing)
├── event_cache.py       # Persistent event cache (Store wrapper)
├── turnover.py          # Turnover event calculation logic
├── http_view.py         # HomeAssistantView for iCal feed endpoint
├── services.py          # Service call handlers (mark_cleaning_started)
├── services.yaml        # Service definitions
├── token.py             # Secret URL token generation/validation
└── models.py            # Data classes for turnover events

tests/
├── conftest.py          # Shared fixtures
├── test_turnover.py     # Turnover calculation unit tests
├── test_event_cache.py  # Cache persistence and expiry tests
├── test_config_flow.py  # Config and options flow tests
├── test_http_view.py    # iCal feed endpoint tests
├── test_calendar.py     # Calendar entity tests
├── test_coordinator.py  # Coordinator integration tests
├── test_token.py        # Token generation/validation tests
└── test_models.py       # Data model tests
```

**Structure Decision**: Standard Home Assistant custom component layout
under `custom_components/turnovercal/`. Tests at repository root under
`tests/`. This follows HA custom component conventions and matches the
existing Rental Control integration structure.

## Complexity Tracking

> No constitution violations detected. Table intentionally left empty.
