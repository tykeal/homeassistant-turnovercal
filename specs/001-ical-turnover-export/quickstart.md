<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Quickstart: TurnoverCal Development

**Feature**: 001-ical-turnover-export
**Date**: 2026-03-16

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Home Assistant 2026.2+ (for development/testing)
- Git with pre-commit hooks installed

## Repository Setup

```bash
# Clone and enter the repository
cd turnovercal

# Install dependencies
uv sync

# Install pre-commit hooks
uv run pre-commit install

# Verify pre-commit hooks work
uv run pre-commit run --all-files
```

## Project Structure

```text
custom_components/turnovercal/
├── __init__.py          # Integration entry point
├── manifest.json        # HA integration metadata
├── config_flow.py       # Setup and options UI flows
├── const.py             # Constants and config keys
├── strings.json         # UI strings
├── translations/en.json # English translations
├── coordinator.py       # DataUpdateCoordinator
├── turnover.py          # Turnover window calculation
├── event_cache.py       # Persistent cache (Store wrapper)
├── http_view.py         # iCal feed HTTP endpoint
├── services.py          # Service call handlers
├── services.yaml        # Service definitions
├── calendar.py          # HA calendar entity
├── token.py             # URL token generation/validation
└── models.py            # Dataclasses

tests/
├── conftest.py          # Shared pytest fixtures
├── test_turnover.py     # Turnover calculation tests
├── test_event_cache.py  # Cache tests
├── test_config_flow.py  # Config flow tests
├── test_http_view.py    # HTTP endpoint tests
├── test_calendar.py     # Calendar entity tests
├── test_coordinator.py  # Coordinator tests
├── test_token.py        # Token tests
└── test_models.py       # Model tests
```

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -x -q

# Run with coverage
uv run pytest tests/ --cov=custom_components/turnovercal

# Run specific test file
uv run pytest tests/test_turnover.py -v

# Run tests matching a pattern
uv run pytest tests/ -k "test_zero_duration"
```

## Linting and Type Checking

```bash
# Ruff linting
uv run ruff check custom_components/ tests/

# Ruff formatting
uv run ruff format custom_components/ tests/

# Type checking
uv run mypy custom_components/turnovercal/

# Docstring coverage (must be 100%)
uv run interrogate -vv --fail-under=100 custom_components/turnovercal/
```

## Key Dependencies

| Package | Version | Purpose |
| --- | --- | --- |
| homeassistant | ≥2026.2.0 | Core HA framework |
| icalendar | ≥6.1.0 | RFC 5545 iCal generation |
| pytest | latest | Test framework |
| pytest-homeassistant-custom-component | latest | HA test fixtures |
| pytest-aiohttp | latest | Async HTTP test client |

## Development Workflow (TDD)

This project follows strict TDD per the constitution:

1. **Red**: Write a failing test for the desired behavior
2. **Green**: Implement minimum code to pass the test
3. **Refactor**: Clean up while keeping tests green
4. **Lint**: Run `uv run ruff check` and `uv run mypy`
5. **Commit**: `git commit -s` with conventional commit message

## Integration Testing with Home Assistant

To test the integration in a live HA instance:

1. Create a symlink or copy `custom_components/turnovercal/` into
   your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "TurnoverCal"
5. Select a Rental Control calendar entity
6. Copy the generated feed URL
7. Subscribe to it in a calendar client

## Commit Message Format

```text
Type(scope): Short imperative description (≤50 chars)

Body explaining what and why. Wrap at 72 characters.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

Types: Fix, Feat, Chore, Docs, Style, Refactor, Perf, Test, Revert,
CI, Build

Always use `git commit -s` for DCO sign-off.
