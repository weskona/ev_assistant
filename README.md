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

[🇩🇪 Deutsche Version](README.de.md)

A comprehensive **EV monitoring integration for Home Assistant**. EV Assistant covers home charging (via evcc), automatic external charge detection and logging, trip logging, charge-efficiency calibration, cost comparison against a combustion car, and a full EV dashboard as a dedicated sidebar panel. Works with any vehicle that exposes an SoC sensor in HA — manufacturer-independent.

---

## Status & Known Limitations

EV Assistant is in **active 0.x development** — pre-1.0. Behavior and configuration can still change between releases; check the [CHANGELOG](custom_components/ev_assistant/CHANGELOG.md) when updating.

It's been tested primarily against **one real setup**: a Stellantis-based vehicle (SoC via the manufacturer's cloud integration), one evcc version, one wallbox. That's a narrow slice of the "any vehicle, any evcc version, any wallbox" space this integration aims to cover — feedback from different vehicles, SoC reporting behavior, evcc versions, and wallboxes is genuinely wanted, not just tolerated. That's exactly what the detection logic needs to get more robust.

A few known limitations, stated plainly:

- **Detection and usage profiles are only as good as the SoC signal.** Vehicles that report coarsely (whole-percent steps only, infrequent updates) still work, just less precisely — a small trip or standby drain can get lost between two identical readings.
- **Usage profiles need time to build up** (roughly two weeks for a full weekday spread) before they're reliable. The live-SoC tracker starts from zero on install/upgrade and can't backfill history that was never recorded.
- **The evcc write control is opt-in and off by default.** Starting out, leave it off, watch the `evcc_mode_control` sensor for a while (it computes its recommendation regardless of whether writing is enabled), compare it against what you'd actually want, and only turn it on once the recommendations look plausible. Once enabled, it sets evcc's charge mode and min/target SoC — it does **not** decide where the charging power comes from (solar/grid/battery); that stays entirely evcc's own job.

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
- **Customizable panel layout** — choose which cards appear on the Beta panel and in what order/size (1/3 to full width, for side-by-side layouts), drag-and-drop reorder, persisted server-side so it's the same across devices.
- **Multi-vehicle support** — configure one integration entry per vehicle; the panel shows pill tabs to switch between them.
- **Diagnostics** — download a redacted config + state snapshot (Settings → Devices & Services → EV Assistant → ⋮ → Download Diagnostics) for troubleshooting or bug reports.
- **Repair issues for stuck sensors** — if a configured source entity (SoC, odometer, plug sensor, ...) goes unavailable or is removed for 30+ minutes, a Repair issue (Settings → System → Repairs) tells you exactly what's affected, instead of estimates silently running on stale data.
- **Plug-in time window tracking** — observation-only diagnostic showing when and how long the vehicle is typically plugged in at the wallbox, per weekday, sourced from evcc's own connection state.
- **Optional home-battery charging priority** — while the vehicle is plugged in, temporarily prioritize its charging over the home battery for PV surplus, restoring your own evcc setting the moment it disconnects.

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

## Screenshots

Placeholders below, pending real screenshots being added to this repo.

<!-- Screenshot: sidebar panel, Overview tab -->
<!-- Screenshot: sidebar panel, Vehicle tab -->
<!-- Screenshot: sidebar panel, Usage Profile tab -->
<!-- Screenshot: config flow, step 1 (Vehicle) -->

---

## Configuration

**Settings → Devices & Services → Add Integration → "EV Assistant"**

Setup runs as a 9-step flow (the same flow is used when editing via **Configure**):

| Step | What it configures |
|------|--------------------|
| 1 — Vehicle | Manufacturer + model (required), first registration date, odometer entity, usable battery capacity in kWh (net, not gross), and a starting charge-efficiency value (auto-calibrated later). |
| 2 — Charging Mode | How you charge this vehicle: **Home only**, **Mixed** (default — same as before this step existed), or **Away only**. Purely controls visibility — which of the following steps and which panel tabs/cards appear — never the calculations themselves (a pure external charger is simply the case where the home aggregates are 0). Changeable at any time via **Configure**, without losing any already-entered data: switching to "Away only" just stops showing/actively using the home-related steps/cards, it doesn't delete them; switching back offers them again with whatever was there before. See [Charging Mode](#charging-mode) below. |
| 3 — evcc & Wallbox | The evcc add-on's host (e.g. `http://192.168.178.1:7070`, optional — talks directly to evcc's REST API, no separate HA integration needed), the vehicle name in evcc (for home-charging history filter), and the wallbox charge-power entity (used as the home-charging signal — any value > 0.1 kW counts as "charging at home"). A follow-up step appears only if evcc manages more than one charge point, to pick which one belongs to this vehicle. Also here, all optional and off by default: `evcc_mode_control_enabled` (see [Automatic evcc Mode / SoC Control](#automatic-evcc-mode--soc-control) below), `evcc_battery_priority_enabled` (that control's [home battery priority override](#automatic-evcc-mode--soc-control)), `wallbox_min_power_w` (that control's [real-time PV surplus override](#automatic-evcc-mode--soc-control), default 1380 W), `evcc_realtime_override_min_solar_share` (an optional minimum solar share, %, on that same override — the equivalent price cap is computed live from evcc's own tariffs, not stored as a fixed price), `pv_forecast_today_remaining_entity` (today's remaining PV forecast for that control — a different entity/timespan than `pv_forecast_entity` in step 7), and the optional house usage profile's `home_consumption_entity`/`battery_charge_entity`. **Skipped** in "Away only" mode. |
| 4 — Charge Power | Optional vehicle charge-power sensor (improves external-charge estimates) and wallbox energy meter (cumulative kWh counter for efficiency calibration and home-charging costs). **Skipped** in "Away only" mode. |
| 5 — Notifications | Push target devices (`notify.*` entities, multi-select) and which events trigger a push: external charge detected, SoC threshold reached, trip detected, Tankerkönig unavailable. SoC thresholds (50/60/70/80/90/100%) fire once per charging session — home or external — as the battery crosses them. A persistent HA notification for external-charge/trip/Tankerkönig events always fires regardless of this step. |
| 6 — Detection | Fine-tune the detection state machine: `start_delta` (min SoC rise to trigger), `noise` (jitter tolerance, must be < `start_delta`), `idle_timeout_s` (session-end timeout), `drop_ends` (SoC drop that ends a session immediately). Defaults work for most vehicles. Optional: `plug_entity` (a plug/connectivity `binary_sensor`) and `plug_debounce_s` — when set, a confirmed "plugged in" overrides `idle_timeout_s` entirely (no more false session splits on coarsely-reported SoC), a confirmed "unplugged" (held for `plug_debounce_s`, guarding against brief flaky readings) ends the session immediately, and a *small* SoC rise while confirmed unplugged doesn't start a session at all (avoids misreading a regenerative-braking uptick while driving as an external charge) — an implausibly *large* one (≥15 points, not realistic for regen) starts one anyway, since it's far more likely a charge that was missed during a telemetry gap than actual braking recovery. |
| 7 — Trip Log | Optional: `trip_min_km` (minimum trip distance), `trip_idle_timeout_s` (standstill-to-trip-end timeout), `gps_entity` (person, device_tracker, or sensor entity for location suggestions). Also optional: `motor_entity` (a motor/driving `binary_sensor`, e.g. ignition/"Ready") and `motor_debounce_s` — a second signal for vehicles whose odometer updates too coarsely/infrequently to derive trip start/end from it directly. A confirmed "driving" starts/continues a trip even without a fresh odometer reading; `trip_idle_timeout_s` still tolerates brief stops (e.g. stop-start at a light). Distance always comes from the odometer regardless. A further optional toggle, `trip_auto_confirm`, adds a detected trip to the trip log immediately instead of waiting for manual start/end-location confirmation — location comes from `gps_entity` if configured, otherwise stays empty (editable later via `edit_trip`). One more optional field, `usage_profile_buffer_pct` (default 20), sets the safety margin added on top of the historical weekday average for the Usage Profile tab's "needed tomorrow" figure. A further optional field, `pv_forecast_entity`, points at any sensor entity providing tomorrow's solar-yield forecast (e.g. from Solcast or Forecast.Solar, in kWh or Wh) — with it, the charge recommendation lets tomorrow's expected PV generation cover a shortfall the current battery charge alone wouldn't; without it, the recommendation only compares the current battery charge to tomorrow's typical need. One more optional field, `outside_temp_entity` (a plain temperature sensor or a `weather.*` entity), groups trip consumption into four temperature bands (<0°C, 0–10°C, 10–20°C, >20°C) — once a band has at least 3 trips, `range_estimate` uses that band's average instead of the flat rolling figure, for a more realistic estimate in cold weather. |
| 8 — Leasing | Optional, and only active once **both** `leasing_inkl_km` and `leasing_end_datum` are set: contract starting odometer reading (`leasing_start_km`), contract start/end date, total included mileage, and an optional per-km price for overage (`leasing_preis_mehr_km`) and/or credit for underage (`leasing_preis_minder_km`). Leave it empty and the feature stays fully inactive — no sensor state, no panel content. See [Leasing mileage budget](#leasing-mileage-budget) below. |
| 9 — Cost Comparison | Optional: combustion reference consumption (L/100 km), fuel price, home electricity price. Fuel price priority: Tankerkönig auto-detection (pick a fuel type, cheapest open station wins) > live entity (km-weighted average — only moves as you actually drive, not while the car is parked) > fixed value. Home electricity price: live entity (kWh-weighted average — only moves as you actually charge) > fixed value. Also optional: `co2_per_kwh_g` (grid CO2 intensity, g/kWh, default 380 — a rough German-grid-average estimate, adjust for your own supplier/tariff) for the CO2 comparison sensor. |

### Charging Mode

Purely additive, no data loss: `lade_modus` only controls which config-flow steps and panel tabs/cards are shown, never the underlying calculations. Existing installations from before this setting existed have no stored value and are treated as **Mixed** everywhere (identical to their previous behavior — nothing changes for you unless you deliberately change the setting).

- **Home only** / **Mixed**: everything works exactly as before this setting existed.
- **Away only**: the evcc/wallbox and charge-power setup steps are skipped, and the Overview panel tab shows only what's relevant to a pure external charger — spending over time, total kWh/cost, EUR/100 km, and the combustion-vehicle cost/CO2 comparison — instead of the home/PV/evcc flow diagram and cards (which would be empty or trivially "100% external" anyway). Switching **to** "Away only" doesn't delete any already-configured evcc/wallbox values, it just stops showing/using them; switching back to "Mixed"/"Home only" brings the same steps back with whatever was there before.

---

## Sensors

The HA device is named `{Manufacturer} {Model}` (e.g. "VW ID.4"), so entity names appear as `{Device} {Sensor}`.

### External Charging

| Key | Name | Description |
|-----|------|-------------|
| `pending` | External Charge Detection Open | Binary sensor — **on** while ≥ 1 charge awaits confirmation. Attributes: `anzahl_offen` (count), `offene_ladungen` (list). |
| `pending_estimate` | External Charge Pending | Estimated kWh of the oldest pending charge. `unknown` when nothing is pending. |
| `last_kwh` | External Charge kWh (last) | kWh from the receipt for the most recently confirmed charge. |
| `last_cost` | External Charge Cost (last) | Cost of the most recently *confirmed* charge (kWh × price, plus any `start_fee`/`block_fee`/`time_fee`) — not necessarily the chronologically latest one, see `historie` below. Attribute `historie` contains the external-charge history list from the last `HISTORY_MAX_MONATE` months (see [Data Retention](#data-retention)), sorted by actual charge time (`start_ts`, newest first) — independent of confirmation/logging order, so a manually logged or later-confirmed charge still shows up in the right chronological position. |
| `last_price` | External Charge Price (last) | Price per kWh entered for the most recent charge. |
| `last_duration` | External Charge Duration (last) | Duration of the detected session in minutes. |
| `last_charge_power` | External Charge Avg Power (last) | Average charge power (kW) of the most recently confirmed charge, from kWh ÷ duration. Sessions < 5 min or with implausible power (< 1 kW or > 350 kW) return `unknown`. |
| `total_kwh` | External Charge kWh (total) | Running total of all confirmed external-charge kWh (`state_class: total_increasing`). |
| `total_cost` | External Charge Cost (total) | Running total of all confirmed external-charge costs. |
| `count` | External Charge Count | Total number of confirmed external charges. |

### Home Charging

| Key | Name | Description |
|-----|------|-------------|
| `home_kwh` | Home Charging kWh (total) | Total kWh charged at home — full evcc cumulative history. Prefers evcc's own session log aggregated per vehicle (fetched directly from evcc's `/api/sessions`, no separate integration needed), then evcc's site-wide "total charged energy" statistic (only if a wallbox meter is also configured for this vehicle — that statistic isn't per-vehicle), then falls back to the wallbox energy meter delta since ev_assistant setup. `unknown` without a configured meter or evcc host. Attributes (only if evcc reports an active charge point, step 3): `evcc_solaranteil_pct` (kWh-weighted solar share across your evcc-controlled home sessions), `evcc_kosten_gesamt` (summed session cost — evcc's own per-session total, not a per-kWh rate), `evcc_preis_je_kwh` (derived from the two). Also carries the live `evcc_live` attribute (charge power, mode, SoC, tariffs, PV/grid/battery power, session stats — the source for the panel's Overview tab). External charges and sessions evcc didn't report simply don't contribute — no zeros, no guessing. |
| `home_cost` | Home Charging Cost (total) | Home-charging cost — full evcc cumulative history. Prefers the per-vehicle cost aggregated from evcc's own session log (same source as `home_kwh` above, most accurate — evcc applies the actual per-session tariff), then evcc's site-wide average-price statistic × kWh (same per-vehicle guard as above), then falls back to kWh × home electricity price (kWh-weighted if the price comes from a live entity — a price spike with zero charging during it doesn't skew the average). `unknown` without meter, evcc host, or price. |
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
| `last_trip_km` | Trip km (last) | Distance of the most recently *confirmed* trip — not necessarily the chronologically latest one, see `fahrtenbuch` below. Attribute `fahrtenbuch` contains the trip history list from the last `FAHRTEN_MAX_MONATE` months (see [Data Retention](#data-retention) — older trips move to an archive, use `export_fahrtenbuch` for the full record), sorted by actual trip time (`start_ts`, newest first) — independent of confirmation order, so a trip whose start time was corrected via `edit_trip` still shows up in the right position. Entries without a directly-reported consumption get their `verbrauch_kwh` estimated from the SoC drop during the trip; if that estimate falls outside a plausible ~8–40 kWh/100 km band (trips under 5 km are exempt), the entry is marked `verbrauch_unsicher: true` — shown with a ⚠️ in the panel — since a vehicle connectivity gap during the trip can freeze the SoC reading and badly skew the estimate. Cleared once a real value is entered via `edit_trip`. |
| `trip_count` | Trip Log Count | Total number of confirmed trips (`state_class: total_increasing`). |
| `total_trip_km` | Trip Log km (total) | Running total of all confirmed trip distances (`state_class: total_increasing`). |
| `trip_avg_consumption` | Trip Log Avg Consumption | Average kWh consumed per trip, across all trips with known consumption (imported directly, or derived from SoC delta for detected trips). `unknown` without any usable data. |

### Cost Comparison

| Key | Name | Description |
|-----|------|-------------|
| `savings` | Savings vs. ICE Vehicle | Estimated savings vs. the combustion reference over km driven since setup. `unknown` until odometer, combustion consumption, and fuel price are all configured. Attributes: `gefahrene_km` (km driven), `heimladen_kosten` (home-charging cost since ev_assistant setup — a separate baseline from the display sensor's full evcc total), `kosten_ev_gesamt` (total EV cost), `kosten_verbrenner_geschaetzt` (estimated combustion cost), `kraftstoffpreis_live` (live/auto fuel price active), `heimstrompreis_live` (live electricity price active). |
| `verbrenner_price_selected` | Fuel Price (Selected) | The raw fuel price currently in effect (Tankerkönig / live entity / fixed value), with a `quelle` attribute naming the active source. Historized via HA Long-Term Statistics. |
| `vehicle_avg_consumption` | Vehicle Avg Consumption | Overall average consumption in kWh/100 km since setup, from the energy balance: total charged kWh (home + external) ÷ km driven. `unknown` without odometer tracking. |
| `range_estimate` | Estimated Range | Current SoC × usable battery capacity ÷ actual consumption (kWh/100 km) — using the current temperature band's average where enough trips exist (see `outside_temp_entity`, step 6), else the rolling 30-day/50 km trip-log average, else the lifetime `vehicle_avg_consumption`. Attributes: `verbrauch_kwh_100km` (consumption figure used), `aussentemperatur`/`temperaturband_aktuell` (current temperature and its band, if `outside_temp_entity` is configured), `verbrauch_nach_temperatur` (full per-band breakdown). `unknown` without SoC or any consumption data. |
| `battery_capacity` | Battery Capacity (Measured) | Rolling average of implied battery capacity from your own charging history: external charges with a SoC swing ≥20 percentage points (kWh from the receipt ÷ SoC delta), plus home charging sessions once a measured charge efficiency is available (wallbox kWh × efficiency ÷ SoC delta). The absolute value typically runs *above* the real usable capacity — charging losses aren't modeled, there's no independent second measurement to calibrate them out (unlike home-charging AC efficiency). Track the value over months/years for battery aging — a decline is the actual signal, not the single current number. `unknown` with fewer than 2 qualifying sessions. |
| `equivalent_full_cycles` | Equivalent Full Cycles | Total SoC throughput (discharge from the trip log + charge from external and home charging sessions) expressed as full 0%→100%→0% cycles — the complement to `battery_capacity`, since real battery warranties are usually specified in both cycles and years. `state_class: total` (can decrease if a trip/charge is later deleted). |
| `charging_location_breakdown` | Charging Location Breakdown | "Where does your charging come from" — state is home's share of total kWh. Attributes: `heim`/`fremd`, each with `kwh`, `kosten`, `kwh_anteil_pct`, `kosten_anteil_pct`, `preis_je_kwh` (only present once that location has a known, non-zero value); `heim` additionally gets `solar_pct` if evcc provides it (see `home_kwh` above). Top-level `eur_je_100km` is the vehicle-wide total cost ÷ km driven — deliberately **not** split per location, since you drive on a mix of both and kilometers can't be attributed to one charging source. Also top-level `gesamt_autarkie_pct` (only with at least some known charging, home or external): the solar share of *all* energy charged into the vehicle, home + external combined — external charging always counts as 0% solar (unknown power mix at a public charger, same reasoning as `solar_pct` above only applying to `heim`). Also `ac_dc` (only present with at least one classifiable external charge): `ac`/`dc` sub-breakdown of *external* charging only (home charging is practically always AC by construction), each with the same `kwh`/`kosten`/`anzahl`/`kwh_anteil_pct`/`kosten_anteil_pct`/`preis_je_kwh` shape — see `ac_charging_kwh`/`dc_charging_kwh` below for the classification method. Also `anbieter` (only present with at least one external charge): breakdown by charging network/operator name (e.g. "EnBW", "Ionity" — *where* you charged, as opposed to `ladekarten`/`karte_id` below, which is *what you paid with*), same `kwh`/`kosten`/`anzahl`/shares/`preis_je_kwh` shape, matched case-insensitively (e.g. "EnBW"/"enbw" merge into one bucket, using the most recently used spelling) and grouped under "Unbekannt" for charges without a provider noted rather than dropping them. Ladekarten base fees are **not** split across providers here, for the same reason they're excluded from `fremd` above. `bekannte_anbieter`: the distinct provider names used so far, most-recently-used first — feeds the suggestion list in the panel's provider input. Pure consolidation of numbers computed elsewhere — no new pricing/PV logic. `unknown` without any known charging at all. |
| `ac_charging_kwh` / `dc_charging_kwh` | External Charging AC/DC | kWh of external charging classified as AC/DC, derived from average power per charge (kWh ÷ duration) against a 22 kW threshold — there's no direct AC/DC signal anywhere in the data, 3-phase AC charging realistically can't exceed that. Charges missing kWh or duration (e.g. a fully manual entry without an end time) are excluded rather than guessed. `state_class: total` (can decrease if a charge is later edited/deleted). Attributes: `kosten`, `anzahl`, `kwh_anteil_pct`, `kosten_anteil_pct`, `preis_je_kwh` — same detail as the `ac`/`dc` sub-breakdown on `charging_location_breakdown` above, kept here too for direct dashboard/automation use without an attribute template. `unknown` without any classifiable charge in that category. |
| `co2_savings` | CO2 Savings vs. ICE Vehicle | Estimated CO2 saved vs. the combustion reference over km driven since setup: (combustion fuel use × its CO2 factor) − (EV kWh used × `co2_per_kwh_g`). Same energy balance as `vehicle_avg_consumption`. `unknown` until odometer and combustion consumption are configured. Attributes: `co2_ev_kg`, `co2_verbrenner_kg`, `co2_ersparnis_kg`. |
| `home_vs_external_price` | External vs. Home Charging Price Difference | Weighted average price paid for external charging minus the home electricity price (both €/kWh, since setup). Positive means external charging cost more per kWh — the usual case. `unknown` without a home electricity price or before any external charge is confirmed. Attributes: `heimladen_preis_kwh`, `fremdladen_preis_kwh`, `differenz_kwh`. |
| `cost_day` / `cost_week` / `cost_month` / `cost_year` | Cost (Today/Week/Month/Year) | Combined home + external charging cost within the current calendar period, same rollover pattern as the driven-km period sensors below. `unknown` before the period's baseline is established (right after setup); clamped to 0 rather than going negative if the total dips below the period baseline (e.g. the home-cost estimate's weighted-average price ticking down as a cheaper session is folded in). Attribute `differenz_vorperiode`: the just-completed period's total cost, once a rollover has actually happened (e.g. last month's full cost, visible starting this month) — missing on the first period after setup/upgrade, never guessed. |
| `kwh_day` / `kwh_week` / `kwh_month` / `kwh_year` | kWh (Today/Week/Month/Year) | Same period pattern as `cost_day`/etc., for combined home + external kWh instead of cost. Same `differenz_vorperiode` attribute (kWh instead of EUR). |
| `erstzulassung` | First Registration | First-registration date from step 1, exposed as a `date`-typed sensor. Diagnostic. |

### Leasing Mileage Budget

Purely additive — configure step 7 (`leasing_inkl_km` and `leasing_end_datum` both set) to activate; otherwise this sensor stays `unknown` and the Leasing panel tab shows a setup hint instead of any content.

| Key | Name | Description |
|-----|------|-------------|
| `leasing_km_vor_ruecklauf` | Kilometerbudget vor Rücklauf | How far ahead of (positive) or behind (negative) the straight-line contract plan you are, in km, against the contract's own starting odometer reading (`leasing_start_km`) — deliberately **not** the same "km driven" figure used by the sensors above, which only counts since this integration was set up. Attributes: the raw contract inputs echoed back for display (`vertrag_start_km`, `vertrag_start_datum`, `vertrag_end_datum`, `vertrag_inkl_km`, and `preis_mehr_km`/`preis_minder_km` if configured), `gefahrene_vertrags_km`, `resterlaubte_km` (kilometers still allowed until contract end, regardless of days remaining), `vertrag_tage`/`vergangene_tage`/`verbleibende_tage`, `soll_km_bis_heute` (target-to-date), `status` (`im_budget` / `knapp` / `ueber`, based on the linear projection with a small tolerance), `verbleibendes_tagesbudget_km` (only while contract days remain). Two independent end-of-contract projections, each present only when computable: `linear` (straight-line from the contract start — the stable reference) and `rollierend` (from your last 30 driving days — reacts faster to a recent change in habits), both with `tempo_km_pro_tag`, `erwartete_end_km`, `erwartete_mehr_bzw_minder_km`, and — only if the matching price is configured — `mehrkosten_eur` (overage) or `gutschrift_eur` (underage credit, only ever shown if `leasing_preis_minder_km` is set; most contracts don't refund unused km). |

### Charging Cards

Purely additive and entirely panel-managed (no config-flow step) — see the "Ladekarten tab" section below. Track subscription cards from external-charging providers with a monthly base fee (e.g. an ADAC e-Charge card), independent of individual charges.

| Key | Name | Description |
|-----|------|-------------|
| `ladekarten_kosten` | Ladekarten-Kosten | Sum of all cards' accrued base fees (active days since each card's `start_datum`, capped at `end_datum` if set, ÷ an average 30.44-day month × the fee tier(s) in effect — a deliberate approximation, since real billing happens in monthly jumps, not continuously). `unknown` without any card configured. Attribute `karten`: the full list, each with `id`, `name`, `start_datum`, `end_datum`, `gebuehren` (the list of fee tiers, each `{ab_datum, gebuehr}` — supports a reduced introductory price that later rises to the regular one, see `add_ladekarte_preisstufe` below), `aktuelle_gebuehr` (the fee in effect right now), and its own accrued `kosten` (correctly split across tiers if the fee changed partway through). This sum automatically flows into `savings`, `vehicle_avg_consumption`-adjacent cost totals (EUR/100km via `charging_location_breakdown`), and the `cost_day`/`cost_week`/`cost_month`/`cost_year` sensors — but deliberately **not** into `charging_location_breakdown`'s `fremd.kosten`/`fremd.preis_je_kwh` or any external charge's own price, since a subscription fee isn't tied to a specific kWh or location. |

### Vehicle Maintenance

Purely additive and entirely panel-managed (no config-flow step) — see the "Wartung tab" section below. Track recurring maintenance items (HU/TÜV, inspection, or freely named) with up to three independent due-date criteria per item — a km interval, a time interval in *months*, and/or a fixed date — whichever comes due first decides the status. Time intervals use real calendar-month arithmetic (e.g. Jan 31 + 1 month → Feb 28/29, 24 months from a given month → the same month 2 years later), not a 30-day approximation.

| Key | Name | Description |
|-----|------|-------------|
| `wartung_faellig` | Wartung fällig | Count of due-soon-or-overdue *active* items (paused items don't count). `unknown` without any item configured. Attribute `punkte`: the full list, each with the item's own fields plus the computed `status` (`ok`/`bald_faellig`/`ueberfaellig`/`unbekannt`), `naechste_quelle` (which criterion is winning), `rest_tage`/`faellig_datum` (from whichever criterion is earliest — the km criterion only contributes a date once your recent driving pace, a rolling 30-day average, is known), and `rest_km` (the km criterion's own remaining distance, kept independent of whether it's the winning criterion — so a time-based item with a km interval too still shows both). `presets`: the built-in starting templates (`tuev`, `inspektion`) offered in the panel's add form — pre-fill only, freely overridable, not manufacturer-specific figures; the add form also shows/hides fields to match the chosen preset (HU/TÜV: fixed date + interval, no km/last-service fields; Inspektion: km interval + interval + last service, no fixed date; no preset: everything). Each item can optionally override the global "due soon" warning window via a per-item reminder (`reminder_tage` internally, entered in months for the time-based side, or directly in km for the km-based side) — falls back to the global default when unset. Marking a HU/TÜV-style item (fixed date *and* a month interval) done automatically advances that fixed date by the interval, counted from the actual completion date — so completing it early pulls the next due date forward too, rather than preserving the original rhythm. |

### Usage Profile

See the "Usage Profile tab" section above for the underlying idea.

| Key | Name | Description |
|-----|------|-------------|
| `usage_profile` | Usage Profile | Average kWh consumed on today's weekday, from the trip log (`verbrauch_kwh` if known per trip, otherwise its `km` × `vehicle_avg_consumption` as an estimate). Attributes: `montag`…`sonntag` (all 7 weekday averages). `unknown` with less than 7 days of trip-log history (guarantees every weekday has been observed at least once). |
| `usage_profile_tomorrow` | Usage Profile (Needed Tomorrow) | Tomorrow's weekday average plus `usage_profile_buffer_pct` margin — directly comparable to `available_kwh`. Attributes: `wochentag`, `roh_kwh` (unbuffered), `puffer_prozent`, `benoetigt_kwh` (same as the state). |
| `available_kwh` | Available kWh | Current SoC × usable battery capacity. |
| `house_usage_profile` | House Usage Profile | Average house kWh consumption on today's weekday (including optional battery charging, see below), from a cumulative home-consumption meter instead of the trip log. Attributes: `montag`…`sonntag` (only actually-observed weekdays — a never-observed day is missing from the result rather than assumed 0 kWh), `konfiguriert` (whether `home_consumption_entity` is set), `speicher_enthalten` (whether `battery_charge_entity` is set). `unknown` without `home_consumption_entity` or without a single observed day yet. |
| `plug_window` | Plug Time Window | Observation-only diagnostic: average hours per weekday the vehicle is plugged in at the wallbox, sourced from evcc's own loadpoint connection state (not the separate, optional `plug_entity`). Attributes: `montag`…`sonntag` (only actually-observed weekdays), `heute` (today's still-running tally), `tage` (the raw recent-days window per weekday, each entry with `date`, `stunden`, `erster_connect`, `letzter_disconnect`). Doesn't influence charge mode/SoC control. |
| `evcc_mode_control` | evcc Mode Control | Diagnostic sensor for the [automatic evcc mode/SoC control](#automatic-evcc-mode--soc-control) below — the mode (`pv`/`minpv`/`now`) it's currently steering toward (already including the [real-time PV surplus override](#automatic-evcc-mode--soc-control) below), or `unknown` if that feature is off (default) or the usage profile isn't available yet. Attributes: `min_soc`, `target_soc`, `verfuegbare_kwh`, `min_kwh`, `target_kwh`, `rest_heute_kwh`, `rest_heute_roh_kwh`, `pv_rest_heute_roh_kwh`, `haus_rest_heute_kwh`, `pv_fuer_auto_kwh`, `pv_ueberschuss_puffer_kwh` (today's leftover PV surplus credited against tomorrow's/the buffer's requirement, see above), `zuletzt_geschrieben`, `aktiv`, `min_soc_scope`, `limit_soc_scope`, `balancing_enabled`, `balancing_aktiv`, `naechste_vollladung_faellig_ts` (see [weekly full charge](#automatic-evcc-mode--soc-control) below), `pv_override_aktiv`, `pv_ueberschuss_w` (see [real-time PV surplus override](#automatic-evcc-mode--soc-control) below), `pv_override_mischpreis_kwh` (the blended EUR/kWh cost of that override's grid top-up, see the economic-cap paragraph below), `pausiert` (whether the manual write-back pause, `set_evcc_mode_control_pause` service/panel toggle, is currently on). |
| `evcc_charge_plan` | evcc Charge Plan | Diagnostic sensor mirroring evcc's own charging plan (target-time charging, see [Charge Plan](#charge-plan) below) — the target time as its state (`unknown` with no plan set), attributes `target_soc`, `projected_start`, `projected_end`, `aktiv` (evcc is currently charging to fulfil this plan, vs. just having one scheduled for later). Works independently of `evcc_mode_control_enabled` — only needs `evcc_host` configured. |
| `binary_sensor ... Charge Before Solar Recommended` | **On** when `available_kwh` is less than `usage_profile_tomorrow`'s buffered figure — i.e. charging now (e.g. from the grid) is advisable rather than waiting for tomorrow's solar surplus. If `pv_forecast_entity` is configured, tomorrow's forecasted PV yield is added to `available_kwh` before this comparison, so a shortfall the battery alone can't cover may still be fine if enough solar is expected. Attributes: `verfuegbare_kwh`, `benoetigt_morgen_kwh`, `pv_prognose_morgen_kwh` (only present if `pv_forecast_entity` is configured and resolvable). `unknown` under the same conditions as `usage_profile`. |

### Automatic evcc Mode / SoC Control

An **opt-in** extension of the usage profile above (`evcc_mode_control_enabled` in the evcc/Wallbox step, off by default) that doesn't just *recommend* charging — it actually writes evcc's charge mode (`pv`/`minpv`/`now`) and the vehicle's min/target SoC, so the wallbox follows the usage profile without any manual mode-switching. Requires an `evcc_host` (step 2); a repair issue is raised if evcc's SoC scope (loadpoint- vs. vehicle-level, depending on the evcc version) can't be determined — the mode is still set in that case, just not the SoC limits.

It's a three-tier decision, re-evaluated roughly every minute and **written whenever it differs from evcc's actual live state** — not just from what ev_assistant itself last wrote, so it self-heals if evcc silently loses the setting again (e.g. an evcc add-on restart falling back to its own config defaults — without this, the weekly full charge below could stay permanently blocked, since the vehicle would never actually reach 100% again). One consequence: a manual override made directly in evcc's own UI now only survives until the next cycle (~1 min), not indefinitely — use the `set_evcc_mode_control_pause` service (also exposed as a toggle right in the "Automatische Ladesteuerung" panel card, see [Services](#services) below) to hold off write-back until you switch it back off, when you need a deliberate manual change to stick for a while:

- **`pv`** (pure solar charging) — the current battery covers the rest of today plus the next two days of typical usage.
- **`minpv`** (minimum power + solar) — covers the rest of today plus tomorrow, but not the two-day buffer.
- **`now`** (force grid charging) — doesn't even cover tomorrow.

Example: usage profile says 8 kWh/day, buffer 20%, 45 kWh usable, 40% SoC (18 kWh) available. Target = (8 + 8 + 8) × 1.2 = 28.8 kWh, min = (8 + 8) × 1.2 = 19.2 kWh → 18 kWh is below even the minimum, so evcc gets `now` plus a min-SoC around 43% and a target-SoC around 64%.

The usage profile feeding this control is sourced entirely from a **live SoC ratchet**, not the trip log — it tracks the vehicle's total net discharge (driving *and* standby drain, e.g. climate preconditioning while parked) continuously from every SoC reading, with the same noise tolerance as charge detection (step 5). This matters for vehicles that only report SoC in coarse whole-percent steps: several short trips in a row can each show 0% delta (too little discharge to cross a full point within one trip) while the real drop is only reported later, while parked between them — with a pure trip-log-based profile, that discharge would vanish entirely instead of showing up somewhere. The trip log itself and its own consumption figures (e.g. `Trip Log Avg Consumption`) are unaffected by this — it only feeds this control's own profile. It starts from scratch on upgrade/setup and takes 1-2 weeks to build up (a weekday not yet observed is conservatively treated as 0 kWh need), since there's no historical SoC log to backfill from and no less-accurate fallback is used in the meantime.

Both this vehicle profile and the optional house profile below use a **recency-weighted sliding window** rather than a lifetime average: each weekday keeps only the last 8 observed calendar days, so a genuinely changed usage pattern (new commute, seasonal change) is reflected within weeks instead of taking years to move a lifetime average. A day correctly excluded as vacation (optional `urlaub_entity`, step 3) simply never enters its weekday's window at all, rather than pulling an average down as a "0 kWh day".

Both profiles also feed into `remaining_today_kwh()` with a **time-of-day taper**: today's typical need is scaled down proportional to how much of the day has already elapsed before subtracting what's already been used today, so the recommended remaining need for today naturally approaches zero as the day progresses — instead of only a flat weekday average compared against today's usage regardless of the current time (which could otherwise recommend a top-up in the evening even though the day's typical need was already effectively covered).

Any leftover PV surplus forecasted for **today**, beyond what today itself needs, also reduces `min_kwh`/`target_kwh` (tomorrow's/the buffer window's requirement) — not just today's own figure. Without this, a single unusually high-consumption day inside the buffer window (e.g. a planned weekend trip) could force overnight grid pre-charging well in advance, even on a day with abundant solar forecast that alone would cover the whole window (production incident: the vehicle charged from the grid all night for an upcoming high-usage Saturday, despite a full day of solar ahead that would have covered it). The `evcc_mode_control` sensor's `pv_ueberschuss_puffer_kwh` attribute shows how much surplus was credited this way.

**Optional house usage profile** (`home_consumption_entity`, `battery_charge_entity`): without it, any configured "PV forecast remaining today" (`pv_forecast_today_remaining_entity` — separate from, and for a different time span than, the "PV forecast tomorrow" field in step 7) would be credited entirely to the vehicle, overstating how much solar surplus is actually left over for it once the house (and an optional home battery, if its charging isn't already counted in the consumption meter) has taken its share. Configuring a cumulative home-consumption energy meter fixes that — the house's own typical remaining-today need gets subtracted from the PV forecast first. Like the vehicle's usage profile, it builds up its own per-weekday average from scratch and needs a few days of history (starting the day after `home_consumption_entity` is set) before it has any effect; until then it's silently treated as 0 kWh, i.e. today's behavior without it.

**Optional weekly full charge for cell balancing** (`weekly_full_charge_enabled`, off by default, plus `weekly_full_charge_interval_days`, default 7): most EVs are healthiest spending most of their time in a mid-range SoC window, which is exactly what the profile-based control above aims for — but the battery management system still needs an occasional full charge to 100% to recalibrate its cell balancing. When enabled and at least the configured number of days have passed since the SoC last reached ~100% (98% is treated as "full" — many vehicles never report an exact 100%), this overrides the profile-based target with target SoC 100% / mode `minpv` until 100% is actually reached, then resets the counter. It doesn't matter *how* 100% was reached — a manual full charge (a longer trip, a deliberate top-up) resets the countdown exactly the same as a triggered one, so this never charges further than necessary. The switch can also be flipped directly from the Wallbox card in the panel (a runtime override, like the buffer slider above — no integration reload) — the interval itself stays an options-flow-only setting.

  Stated plainly, since it's easy to assume otherwise: this **only** ever sets target SoC and charge mode. It does **not** decide *where* the charging power comes from — that's entirely evcc's own job, unaffected by this integration. `minpv` uses whatever minimum charge power you've configured in evcc as a floor, topped up with solar surplus when available; if you want a full-charge to avoid draining a home battery, that's evcc's own discharge-lockout setting, already yours to control there — this integration doesn't touch it.

**Real-time PV surplus override** (`wallbox_min_power_w`, default 1380 W = 6A × 230V single-phase — for a three-phase wallbox connection it'd be 6A × 3 × 230V ≈ 4140 W): the three-tier decision above is re-evaluated roughly once a minute from the usage profile, which is intentionally slow-moving (day-scale). On top of it, a second, faster layer reacts to the *current* PV surplus (site PV minus grid export, read from the same live evcc feed already polled for the panel — no extra evcc call) and can upgrade `pv` to `minpv` in real time, **never** the other way, and only while the usage profile itself recommends `pv`. The problem it solves: in pure `pv` mode, the wallbox only draws power once the surplus clears its own minimum charge power (`wallbox_min_power_w`) — a surplus just below that (e.g. 1200 W against a 1380 W floor) charges nothing at all and gets fed into the grid unused, even though `minpv` would happily take it (topped up with a small grid/battery contribution). Once the surplus clears the floor by a further 100 W margin, it switches back to `pv` — that margin (hysteresis) is what stops it flapping back and forth on a surplus that hovers right at the threshold (passing clouds, a kettle switching on). It deliberately does **not** count PV currently charging a home battery as "surplus" — that's already being put to good use (autarky/cell balancing) rather than wasted, and upgrading the wallbox against that would fight any battery-protection priority you've set up in evcc itself.

**Optional economic cap on the grid top-up** (`evcc_realtime_override_min_solar_share`, %, no default — the override above is unconditional on wattage alone until this is set): solar power used for charging isn't actually free — every kWh not exported instead costs you the feed-in tariff you gave up. Filling the gap up to `wallbox_min_power_w` with grid power therefore has a real blended cost: `(surplus_w × feed-in tariff + grid_topup_w × grid price) ÷ wallbox_min_power_w`. Rather than entering that price directly, you set a minimum acceptable **solar share** (e.g. 50%) and the equivalent price ceiling is computed fresh on every cycle from evcc's own live tariffs (`tariffFeedIn`/`tariffGrid`) — so it stays correct automatically if your tariff changes (provider switch, dynamic pricing), instead of going stale like a fixed price would. The override only upgrades to `minpv` when the blended cost implies at least that much solar share; otherwise it stays `pv` and the small surplus is fed in instead of buying expensive grid power to use it. The `evcc_mode_control` sensor's `pv_override_mischpreis_kwh` attribute shows the current blended price whenever a `minpv` candidate is present, even before you've configured a cap, so you can see what a sensible share would be.

**Optional home battery priority** (`evcc_battery_priority_enabled`, off by default): the setting above deliberately respects evcc's own home-battery priority (`prioritySoc`) — but a `prioritySoc` fixed at 100% means the battery always charges to full *first* on any PV-surplus day, before the vehicle gets anything at all. If the vehicle happens to leave right around when the battery reaches 100%, it gets essentially no solar charge, and any further surplus that day goes to the grid unused instead of ever reaching it. When enabled, ev_assistant lowers evcc's site-wide `prioritySoc` while the vehicle is plugged in — giving it full priority over the battery for PV surplus — and restores the threshold you had set once the vehicle disconnects, rather than resetting it to a fixed value. This only changes how PV *charging* surplus is split between wallbox and battery; it has no effect on battery *discharge* behavior, which stays entirely under whatever separate control (evcc's own battery mode, or your own automation) you already have for that.

### Charge Plan

A separate, opt-in-by-use complement to the automatic mode/SoC control above: sets evcc's own charging plan (target-time charging) via the `set_evcc_charge_plan` service (`config_entry_id`, `target_soc`, `target_time` as a Unix timestamp) or the "Ladeplan" panel card — "the car needs to be at 80% by 7am tomorrow." evcc then decides itself *when* to charge (tariff-/PV-optimized) to hit that deadline, the same mechanism its own UI's charging plan uses. Only needs `evcc_host` configured, no `evcc_mode_control_enabled`.

This solves a case the profile-based mode control above doesn't: a hard deadline. The three-tier `pv`/`minpv`/`now` decision only looks at a rolling 1-2 day buffer, never a specific clock time.

**While a plan is active** (`evcc_charge_plan` sensor has a state), the automatic mode/SoC control above steps back entirely and writes nothing — regardless of whether the plan was set through ev_assistant or directly in evcc's own UI, so the two mechanisms never fight over the loadpoint. It resumes automatically as soon as the plan is cleared (`clear_evcc_charge_plan` service, or the panel's "Plan löschen" button), or once evcc's own plan naturally expires.

---

## Panel / Dashboard

EV Assistant registers a **sidebar panel** automatically — no extra setup beyond the integration itself. If you have more than one vehicle (i.e. more than one EV Assistant integration instance), a vehicle switcher appears in its own row above the tab bar; every tab shows the currently selected vehicle's data. With only one vehicle configured, the switcher is hidden entirely.

### Overview (Beta) tab

The main dashboard tab, built entirely from already-existing sensors/attributes (no new calculations): a hero card for this month's cost so far (with last month's total, once known) next to a vehicle SoC row, a wallbox status card (always the same layout regardless of state — charging/connected/not connected — showing the live or last-session solar/grid split, mode, and min-/target-SoC limits), a KPI row (EUR/100 km, savings vs. combustion, CO2 saved), and — as horizontal proportion bars instead of tables — a combustion-car comparison and a charging-location breakdown. Mode-adaptive: in **Away only** [charging mode](#charging-mode) the wallbox card and vehicle SoC row are replaced by the last confirmed external charge (no wallbox in that mode), and the location breakdown is an AC/DC split of external charging only (marked as an estimate — see the `charging_location_breakdown` sensor above). Cards/rows for values that don't apply are omitted entirely rather than shown empty or as 0. *A multi-month spending history (bar chart of completed past months) is a planned addition — the underlying data exists but isn't aggregated into a series yet, see the CHANGELOG.*

(The "(Beta)" name is a holdover from when this ran side by side with a separate classic Overview tab, for comparison — that older tab was removed in 0.98.8 once this one fully replaced it.)

When a charge or trip is awaiting confirmation, a blinking pill appears at the top of this tab ("1 offene Fremdladung" / "N offene Fahrten") — clicking it opens a popup with the same confirm/discard cards as the Vehicle tab's "Laufende Erfassung" card, without having to switch tabs.

If [automatic evcc mode/SoC control](#automatic-evcc-mode--soc-control) is enabled, an additional "Automatische Ladesteuerung" card shows the currently steered mode, min-/target-SoC, today's remaining need (hover for the full PV/house calculation chain), how much forecasted PV is left over for the car, and when evcc was last actually written, plus a pause toggle — hidden entirely while the feature is off. A "Ladeplan" card (see [Charge Plan](#charge-plan) above) is shown whenever evcc is configured at all, independent of that toggle — lets you set/clear a target-time charging deadline right from the panel.

An "Anpassen" (gear) button lets you customize this tab: choose which cards are shown, their order (drag-and-drop, works with touch and mouse), and their width (1/3, 1/2, 2/3, or full — so cards can sit side by side). Hiding a card keeps it available in the picker for later, rather than removing it permanently. The layout is saved server-side (`set_panel_layout` service under the hood), so it's the same everywhere you open the panel, not a per-browser preference.

### Vehicle tab

Per-vehicle dashboard in a three-column layout:

| Column | Content |
|--------|---------|
| **Home Charging** | Home charging totals (kWh, EUR, session count, avg. solar share), last session KPIs, full evcc session history. Each entry shows SOC start→end, kWh, Ø charge power, EUR/kWh, cost, solar share, duration, and a SOC bar. |
| **External Charging** | External charge totals, last session KPIs, editable history. Each entry shows kWh, Ø charge power, cost, and a SOC bar; a `start_fee`, `block_fee`, and/or `time_fee` each show as their own separate line next to the price — some receipts list several at once (e.g. a flat start fee plus a blocking fee for overstaying after charging finished, or a time-based fee some fast-charging networks bill instead of/alongside kWh). A "Log manually" button next to the history heading opens a form to add a charge without any prior detection — start/end time, kWh, price, SoC start/end, and the optional fees. |
| **Trip Log** | Trip totals, last trip KPIs (km, route), editable trip history. Each entry with a known consumption shows both the trip's total kWh and its kWh/100km rate side by side, to avoid misreading the absolute figure as a rate. |

Above the three columns, two bar charts ("Ladeübersicht"/charging overview and "Kostenübersicht"/cost overview) plot home vs. external kWh/cost side by side over time, plus a third chart of the average home solar share ("Solaranteil"). Mode-adaptive like the other tabs: in **Home only** mode, the External Charging column and the external row/legend in the two charts are omitted. In **Away only** mode, the Home Charging column, the home row/legend, and the solar-share chart (solar only ever applies to home charging) are all omitted. **Mixed** mode (the default) is unchanged.

### Usage Profile tab

Answers "do I need to charge tonight, or can charging wait for tomorrow's solar surplus?" from your own driving history — no manual input needed. A bar chart shows the average kWh consumed per weekday (Mon–Sun), derived from the trip log: for each weekday, total kWh used on that weekday ÷ number of that weekday that have elapsed since your first logged trip (days without a trip still count as 0 kWh, so "rarely drives on Sundays" correctly pulls the Sunday average down instead of being ignored). Requires at least 7 days of trip-log history before it shows anything (see `usage_profile` below); today's and tomorrow's bars are highlighted. Below the chart: currently available battery kWh (from SoC × usable capacity), tomorrow's typical need plus your configured buffer, and a plain-language recommendation. If `pv_forecast_entity` is configured (see step 6), tomorrow's forecasted PV yield is also shown and factored into the recommendation — a shortfall the battery alone can't cover may still not need a grid charge if enough solar is expected tomorrow.

Below that, as its own card: the **House Usage Profile** (see `home_consumption_entity`/`battery_charge_entity`, and [automatic evcc mode/SoC control](#automatic-evcc-mode--soc-control) below) — the same bar-chart idea, but for house consumption instead of the vehicle, including battery charging if configured (shown in the subtitle). Appears once `home_consumption_entity` is configured; a weekday never yet observed shows a dashed "–" bar instead of falsely showing 0 kWh — unlike the vehicle profile above, this card doesn't need a full 7 days before showing anything, it fills in day by day.

A third card, **Steckerprofil** (Plug Time Window, see `plug_window` above), shows the same bar-chart idea again — but for how many hours per weekday the vehicle is typically plugged in at the wallbox, not any energy figure. Observation only: helps you see when charging windows actually occur, without affecting the automatic control above.

### Analyse tab

Longer-term signals that don't belong on the day-to-day vehicle card: the measured battery capacity trend and equivalent full cycles (see `battery_capacity`/`equivalent_full_cycles` above), the charging location breakdown (home vs. external — kWh, cost, share, price/kWh, home's solar share, and a vehicle-wide EUR/100km, see `charging_location_breakdown` above) including an AC/DC sub-breakdown of external charging once at least one charge can be classified, a horizontal-bar breakdown by charging network/operator ("Verteilung nach Anbieter", see `anbieter` on `charging_location_breakdown` above) shown once at least two provider buckets exist and hidden entirely in **Home only** mode (no external charging happens there), and — if `outside_temp_entity` is configured (step 6) — a bar chart of average consumption per temperature band, with the current outside temperature and its active band shown alongside.

**Vehicle card** (above the three columns): vehicle name, current SOC with colour-coded bar (red < 20 %, orange < 40 %, green otherwise), odometer, average consumption (kWh/100 km, from the overall energy balance — total charged kWh since setup ÷ km driven since setup), and charge efficiency. Below that, three columns: a compact km grid (driven km today/week/month/year on the left, rolling averages and projections on the right), a Cost column (combined home + external charging cost today/week/month/year, from the `cost_day`/`cost_week`/`cost_month`/`cost_year` sensors), and the ICE Comparison section (savings, EV cost, estimated combustion cost, cost per 100 km).

**Bar charts**: charging overview, cost overview, and solar share — switchable between week / month / year view with prev/next navigation. Hover over any bar to see its value in a tooltip (replacing the per-bar labels that overlapped in monthly view). Mobile-responsive: on screens ≤ 600 px the three charts stack vertically.

**Number formatting**: all values in the panel respect the HA locale setting (`Settings → Profile → Number format`) — no manual configuration needed.

### Leasing tab

Only shows content once the Leasing step is configured (see `leasing_km_vor_ruecklauf` above) — otherwise a plain "set this up in options" hint instead of empty cards. Shows the contract's start/end date, elapsed vs. remaining days, kilometers driven since contract start vs. the target-to-date, and kilometers still allowed until contract end, plus — if configured — the per-km overage/underage price. A progress bar shows the actual odometer progress against the total included mileage, with a marker for where the linear plan says you should be today. Below that, the linear and rolling projections side by side (Ø km/day, expected end-odometer, projected over/under-km, and — only if configured — the €-estimate), and the remaining daily budget. Missing values (e.g. no rolling pace yet, no price configured for a credit) are hidden rather than shown as 0 or "n/a".

### Ladekarten tab

Always visible in the tab bar (so there's somewhere to add your first card from), but shows a plain empty-state hint instead of any content until at least one charging card exists. Add/edit/delete cards directly in the panel — name, monthly fee, start date, and an optional end date (a cleared end date reactivates a cancelled card). Each card shows its current fee, its price history, and its accrued cost so far; a "Preisänderung" mini-form adds a new fee tier (e.g. once a reduced introductory price ends), with a delete action per tier except the earliest. A KPI at the top sums all cards. The manual-entry and edit forms for external charges gain a "Ladekarte" dropdown once at least one card exists, to optionally note which card was used for a given charge (shown as a 🎫 badge in the history) — purely informational, doesn't affect any cost calculation.

Separately, those same forms (plus the pending-charge confirmation card) also have an "Anbieter" field — free-text, with previously used names suggested — for the charging network/operator itself (e.g. "EnBW", "Ionity"), shown as a 🏢 badge in the history. Don't confuse the two: a charging card is *what you paid with*, the provider is *where you charged* — a charge can have either, both, or neither, and they're tracked completely independently (see `anbieter` on `charging_location_breakdown` above, and the "Verteilung nach Anbieter" card in the Analyse tab below).

### Wartung tab

Always visible in the tab bar, but shows a plain empty-state hint instead of any content until at least one maintenance item exists. The add form (and each item's edit form) is grouped into Grunddaten (optional preset + name), Fälligkeit (the three criteria — at least one required, whichever comes first wins), Letzter Service (km + date), Erinnerung (optional per-item reminder override), and Kosten, instead of one flat row of fields. Picking a preset in the add form both pre-fills defaults and shows only the fields that preset actually uses (see [Vehicle Maintenance](#vehicle-maintenance) above); picking "eigene" (no preset) shows everything. Each item in the list shows a status indicator (OK/bald fällig/überfällig), the earliest-due criterion ("zuerst fällig: in X Tagen (date)"), a separate remaining-distance line when a km interval is also configured ("noch X km bis Y km", omitted if that would just duplicate the primary line), the configured criteria, the last-service record, and an optional cost. Actions per item: mark as done (resets the last-service record to today's odometer/date, and for a HU/TÜV-style item also advances its fixed due date by the configured interval), edit, delete, or pause (excludes it from the due count without deleting it).

---

## Services

All services require `config_entry_id` to target a specific vehicle when multiple entries are configured.

| Service | Parameters | Description |
|---------|-----------|-------------|
| `log_charge` | `config_entry_id`, `kwh`, `price_kwh`, `start_ts`*, `end_ts`*, `soc_start`*, `soc_end`*, `start_fee`*, `block_fee`*, `time_fee`*, `karte_id`*, `anbieter`* | Confirm a pending external charge with receipt values, or — if none is pending — log a completely standalone entry (same as the panel's "Log manually" button in the External Charging card). `start_ts` selects which pending charge (oldest if omitted); for a standalone entry it's the charge's start time. `end_ts`/`soc_start`/`soc_end` only take effect for a standalone entry (a confirmed pending charge keeps its own measured duration/SoC): `end_ts` combines with `start_ts` into the session duration, `soc_start`/`soc_end` combine into `delta_soc`. `start_fee`/`block_fee`/`time_fee` are optional flat fees some networks/chargers add on top of the kWh price (a start fee, a blocking fee for overstaying, and a time-based fee for charging duration) — kept as separate fields since a receipt can list several at once, default 0 each. `karte_id` optionally notes which charging card (see [Charging Cards](#charging-cards) below) was used — purely informational, doesn't affect any cost calculation. `anbieter` optionally notes the charging network/operator (e.g. "EnBW", "Ionity") — free text, not a fixed catalog; the panel suggests previously used names but anything can be typed. This is a *different* thing from `karte_id`: a charge always has a location it happened at, independent of which card (if any) paid for it. |
| `discard_pending` | `config_entry_id`, `start_ts`* | Discard a pending external charge (false positive). |
| `edit_charge` | `config_entry_id`, `erfasst_ts`, `kwh`*, `price_kwh`*, `start_fee`*, `block_fee`*, `time_fee`*, `start_ts`*, `end_ts`*, `soc_start`*, `soc_end`*, `karte_id`*, `anbieter`* | Correct any field of an already-confirmed history entry, same "only given fields change" model as `edit_trip`. Running totals adjust by the difference when kWh/price/fees change; `soc_start`/`soc_end` changes recompute the SoC delta; `end_ts` is converted to a duration together with the (new or existing) `start_ts`. `karte_id`: `0` removes an existing card assignment, any other value sets/changes it. `anbieter`: an empty string removes an existing provider name, any other value sets/changes it. |
| `delete_charge` | `config_entry_id`, `erfasst_ts` | Remove a confirmed history entry. **Not reversible.** |
| `simulate_event` | `config_entry_id`, `soc_start`, `soc_end`, `energy_source`* | Fire a test external-charge event without a car. |
| `log_trip` | `config_entry_id`, `start_ort`, `end_ort`, `start_ts`* | Confirm a pending trip with a start/end location. |
| `discard_pending_trip` | `config_entry_id`, `start_ts`* | Discard a pending trip. |
| `edit_trip` | `config_entry_id`, `erfasst_ts`, `start_ort`*, `end_ort`*, `start_ts`*, `end_ts`*, `km`*, `odo_start`*, `odo_end`*, `soc_start`*, `soc_end`*, `verbrauch_kwh`* | Correct any field of a confirmed trip log entry, including its date/time. Only given fields change. |
| `delete_trip` | `config_entry_id`, `erfasst_ts` | Remove a confirmed trip log entry. **Not reversible.** |
| `export_fahrtenbuch` | `config_entry_id` | Write full trip history as CSV to `www/ev_assistant_fahrtenbuch_<entry_id>.csv`. |
| `import_fahrtenbuch` | `config_entry_id`, `trips` | Bulk-import historical trips from another trip-log app/export (list of `{start, start_ort, ende, ziel_ort, strecke, ...}`), bypassing the odometer detector. Safe to re-run — entries already present are skipped. |
| `simulate_trip` | `config_entry_id`, `km` | Fire a test trip event without a car. |
| `add_ladekarte` | `config_entry_id`, `name`, `monatliche_gebuehr`, `start_datum`, `end_datum`* | Add a new charging card (see [Charging Cards](#charging-cards) below). `monatliche_gebuehr` becomes the card's first fee tier, effective from `start_datum`. |
| `edit_ladekarte` | `config_entry_id`, `karte_id`, `name`*, `monatliche_gebuehr`*, `start_datum`*, `end_datum`* | Correct any field of an existing card. Only given fields change; an empty `end_datum` clears a previously set one (reactivate a cancelled card). `monatliche_gebuehr` corrects only the *earliest* fee tier (e.g. a typo at setup) — for an actual price change, use `add_ladekarte_preisstufe` instead. |
| `delete_ladekarte` | `config_entry_id`, `karte_id` | Remove a charging card. **Not reversible.** Charges already attributed to it keep that (then orphaned) reference — the history itself is untouched. |
| `add_ladekarte_preisstufe` | `config_entry_id`, `karte_id`, `gebuehr`, `ab_datum` | Add a new fee tier to an existing card — e.g. when a reduced introductory price ends and the regular price takes over. Each tier applies from its own date until the next tier's date; order of calls doesn't matter. A tier already existing for that exact date gets its fee replaced instead of duplicated. |
| `delete_ladekarte_preisstufe` | `config_entry_id`, `karte_id`, `ab_datum` | Remove a previously added fee tier. The card's earliest tier can't be removed — a card always needs at least one known fee. |
| `add_maintenance` | `config_entry_id`, `name`*, `preset`*, `km_intervall`*, `zeit_intervall_monate`*, `festes_datum`*, `kosten`*, `last_done_km`*, `last_done_datum`*, `reminder_monate`*, `reminder_km`* | Add a new maintenance item (see [Vehicle Maintenance](#vehicle-maintenance) above). `preset` (`tuev` or `inspektion`) fills `name`/interval defaults as a starting point — any explicitly given field wins. Requires a name (own or from the preset) and at least one due-date criterion (km interval, time interval in months, and/or fixed date) after the preset is applied, otherwise the call is rejected and logged. `reminder_monate`/`reminder_km` optionally override the global "due soon" warning window for just this item (`reminder_monate` is converted to days once at write time — the warning window itself doesn't need calendar precision, unlike the due-date interval). |
| `edit_maintenance` | `config_entry_id`, `wartung_id`, `name`*, `km_intervall`*, `zeit_intervall_monate`*, `festes_datum`*, `kosten`*, `last_done_km`*, `last_done_datum`*, `aktiv`*, `reminder_monate`*, `reminder_km`* | Correct any field of an existing item. Only given fields change; an empty `km_intervall`/`zeit_intervall_monate`/`kosten`/`festes_datum`/`reminder_monate`/`reminder_km` clears that field. Rejected (and rolled back) if it would leave the item with zero due-date criteria — an item always needs at least one (the reminder fields don't count as one). `aktiv: false` pauses the item (excluded from `wartung_faellig`'s count, still shown in the panel). |
| `delete_maintenance` | `config_entry_id`, `wartung_id` | Remove a maintenance item. **Not reversible.** |
| `mark_maintenance_done` | `config_entry_id`, `wartung_id`, `km`*, `datum`* | Record the item as done, resetting its due-date calculation. Defaults to the current odometer reading and today's date if `km`/`datum` aren't given. |

*optional

---

## Examples

**Automation: notify when forced grid charging kicks in.** If you rely on solar and have the [automatic evcc mode/SoC control](#automatic-evcc-mode--soc-control) enabled, this fires whenever the computed mode drops all the way to `now` — the usage profile decided your current battery plus expected solar won't cover the next couple of days, so grid charging is being forced. The exact `entity_id` below depends on your vehicle's device name.

```yaml
automation:
  - alias: "EV Assistant: forced grid charging"
    trigger:
      - platform: state
        entity_id: sensor.your_vehicle_evcc_mode_control
        to: "now"
    action:
      - service: notify.notify
        data:
          title: "EV charging forced from the grid"
          message: >
            evcc mode switched to "now" — {{ state_attr('sensor.your_vehicle_evcc_mode_control', 'rest_heute_kwh') }} kWh still needed today, not enough solar/battery to cover it.
```

**Lovelace: a handful of key sensors on an existing dashboard.** The [sidebar panel](#panel--dashboard) already covers all of this in far more depth — this is just for pinning a few values onto a dashboard you already have. Replace `your_vehicle` with your device's actual entity_id slug.

```yaml
type: entities
title: EV Assistant
entities:
  - entity: sensor.your_vehicle_available_kwh
  - entity: sensor.your_vehicle_usage_profile_tomorrow
  - entity: binary_sensor.your_vehicle_charge_before_solar_recommended
  - entity: sensor.your_vehicle_evcc_mode_control
```

---

## How External Charge Detection Works

EV Assistant needs no GPS, no manufacturer API, and no list of charging stations. The principle in one sentence: **if the battery SoC rises while the home-charging signal is off, the car must be charging elsewhere**.

A small state machine (`engine.py::ChargeDetector`) watches every SoC reading. It tracks the last resting low point ("anchor"). Once SoC has risen ≥ `start_delta` above the anchor *with home-charging off*, a session starts — unless `plug_entity` is configured and confirms the vehicle is unplugged, in which case the rise (e.g. a few points recovered via regenerative braking while driving) just moves the anchor up instead of starting a session, *provided the rise is small enough to plausibly be regen* (under 15 points). A larger rise despite a confirmed unplug is treated as a charge anyway — regenerative braking realistically can't add that much in one gap, so it's almost certainly a charge that happened during a detection gap (e.g. a multi-day loss of connection to the vehicle's telemetry source) rather than actual braking recovery. It ends when the home-charging signal turns on, SoC drops > `drop_ends` below the tracked peak, `idle_timeout_s` passes without a new high, or (if `plug_entity` is configured) a confirmed unplug is detected.

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

## Data Retention

Trip log and external-charge entries accumulate for as long as the integration is set up — potentially years for a leasing contract. To keep Home Assistant's storage file and every scan of that data bounded, entries older than `FAHRTEN_MAX_MONATE`/`HISTORY_MAX_MONATE` (both 24 months by default, `const.py`) are moved daily into a separate archive file — **never deleted**. `export_fahrtenbuch` reads the archive together with the current list, so the CSV export always covers everything; re-running `import_fahrtenbuch` also checks the archive, so it won't create duplicates for already-archived trips.

All totals and averages — savings, €/100 km, total kWh/cost, `equivalent_full_cycles`, the AC/DC and provider breakdowns, and the consumption-by-temperature-band/weekday figures — are computed from running lifetime totals, not from the trip/charge lists directly, so archiving never changes any of them. Only the "recent window" you see via the `fahrtenbuch`/`historie` entity attributes and the panel's history views shrinks over time; the full record stays available through `export_fahrtenbuch`.

---

## Requirements

- **Home Assistant 2024.1** or later
- **evcc** (the add-on/binary itself, reachable over the network) — optional, but required for home charging history and live energy-flow data in the panel. EV Assistant talks to evcc's own REST API directly (`evcc_host` in step 3) — no separate `evcc_intg` HA integration needed.
- Any vehicle with an SoC sensor in HA (WiCAN Pro / MQTT, manufacturer cloud integrations, evcc vehicle sensors, ...)

---

## Testing

**Unit tests (pure logic, `tests/test_engine.py`, no HA needed):**
```bash
python -m pytest tests/test_engine.py -q
```

**HA wiring tests (`tests/ha/`, config flow/coordinator/entry lifecycle — needs `pytest-homeassistant-custom-component`, see `requirements_test.txt`):**
```bash
pip install -r requirements_test.txt
pytest tests -q  # runs both suites together, see tests/ha/conftest.py for how they coexist
```

**End-to-end in HA (no car needed):**
- External charge: call `ev_assistant.simulate_event` with `config_entry_id`, `soc_start: 32`, `soc_end: 74`. Expect a notification and `binary_sensor ... External Charge Detection Open` to turn on. Confirm via the panel.
- Trip: call `ev_assistant.simulate_trip` with `config_entry_id`, `km: 12.5`. Confirm via the panel, then call `export_fahrtenbuch` and verify the CSV in `www/`.

---

## Troubleshooting / FAQ

Enable debug logging for more detail than the panel/sensors show:

```yaml
logger:
  logs:
    custom_components.ev_assistant: debug
```

**Every SoC increase gets detected as an external charge, even when charging at home.** The wallbox charge-power entity (step 3) is missing or not reporting correctly — without it, EV Assistant has no way to tell home charging from external charging. See [Configuration](#configuration), step 3.

**The Usage Profile tab / `usage_profile` sensor stays `unknown` or empty.** It needs at least 7 days of trip-log history before it shows anything, so every weekday has been observed at least once — see [Usage Profile](#usage-profile). Keep confirming (or manually logging) trips and it fills in on its own.

**`evcc_mode_control` sets the charge mode but not min-/target-SoC, or an `evcc_soc_scope_failed` repair issue appears.** evcc couldn't be probed for its SoC scope (loadpoint-level vs. vehicle-level — this varies by evcc version, and the two can even differ from each other, see [Automatic evcc Mode / SoC Control](#automatic-evcc-mode--soc-control)). The mode keeps getting set regardless; only the affected SoC limit is skipped until the next successful probe.

**All the energy estimates look off by a consistent factor.** Double-check the usable battery capacity entered in step 1 — it's the *net* usable kWh your car can actually charge to/from, not the larger gross/factory figure some manufacturers advertise. Every SoC-based kWh estimate in the integration scales directly off this one number.

---

## Contributing

Found a bug or have a feature request? Please [open a GitHub Issue](https://github.com/weskona/ev_assistant/issues) — include your Home Assistant version and, if relevant, a debug log (see Troubleshooting above). Pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) before opening one.

---

## License

MIT — see [LICENSE](LICENSE).

## Credits & Support

Created and maintained by [@weskona](https://github.com/weskona).

The app icon is based on the "ev-station" glyph from Material Design Icons
(https://pictogrammers.com/library/mdi/), © Pictogrammers, licensed under
Apache License 2.0. The glyph was placed on a custom hexagon tile.

Questions or support requests: please use [GitHub Issues](https://github.com/weskona/ev_assistant/issues) rather than direct messages.
