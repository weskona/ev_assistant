<p align="center">
  <img src="https://raw.githubusercontent.com/weskona/ev_assistant/main/custom_components/ev_assistant/brand/logo.png" alt="EV Assistant logo" width="400">
</p>

# EV Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/v/release/weskona/ev_assistant)](https://github.com/weskona/ev_assistant/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![HA min version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io)
[![Validate](https://github.com/weskona/ev_assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/weskona/ev_assistant/actions/workflows/validate.yml)
[![Downloads](https://img.shields.io/github/downloads/weskona/ev_assistant/total)](https://github.com/weskona/ev_assistant/releases)

[🇩🇪 Deutsche Version](README.de.md) · 📖 [Full documentation on the Wiki](https://github.com/weskona/ev_assistant/wiki)

A comprehensive **EV monitoring integration for Home Assistant**. EV Assistant covers home charging (via evcc), automatic external charge detection and logging, trip logging, charge-efficiency calibration, cost comparison against a combustion car, and a full EV dashboard as a dedicated sidebar panel. Works with any vehicle that exposes an SoC sensor in HA — manufacturer-independent.

---

## Status & Known Limitations

EV Assistant is in **active 0.x development** — pre-1.0. Behavior and configuration can still change between releases; check the [CHANGELOG](custom_components/ev_assistant/CHANGELOG.md) when updating.

It's been tested primarily against **one real setup**: a Stellantis-based vehicle (SoC via the manufacturer's cloud integration), one evcc version, one wallbox. That's a narrow slice of the "any vehicle, any evcc version, any wallbox" space this integration aims to cover — feedback from different vehicles, SoC reporting behavior, evcc versions, and wallboxes is genuinely wanted, not just tolerated.

A few known limitations, stated plainly:

- **Detection and usage profiles are only as good as the SoC signal.** Vehicles that report coarsely (whole-percent steps only, infrequent updates) still work, just less precisely.
- **Usage profiles need time to build up** (roughly two weeks for a full weekday spread) before they're reliable.
- **The evcc write control is opt-in and off by default.** Leave it off at first, watch the `evcc_mode_control` sensor for a while, and only turn on writing once its recommendations look plausible. It sets evcc's charge mode and min/target SoC — it does **not** decide where the charging power comes from (solar/grid/battery); that stays entirely evcc's own job.

---

## Features

- **Home charging monitoring** — tracks kWh and cost via your wallbox energy meter and evcc session history; session history with SOC bars, solar share, and Ø charge power per session.
- **External charge detection** — detects away-from-home charges purely from SoC telemetry (no GPS, no charger list). Prompts you to log the real kWh/price from the receipt.
- **Automatic trip log** — detects trips from your odometer sensor; you confirm start/end locations. CSV export included.
- **Charge-efficiency calibration** — learns your car's real AC→battery efficiency from home sessions and applies it automatically.
- **Odometer statistics** — driven km per day/week/month/year plus rolling averages and calendar-year projection.
- **Cost comparison** — compares total EV spend against an equivalent combustion car, with automatic or live fuel-price lookup.
- **Automatic evcc mode/SoC control** — optionally steers evcc's charge mode from your own usage profile, including a real-time PV-surplus override, an economic cap on grid top-ups, and home-battery priority.
- **Trip import** — bulk-import historical trips from another trip-log app/export.
- **Full sidebar panel** — a built-in, customizable EV dashboard; no Lovelace card setup needed.
- **Multi-vehicle support** — one integration entry per vehicle, with a panel tab switcher.
- **Diagnostics & repair issues** — a downloadable redacted state snapshot, plus Repair issues when a source entity goes stale.
- **Leasing mileage budget, charging cards, and vehicle maintenance tracking** — all fully optional, panel-managed.

See the [Wiki](https://github.com/weskona/ev_assistant/wiki) for the full breakdown of every sensor, service, and panel tab.

---

## Installation

### Via HACS (recommended)

1. **HACS** → Integrations → ⋮ → **Custom repositories**
2. Add URL: `https://github.com/weskona/ev_assistant` — Category: **Integration**
3. Install **EV Assistant**, then restart Home Assistant.

### Manual

1. Copy `custom_components/ev_assistant/` into your `config/custom_components/` directory.
2. Restart Home Assistant.

---

## Getting Started

**Settings → Devices & Services → Add Integration → "EV Assistant"**

Setup runs as a 9-step flow — vehicle details, charging mode, evcc/wallbox, charge power, notifications, detection tuning, trip log, leasing, and cost comparison. Only step 1 (vehicle) is required; everything else is optional and can be added or changed later via **Configure**.

📖 **[Configuration](https://github.com/weskona/ev_assistant/wiki/Configuration)** on the Wiki has the full step-by-step reference.

Once set up, EV Assistant registers a sidebar panel automatically — no dashboard/Lovelace setup needed. See **[Panel Tour](https://github.com/weskona/ev_assistant/wiki/Panel-Tour)** for a tab-by-tab walkthrough.

---

## Documentation

The [Wiki](https://github.com/weskona/ev_assistant/wiki) has the full reference:

| Page | Covers |
|---|---|
| [Configuration](https://github.com/weskona/ev_assistant/wiki/Configuration) | The full 9-step setup flow, every option explained. |
| [Sensors & Entities](https://github.com/weskona/ev_assistant/wiki/Sensors-and-Entities) | Every sensor/binary sensor, with all attributes. |
| [Services](https://github.com/weskona/ev_assistant/wiki/Services) | Every service call, with parameters. |
| [Panel Tour](https://github.com/weskona/ev_assistant/wiki/Panel-Tour) | A tab-by-tab walkthrough of the sidebar panel. |
| [Automatic evcc Mode Control](https://github.com/weskona/ev_assistant/wiki/Automatic-evcc-Mode-Control) | Deep dive: the day-ahead decision, PV-surplus carryover, real-time override, economic cap, charge plan. |
| [External Charge Detection](https://github.com/weskona/ev_assistant/wiki/External-Charge-Detection-Deep-Dive) | Deep dive: the exact state machine behind detecting away-from-home charges. |
| [Usage Profile & Recency-Weighting](https://github.com/weskona/ev_assistant/wiki/Usage-Profile-Deep-Dive) | Deep dive: how your typical daily need is learned and kept current. |
| [Panel Customization Guide](https://github.com/weskona/ev_assistant/wiki/Panel-Customization-Guide) | Practical walkthrough of card selection/reordering/sizing. |
| [Architecture & Contributing](https://github.com/weskona/ev_assistant/wiki/Architecture-and-Contributing) | Module layout, testing, and a guide to adding a new sensor. |
| [FAQ / Troubleshooting](https://github.com/weskona/ev_assistant/wiki/FAQ-Troubleshooting) | Setup issues and common behavior questions. |

---

## Requirements

- **Home Assistant 2024.1** or later
- **evcc** (the add-on/binary itself, reachable over the network) — optional, but required for home charging history and live energy-flow data in the panel. EV Assistant talks to evcc's own REST API directly — no separate `evcc_intg` HA integration needed.
- Any vehicle with an SoC sensor in HA (WiCAN Pro / MQTT, manufacturer cloud integrations, evcc vehicle sensors, ...)

---

## Contributing

Found a bug or have a feature request? Please [open a GitHub Issue](https://github.com/weskona/ev_assistant/issues) — include your Home Assistant version and, if relevant, a debug log (see [Troubleshooting](https://github.com/weskona/ev_assistant/wiki/FAQ-Troubleshooting)). Pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) and the wiki's [Architecture & Contributing](https://github.com/weskona/ev_assistant/wiki/Architecture-and-Contributing) page before opening one.

---

## License

MIT — see [LICENSE](LICENSE).

## Credits & Support

Created and maintained by [@weskona](https://github.com/weskona).

The app icon is based on the "ev-station" glyph from Material Design Icons
(https://pictogrammers.com/library/mdi/), © Pictogrammers, licensed under
Apache License 2.0. The glyph was placed on a custom hexagon tile.

Questions or support requests: please use [GitHub Issues](https://github.com/weskona/ev_assistant/issues) rather than direct messages.
