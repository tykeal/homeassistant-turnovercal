<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# TurnoverCal

[![Validate][validate-badge]][validate-workflow]
[![pre-commit.ci status][pre-commit-badge]][pre-commit-results]
[![License][license-badge]][license]

A [Home Assistant][ha] custom integration that generates cleaning
turnover windows from [Rental Control][rental-control] guest calendars
and serves them as an RFC 5545 iCal feed.

Subscribe the feed URL in Google Calendar, Apple Calendar, Outlook, or
any standards-compliant calendar client to see upcoming cleaning
windows alongside your personal schedule.

## Features

- **Automatic turnover detection** — computes the gap between each
  guest checkout and the next check-in from a Rental Control calendar
  entity.
- **Trailing turnover** — generates a configurable cleaning window
  (default 4 hours) after the last known booking.
- **RFC 5545 iCal feed** — exposes a public URL (secured by a secret
  token) that any calendar client can subscribe to.
- **Historical event caching** — retains past turnover events for a
  configurable retention period (default 6 weeks), even after the
  source booking platform removes the data.
- **Keymaster lock integration** — monitors unlock events from
  [Keymaster][keymaster] to shorten the cleaning window when staff
  arrive early.
- **Manual cleaning signal** — a `turnovercal.mark_cleaning_started`
  service call for properties without smart locks.
- **Stable UIDs** — deterministic event identifiers that survive
  calendar modifications and cancellations.

## Requirements

| Component                        | Version                  |
| -------------------------------- | ------------------------ |
| Home Assistant                   | ≥ 2026.2.0               |
| [Rental Control][rental-control] | Installed and configured |
| Python                           | ≥ 3.13                   |

[Keymaster][keymaster] is optional — only required for automatic early
completion via lock monitoring.

## Installation

### HACS (recommended)

1. Open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/tykeal/homeassistant-turnovercal` with
   category **Integration**.
3. Search for **TurnoverCal** and install it.
4. Restart Home Assistant.

### Manual

Copy the `custom_components/turnovercal` directory into your Home
Assistant `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **TurnoverCal**.
3. Select the Rental Control calendar entity for your property.
4. A unique feed token is generated automatically.

### Options

After setup, configure these options via the integration's
**Configure** button:

| Option                     | Default         | Description                   |
| -------------------------- | --------------- | ----------------------------- |
| Summary prefix             | `Turnover`      | Prefix for event titles       |
| Property name              | *(entry title)* | Property name in event titles |
| Trailing duration (hours)  | `4`             | Window after last booking     |
| Update interval (minutes)  | `5`             | Source calendar poll interval |
| Retention (weeks)          | `6`             | How long to keep past events  |
| Lock monitoring            | `false`         | Enable Keymaster integration  |
| Lock entity                | —               | Lock entity to monitor        |
| Cleaning code slot         | —               | Keymaster code slot for staff |
| Early-unlock grace (hours) | `2`             | Pre-checkout unlock tolerance |

### Subscribing to the feed

After configuration, find the feed URL in the integration's entry
details. It follows this pattern:

```text
http://<ha-host>:8123/api/turnovercal/<token>/calendar.ics
```

Add this URL as a calendar subscription in your preferred client.

## Services

### `turnovercal.mark_cleaning_started`

Signal that cleaning has begun — useful as a fallback when Keymaster
is not available.

| Parameter         | Required | Description                  |
| ----------------- | -------- | ---------------------------- |
| *entity target*   | One of   | Target a TurnoverCal entity  |
| `config_entry_id` | One of   | Target by config entry ID    |
| `timestamp`       | No       | Override the start time      |

## Development

```bash
git clone git@github.com:tykeal/homeassistant-turnovercal.git
cd homeassistant-turnovercal
uv sync
uv run pre-commit install
```

Run the test suite:

```bash
uv run pytest tests/ -x -q
```

See [AGENTS.md](AGENTS.md) for commit conventions and development
workflow details.

## License

This project is licensed under the [Apache License 2.0][license].

SPDX compliance is managed with [REUSE][reuse].

<!-- Badge links -->
[validate-badge]: https://github.com/tykeal/homeassistant-turnovercal/actions/workflows/validate.yaml/badge.svg
[validate-workflow]: https://github.com/tykeal/homeassistant-turnovercal/actions/workflows/validate.yaml
[pre-commit-badge]: https://results.pre-commit.ci/badge/github/tykeal/homeassistant-turnovercal/main.svg
[pre-commit-results]: https://results.pre-commit.ci/latest/github/tykeal/homeassistant-turnovercal/main
[license-badge]: https://img.shields.io/github/license/tykeal/homeassistant-turnovercal
[license]: LICENSE

<!-- External links -->
[ha]: https://www.home-assistant.io/
[rental-control]: https://github.com/tykeal/homeassistant-rental-control
[keymaster]: https://github.com/FutureTense/keymaster
[reuse]: https://reuse.software/
