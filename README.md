# EV Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/v/release/weskona/ev_assistant)](https://github.com/weskona/ev_assistant/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![HA min version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io)

[🇩🇪 Deutsche Version](README.de.md)

A comprehensive **EV monitoring integration for Home Assistant**. EV Assistant covers home charging (via evcc), automatic external charge detection and logging, trip logging, charge-efficiency calibration, cost comparison against a combustion car, and a full EV dashboard as a dedicated sidebar panel. Works with any vehicle that exposes an SoC sensor in HA — manufacturer-independent.

---

## Features

- **Home charging monitoring** — tracks kWh and cost via your wallbox energy meter and evcc session history; displays session history with SOC bars, solar share, and Ø charge power per session.
- **External charge detection** — detects away-from-home charges purely from SoC telemetry (no GPS, no charger list). Prompts you to log the real kWh/price from the receipt.
- **Automatic trip log** — detects trips from your odometer sensor; you confirm start/end locations. CSV export included.
- **Charge-efficiency calibration** — learns your car's real AC→battery efficiency from home sessions and applies it automatically to all estimates.
- **Odometer statistics** — driven km per day/week/month/year plus rolling averages and calendar-year projection, sourced from HA Long-Term Statistics.
- **Cost comparison** — compares total EV spend (home + external charging) against an equivalent combustion car; shown live in the vehicle card. Fuel price can come from a fixed value, a live entity, or automatic Tankerkönig station lookup (cheapest open station), with graceful fallback if the price source becomes unavailable.
- **Trip import** — bulk-import historical trips from another trip-log app/export via a service call, for a one-time backfill without needing the odometer detector.
- **Full sidebar panel** — a built-in EV dashboard; no Lovelace card setup needed.
- **Multi-vehicle support** — configure one integration entry per vehicle; the panel shows pill tabs to switch between them.
- **Diagnostics** — download a redacted config + state snapshot (Settings → Devices & Services → EV Assistant → ⋮ → Download Diagnostics) for troubleshooting or bug reports.
- **Repair issues for stuck sensors** — if a configured source entity (SoC, odometer, plug sensor, ...) goes unavailable or is removed for 30+ minutes, a Repair issue (Settings → System → Repairs) tells you exactly what's affected, instead of estimates silently running on stale data.

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

## Configuration

**Settings → Devices & Services → Add Integration → "EV Assistant"**

Setup runs as a 7-step flow (the same flow is used when editing via **Configure**):

| Step | What it configures |
|------|--------------------|
| 1 — Vehicle | Manufacturer + model (required), first registration date, odometer entity, usable battery capacity in kWh (net, not gross), and a starting charge-efficiency value (auto-calibrated later). |
| 2 — evcc & Wallbox | Vehicle name in evcc (for home-charging history filter) and the wallbox charge-power entity (used as the home-charging signal — any value > 0.1 kW counts as "charging at home"). |
| 3 — Charge Power | Optional vehicle charge-power sensor (improves external-charge estimates) and wallbox energy meter (cumulative kWh counter for efficiency calibration and home-charging costs). |
| 4 — Notifications | Push target devices (`notify.*` entities, multi-select) and which events trigger a push: external charge detected, SoC threshold reached, trip detected, Tankerkönig unavailable. SoC thresholds (50/60/70/80/90/100%) fire once per charging session — home or external — as the battery crosses them. A persistent HA notification for external-charge/trip/Tankerkönig events always fires regardless of this step. |
| 5 — Detection | Fine-tune the detection state machine: `start_delta` (min SoC rise to trigger), `noise` (jitter tolerance, must be < `start_delta`), `idle_timeout_s` (session-end timeout), `drop_ends` (SoC drop that ends a session immediately). Defaults work for most vehicles. Optional: `plug_entity` (a plug/connectivity `binary_sensor`) and `plug_debounce_s` — when set, a confirmed "plugged in" overrides `idle_timeout_s` entirely (no more false session splits on coarsely-reported SoC), a confirmed "unplugged" (held for `plug_debounce_s`, guarding against brief flaky readings) ends the session immediately, and a SoC rise while confirmed unplugged no longer starts a session at all (avoids misreading a regenerative-braking uptick while driving as an external charge). |
| 6 — Trip Log | Optional: `trip_min_km` (minimum trip distance), `trip_idle_timeout_s` (standstill-to-trip-end timeout), `gps_entity` (person, device_tracker, or sensor entity for location suggestions). Also optional: `motor_entity` (a motor/driving `binary_sensor`, e.g. ignition/"Ready") and `motor_debounce_s` — a second signal for vehicles whose odometer updates too coarsely/infrequently to derive trip start/end from it directly. A confirmed "driving" starts/continues a trip even without a fresh odometer reading; `trip_idle_timeout_s` still tolerates brief stops (e.g. stop-start at a light). Distance always comes from the odometer regardless. A further optional toggle, `trip_auto_confirm`, adds a detected trip to the trip log immediately instead of waiting for manual start/end-location confirmation — location comes from `gps_entity` if configured, otherwise stays empty (editable later via `edit_trip`). One more optional field, `usage_profile_buffer_pct` (default 20), sets the safety margin added on top of the historical weekday average for the Usage Profile tab's "needed tomorrow" figure. A further optional field, `pv_forecast_entity`, points at any sensor entity providing tomorrow's solar-yield forecast (e.g. from Solcast or Forecast.Solar, in kWh or Wh) — with it, the charge recommendation lets tomorrow's expected PV generation cover a shortfall the current battery charge alone wouldn't; without it, the recommendation only compares the current battery charge to tomorrow's typical need. |
| 7 — Cost Comparison | Optional: combustion reference consumption (L/100 km), fuel price, home electricity price. Fuel price priority: Tankerkönig auto-detection (pick a fuel type, cheapest open station wins) > live entity > fixed value. Home electricity price: live entity (kWh-weighted average) > fixed value. Also optional: `co2_per_kwh_g` (grid CO2 intensity, g/kWh, default 380 — a rough German-grid-average estimate, adjust for your own supplier/tariff) for the CO2 comparison sensor. |

---

## Sensors

The HA device is named `{Manufacturer} {Model}` (e.g. "VW ID.4"), so entity names appear as `{Device} {Sensor}`.

### External Charging

| Key | Name | Description |
|-----|------|-------------|
| `pending` | External Charge Detection Open | Binary sensor — **on** while ≥ 1 charge awaits confirmation. Attributes: `anzahl_offen` (count), `offene_ladungen` (list). |
| `pending_estimate` | External Charge Pending | Estimated kWh of the oldest pending charge. `unknown` when nothing is pending. |
| `last_kwh` | External Charge kWh (last) | kWh from the receipt for the most recently confirmed charge. |
| `last_cost` | External Charge Cost (last) | Cost of the most recently confirmed charge (kWh × price, plus any `start_fee`). |
| `last_price` | External Charge Price (last) | Price per kWh entered for the most recent charge. |
| `last_duration` | External Charge Duration (last) | Duration of the detected session in minutes. |
| `last_charge_power` | External Charge Avg Power (last) | Average charge power (kW) of the most recently confirmed charge, from kWh ÷ duration. Sessions < 5 min or with implausible power (< 1 kW or > 350 kW) return `unknown`. |
| `total_kwh` | External Charge kWh (total) | Running total of all confirmed external-charge kWh (`state_class: total_increasing`). |
| `total_cost` | External Charge Cost (total) | Running total of all confirmed external-charge costs. |
| `count` | External Charge Count | Total number of confirmed external charges. |

### Home Charging

| Key | Name | Description |
|-----|------|-------------|
| `home_kwh` | Home Charging kWh (total) | Total kWh charged at home — full evcc cumulative history. Prefers evcc's own per-vehicle session data, then evcc's site-wide "total charged energy" statistic (only if a wallbox meter is also configured for this vehicle — that statistic isn't per-vehicle), then falls back to the wallbox energy meter delta since ev_assistant setup. `unknown` without a configured meter. |
| `home_cost` | Home Charging Cost (total) | Home-charging cost — full evcc cumulative history. Prefers the per-vehicle cost reported directly by evcc (`sensor.evcc_charging_sessions_vehicles`, most accurate — evcc applies the actual per-session tariff), then evcc's site-wide average-price statistic × kWh (same per-vehicle guard as above), then falls back to kWh × home electricity price (kWh-weighted if the price comes from a live entity — a price spike with zero charging during it doesn't skew the average). `unknown` without meter or price. |
| `measured_efficiency` | Charge Efficiency (measured) | Live-calibrated AC→battery efficiency from home sessions. Attributes: `anzahl_sessions` (sample count), `benoetigte_sessions` (threshold: 3), `einzelwerte_prozent` (individual readings), `wird_verwendet` (active), `manueller_wert_prozent` (configured fallback). Diagnostic. |

### Odometer & Driven Kilometres

All odometer sensors are `entity_category: diagnostic`. The period and LTS sensors require the odometer entity to be configured in step 1 and to have Long-Term Statistics recorded in HA.

| Key | Name | Description |
|-----|------|-------------|
| `odo` | Odometer | Mirrors the configured odometer entity onto the EV Assistant device. |
| `odo_day_km` | km driven (today) | Km driven since start of the current calendar day. |
| `odo_week_km` | km driven (week) | Km driven since start of the current ISO week. |
| `odo_month_km` | km driven (month) | Km driven since start of the current calendar month. |
| `odo_year_km` | km driven (year) | Km driven since start of the current calendar year. |
| `odo_avg_day` | Avg km/day | 30-day rolling average of daily km (from LTS sum deltas). |
| `odo_avg_week` | Avg km/week | 30-day rolling average, scaled to per-week. |
| `odo_avg_month` | Avg km/month | 90-day rolling average, scaled to per-month. |
| `odo_avg_year` | Avg km/year | 365-day rolling average, scaled to per-year. |
| `odo_year_projected` | Projected km (calendar year) | Extrapolates km from Jan 1 to the full calendar year. Returns `unknown` until ≥ 7 days into the year. |
| `odo_annual_from_reg` | Projected km/year (since registration) | Annual rate since the first-registration date configured in step 1. |

### Trip Log

| Key | Name | Description |
|-----|------|-------------|
| `trip_pending` | Trip Capture Open | Binary sensor — **on** while ≥ 1 detected trip awaits a start/end location. |
| `trip_pending_estimate` | Trip Pending | Distance (km) of the oldest pending trip. |
| `last_trip_km` | Trip km (last) | Distance of the most recently confirmed trip. Attribute `fahrtenbuch` contains the full trip history list. |
| `trip_count` | Trip Log Count | Total number of confirmed trips (`state_class: total_increasing`). |
| `total_trip_km` | Trip Log km (total) | Running total of all confirmed trip distances (`state_class: total_increasing`). |
| `trip_avg_consumption` | Trip Log Avg Consumption | Average kWh consumed per trip, across all trips with known consumption (imported directly, or derived from SoC delta for detected trips). `unknown` without any usable data. |

### Cost Comparison

| Key | Name | Description |
|-----|------|-------------|
| `savings` | Savings vs. ICE Vehicle | Estimated savings vs. the combustion reference over km driven since setup. `unknown` until odometer, combustion consumption, and fuel price are all configured. Attributes: `gefahrene_km` (km driven), `heimladen_kosten` (home-charging cost since ev_assistant setup — a separate baseline from the display sensor's full evcc total), `kosten_ev_gesamt` (total EV cost), `kosten_verbrenner_geschaetzt` (estimated combustion cost), `kraftstoffpreis_live` (live/auto fuel price active), `heimstrompreis_live` (live electricity price active). |
| `verbrenner_price_selected` | Fuel Price (Selected) | The raw fuel price currently in effect (Tankerkönig / live entity / fixed value), with a `quelle` attribute naming the active source. Historized via HA Long-Term Statistics. |
| `vehicle_avg_consumption` | Vehicle Avg Consumption | Overall average consumption in kWh/100 km since setup, from the energy balance: total charged kWh (home + external) ÷ km driven. `unknown` without odometer tracking. |
| `co2_savings` | CO2 Savings vs. ICE Vehicle | Estimated CO2 saved vs. the combustion reference over km driven since setup: (combustion fuel use × its CO2 factor) − (EV kWh used × `co2_per_kwh_g`). Same energy balance as `vehicle_avg_consumption`. `unknown` until odometer and combustion consumption are configured. Attributes: `co2_ev_kg`, `co2_verbrenner_kg`, `co2_ersparnis_kg`. |
| `home_vs_external_price` | External vs. Home Charging Price Difference | Weighted average price paid for external charging minus the home electricity price (both €/kWh, since setup). Positive means external charging cost more per kWh — the usual case. `unknown` without a home electricity price or before any external charge is confirmed. Attributes: `heimladen_preis_kwh`, `fremdladen_preis_kwh`, `differenz_kwh`. |
| `cost_day` / `cost_week` / `cost_month` / `cost_year` | Cost (Today/Week/Month/Year) | Combined home + external charging cost within the current calendar period, same rollover pattern as the driven-km period sensors below. `unknown` before the period's baseline is established (right after setup); clamped to 0 rather than going negative if the total dips below the period baseline (e.g. the home-cost estimate's weighted-average price ticking down as a cheaper session is folded in). |
| `erstzulassung` | First Registration | First-registration date from step 1, exposed as a `date`-typed sensor. Diagnostic. |

### Usage Profile

See the "Usage Profile tab" section above for the underlying idea.

| Key | Name | Description |
|-----|------|-------------|
| `usage_profile` | Usage Profile | Average kWh consumed on today's weekday, from the trip log (`verbrauch_kwh` if known per trip, otherwise its `km` × `vehicle_avg_consumption` as an estimate). Attributes: `montag`…`sonntag` (all 7 weekday averages). `unknown` with less than 7 days of trip-log history (guarantees every weekday has been observed at least once). |
| `usage_profile_tomorrow` | Usage Profile (Needed Tomorrow) | Tomorrow's weekday average plus `usage_profile_buffer_pct` margin — directly comparable to `available_kwh`. Attributes: `wochentag`, `roh_kwh` (unbuffered), `puffer_prozent`, `benoetigt_kwh` (same as the state). |
| `available_kwh` | Available kWh | Current SoC × usable battery capacity. |
| `binary_sensor ... Charge Before Solar Recommended` | **On** when `available_kwh` is less than `usage_profile_tomorrow`'s buffered figure — i.e. charging now (e.g. from the grid) is advisable rather than waiting for tomorrow's solar surplus. If `pv_forecast_entity` is configured, tomorrow's forecasted PV yield is added to `available_kwh` before this comparison, so a shortfall the battery alone can't cover may still be fine if enough solar is expected. Attributes: `verfuegbare_kwh`, `benoetigt_morgen_kwh`, `pv_prognose_morgen_kwh` (only present if `pv_forecast_entity` is configured and resolvable). `unknown` under the same conditions as `usage_profile`. |

---

## Panel / Dashboard

EV Assistant registers a **sidebar panel** automatically — no extra setup beyond the integration itself.

### Overview tab

Live energy-flow diagram showing current PV, grid, home, battery, and wallbox power. Displays the active charging session (mode, SOC, session energy, solar share, tariff) and any pending charges or trips waiting for confirmation. The SOC bar ("Fahrzeug-Akku") reads from the `soc_entity` configured in step 1, falling back to the evcc vehicle SOC if no `soc_entity` is set.

### Vehicles tab

Per-vehicle dashboard in a three-column layout:

| Column | Content |
|--------|---------|
| **Home Charging** | Home charging totals (kWh, EUR, session count, avg. solar share), last session KPIs, full evcc session history. Each entry shows SOC start→end, kWh, Ø charge power, EUR/kWh, cost, solar share, duration, and a SOC bar. |
| **External Charging** | External charge totals, last session KPIs, editable history. Each entry shows kWh, Ø charge power, cost, and a SOC bar; entries with a `start_fee` also show it as a separate line next to the price. |
| **Trip Log** | Trip totals, last trip KPIs (km, route), editable trip history. |

### Usage Profile tab

Answers "do I need to charge tonight, or can charging wait for tomorrow's solar surplus?" from your own driving history — no manual input needed. A bar chart shows the average kWh consumed per weekday (Mon–Sun), derived from the trip log: for each weekday, total kWh used on that weekday ÷ number of that weekday that have elapsed since your first logged trip (days without a trip still count as 0 kWh, so "rarely drives on Sundays" correctly pulls the Sunday average down instead of being ignored). Requires at least 7 days of trip-log history before it shows anything (see `usage_profile` below); today's and tomorrow's bars are highlighted. Below the chart: currently available battery kWh (from SoC × usable capacity), tomorrow's typical need plus your configured buffer, and a plain-language recommendation. If `pv_forecast_entity` is configured (see step 6), tomorrow's forecasted PV yield is also shown and factored into the recommendation — a shortfall the battery alone can't cover may still not need a grid charge if enough solar is expected tomorrow.

**Vehicle card** (above the three columns): vehicle name, current SOC with colour-coded bar (red < 20 %, orange < 40 %, green otherwise), odometer, average consumption (kWh/100 km, from the overall energy balance — total charged kWh since setup ÷ km driven since setup), and charge efficiency. Below that, three columns: a compact km grid (driven km today/week/month/year on the left, rolling averages and projections on the right), a Cost column (combined home + external charging cost today/week/month/year, from the `cost_day`/`cost_week`/`cost_month`/`cost_year` sensors), and the ICE Comparison section (savings, EV cost, estimated combustion cost, cost per 100 km).

**Bar charts**: charging overview, cost overview, and solar share — switchable between week / month / year view with prev/next navigation. Hover over any bar to see its value in a tooltip (replacing the per-bar labels that overlapped in monthly view). Mobile-responsive: on screens ≤ 600 px the three charts stack vertically.

**Number formatting**: all values in the panel respect the HA locale setting (`Settings → Profile → Number format`) — no manual configuration needed.

---

## Services

All services require `config_entry_id` to target a specific vehicle when multiple entries are configured.

| Service | Parameters | Description |
|---------|-----------|-------------|
| `log_charge` | `config_entry_id`, `kwh`, `price_kwh`, `start_ts`*, `start_fee`* | Confirm a pending external charge with receipt values. `start_ts` selects which pending charge (oldest if omitted). `start_fee` is an optional flat fee some networks/chargers add on top of the kWh price (e.g. a start or blocking fee), default 0. |
| `discard_pending` | `config_entry_id`, `start_ts`* | Discard a pending external charge (false positive). |
| `edit_charge` | `config_entry_id`, `erfasst_ts`, `kwh`*, `price_kwh`*, `start_fee`*, `start_ts`*, `end_ts`*, `soc_start`*, `soc_end`* | Correct any field of an already-confirmed history entry, same "only given fields change" model as `edit_trip`. Running totals adjust by the difference when kWh/price/fee change; `soc_start`/`soc_end` changes recompute the SoC delta; `end_ts` is converted to a duration together with the (new or existing) `start_ts`. |
| `delete_charge` | `config_entry_id`, `erfasst_ts` | Remove a confirmed history entry. **Not reversible.** |
| `simulate_event` | `config_entry_id`, `soc_start`, `soc_end`, `energy_source`* | Fire a test external-charge event without a car. |
| `log_trip` | `config_entry_id`, `start_ort`, `end_ort`, `start_ts`* | Confirm a pending trip with a start/end location. |
| `discard_pending_trip` | `config_entry_id`, `start_ts`* | Discard a pending trip. |
| `edit_trip` | `config_entry_id`, `erfasst_ts`, `start_ort`*, `end_ort`*, `start_ts`*, `end_ts`*, `km`*, `odo_start`*, `odo_end`*, `soc_start`*, `soc_end`*, `verbrauch_kwh`* | Correct any field of a confirmed trip log entry, including its date/time. Only given fields change. |
| `delete_trip` | `config_entry_id`, `erfasst_ts` | Remove a confirmed trip log entry. **Not reversible.** |
| `export_fahrtenbuch` | `config_entry_id` | Write full trip history as CSV to `www/ev_assistant_fahrtenbuch_<entry_id>.csv`. |
| `import_fahrtenbuch` | `config_entry_id`, `trips` | Bulk-import historical trips from another trip-log app/export (list of `{start, start_ort, ende, ziel_ort, strecke, ...}`), bypassing the odometer detector. Safe to re-run — entries already present are skipped. |
| `simulate_trip` | `config_entry_id`, `km` | Fire a test trip event without a car. |

*optional

---

## How External Charge Detection Works

EV Assistant needs no GPS, no manufacturer API, and no list of charging stations. The principle in one sentence: **if the battery SoC rises while the home-charging signal is off, the car must be charging elsewhere**.

A small state machine (`engine.py::ChargeDetector`) watches every SoC reading. It tracks the last resting low point ("anchor"). Once SoC has risen ≥ `start_delta` above the anchor *with home-charging off*, a session starts — unless `plug_entity` is configured and confirms the vehicle is unplugged, in which case the rise (e.g. a few points recovered via regenerative braking while driving) just moves the anchor up instead of starting a session. It ends when the home-charging signal turns on, SoC drops > `drop_ends` below the tracked peak, `idle_timeout_s` passes without a new high, or (if `plug_entity` is configured) a confirmed unplug is detected.

Energy is estimated from SoC delta × usable battery ÷ charge efficiency, or — when a vehicle charging-power sensor is configured — from the integrated power curve (more accurate, also works away from home where the wallbox has no data).

Vehicles that report SoC only coarsely or infrequently (some manufacturer cloud APIs) can trip `idle_timeout_s` between two SoC ticks of the *same* ongoing charge, splitting it into several "pending" entries. Two safeguards handle this: newly detected charges are merged into the previous pending one whenever there was no SoC drop in between (a real drop means driving happened, i.e. genuinely separate charge stops); and if a `plug_entity` is configured, a confirmed "plugged in" state overrides `idle_timeout_s` entirely, so the session simply never ends while the car stays connected.

---

## Automatic Efficiency Calibration

Configure a **wallbox energy meter** (step 3 — a cumulative kWh counter). For each home-charging session EV Assistant records the wallbox energy drawn and the SoC gained, and computes:

```
efficiency = (soc_gain% × usable_kWh) ÷ wallbox_kWh_delta
```

After 3 valid sessions (≥ 5 pp SoC gain, result in 50–100 % range) it starts averaging the last 10 samples and automatically applies the result — no restart required. The `Charge Efficiency (Measured)` sensor shows the live value and its status.

---

## Requirements

- **Home Assistant 2024.1** or later
- **evcc_intg** — optional, but required for home charging history and live energy-flow data in the panel
- Any vehicle with an SoC sensor in HA (WiCAN Pro / MQTT, manufacturer cloud integrations, evcc vehicle sensors, ...)

---

## Testing

**Unit tests (no HA needed):**
```bash
python -m pytest tests -q
```

**End-to-end in HA (no car needed):**
- External charge: call `ev_assistant.simulate_event` with `config_entry_id`, `soc_start: 32`, `soc_end: 74`. Expect a notification and `binary_sensor ... External Charge Detection Open` to turn on. Confirm via the panel.
- Trip: call `ev_assistant.simulate_trip` with `config_entry_id`, `km: 12.5`. Confirm via the panel, then call `export_fahrtenbuch` and verify the CSV in `www/`.

---

## License

MIT — see [LICENSE](LICENSE).
