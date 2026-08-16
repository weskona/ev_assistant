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

Setup runs as a 9-step flow (the same flow is used when editing via **Configure**):

| Step | What it configures |
|------|--------------------|
| 1 — Vehicle | Manufacturer + model (required), first registration date, odometer entity, usable battery capacity in kWh (net, not gross), and a starting charge-efficiency value (auto-calibrated later). |
| 2 — Charging Mode | How you charge this vehicle: **Home only**, **Mixed** (default — same as before this step existed), or **Away only**. Purely controls visibility — which of the following steps and which panel tabs/cards appear — never the calculations themselves (a pure external charger is simply the case where the home aggregates are 0). Changeable at any time via **Configure**, without losing any already-entered data: switching to "Away only" just stops showing/actively using the home-related steps/cards, it doesn't delete them; switching back offers them again with whatever was there before. See [Charging Mode](#charging-mode) below. |
| 3 — evcc & Wallbox | Vehicle name in evcc (for home-charging history filter) and the wallbox charge-power entity (used as the home-charging signal — any value > 0.1 kW counts as "charging at home"). **Skipped** in "Away only" mode. |
| 4 — Charge Power | Optional vehicle charge-power sensor (improves external-charge estimates) and wallbox energy meter (cumulative kWh counter for efficiency calibration and home-charging costs). **Skipped** in "Away only" mode. |
| 5 — Notifications | Push target devices (`notify.*` entities, multi-select) and which events trigger a push: external charge detected, SoC threshold reached, trip detected, Tankerkönig unavailable. SoC thresholds (50/60/70/80/90/100%) fire once per charging session — home or external — as the battery crosses them. A persistent HA notification for external-charge/trip/Tankerkönig events always fires regardless of this step. |
| 6 — Detection | Fine-tune the detection state machine: `start_delta` (min SoC rise to trigger), `noise` (jitter tolerance, must be < `start_delta`), `idle_timeout_s` (session-end timeout), `drop_ends` (SoC drop that ends a session immediately). Defaults work for most vehicles. Optional: `plug_entity` (a plug/connectivity `binary_sensor`) and `plug_debounce_s` — when set, a confirmed "plugged in" overrides `idle_timeout_s` entirely (no more false session splits on coarsely-reported SoC), a confirmed "unplugged" (held for `plug_debounce_s`, guarding against brief flaky readings) ends the session immediately, and a *small* SoC rise while confirmed unplugged doesn't start a session at all (avoids misreading a regenerative-braking uptick while driving as an external charge) — an implausibly *large* one (≥15 points, not realistic for regen) starts one anyway, since it's far more likely a charge that was missed during a telemetry gap than actual braking recovery. |
| 7 — Trip Log | Optional: `trip_min_km` (minimum trip distance), `trip_idle_timeout_s` (standstill-to-trip-end timeout), `gps_entity` (person, device_tracker, or sensor entity for location suggestions). Also optional: `motor_entity` (a motor/driving `binary_sensor`, e.g. ignition/"Ready") and `motor_debounce_s` — a second signal for vehicles whose odometer updates too coarsely/infrequently to derive trip start/end from it directly. A confirmed "driving" starts/continues a trip even without a fresh odometer reading; `trip_idle_timeout_s` still tolerates brief stops (e.g. stop-start at a light). Distance always comes from the odometer regardless. A further optional toggle, `trip_auto_confirm`, adds a detected trip to the trip log immediately instead of waiting for manual start/end-location confirmation — location comes from `gps_entity` if configured, otherwise stays empty (editable later via `edit_trip`). One more optional field, `usage_profile_buffer_pct` (default 20), sets the safety margin added on top of the historical weekday average for the Usage Profile tab's "needed tomorrow" figure. A further optional field, `pv_forecast_entity`, points at any sensor entity providing tomorrow's solar-yield forecast (e.g. from Solcast or Forecast.Solar, in kWh or Wh) — with it, the charge recommendation lets tomorrow's expected PV generation cover a shortfall the current battery charge alone wouldn't; without it, the recommendation only compares the current battery charge to tomorrow's typical need. One more optional field, `outside_temp_entity` (a plain temperature sensor or a `weather.*` entity), groups trip consumption into four temperature bands (<0°C, 0–10°C, 10–20°C, >20°C) — once a band has at least 3 trips, `range_estimate` uses that band's average instead of the flat rolling figure, for a more realistic estimate in cold weather. |
| 8 — Leasing | Optional, and only active once **both** `leasing_inkl_km` and `leasing_end_datum` are set: contract starting odometer reading (`leasing_start_km`), contract start/end date, total included mileage, and an optional per-km price for overage (`leasing_preis_mehr_km`) and/or credit for underage (`leasing_preis_minder_km`). Leave it empty and the feature stays fully inactive — no sensor state, no panel content. See [Leasing mileage budget](#leasing-mileage-budget) below. |
| 9 — Cost Comparison | Optional: combustion reference consumption (L/100 km), fuel price, home electricity price. Fuel price priority: Tankerkönig auto-detection (pick a fuel type, cheapest open station wins) > live entity > fixed value. Home electricity price: live entity (kWh-weighted average) > fixed value. Also optional: `co2_per_kwh_g` (grid CO2 intensity, g/kWh, default 380 — a rough German-grid-average estimate, adjust for your own supplier/tariff) for the CO2 comparison sensor. |

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
| `last_cost` | External Charge Cost (last) | Cost of the most recently confirmed charge (kWh × price, plus any `start_fee`/`block_fee`/`time_fee`). |
| `last_price` | External Charge Price (last) | Price per kWh entered for the most recent charge. |
| `last_duration` | External Charge Duration (last) | Duration of the detected session in minutes. |
| `last_charge_power` | External Charge Avg Power (last) | Average charge power (kW) of the most recently confirmed charge, from kWh ÷ duration. Sessions < 5 min or with implausible power (< 1 kW or > 350 kW) return `unknown`. |
| `total_kwh` | External Charge kWh (total) | Running total of all confirmed external-charge kWh (`state_class: total_increasing`). |
| `total_cost` | External Charge Cost (total) | Running total of all confirmed external-charge costs. |
| `count` | External Charge Count | Total number of confirmed external charges. |

### Home Charging

| Key | Name | Description |
|-----|------|-------------|
| `home_kwh` | Home Charging kWh (total) | Total kWh charged at home — full evcc cumulative history. Prefers evcc's own per-vehicle session data, then evcc's site-wide "total charged energy" statistic (only if a wallbox meter is also configured for this vehicle — that statistic isn't per-vehicle), then falls back to the wallbox energy meter delta since ev_assistant setup. `unknown` without a configured meter. Attributes (only if evcc exposes `session_energy`/`session_solar_percentage`/`session_price` for your setup, step 2): `evcc_solaranteil_pct` (kWh-weighted solar share across your evcc-controlled home sessions), `evcc_kosten_gesamt` (summed session cost — evcc's own per-session total, not a per-kWh rate), `evcc_preis_je_kwh` (derived from the two). External charges and sessions evcc didn't expose data for simply don't contribute — no zeros, no guessing. |
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
| `last_trip_km` | Trip km (last) | Distance of the most recently confirmed trip. Attribute `fahrtenbuch` contains the full trip history list. Entries without a directly-reported consumption get their `verbrauch_kwh` estimated from the SoC drop during the trip; if that estimate falls outside a plausible ~8–40 kWh/100 km band (trips under 5 km are exempt), the entry is marked `verbrauch_unsicher: true` — shown with a ⚠️ in the panel — since a vehicle connectivity gap during the trip can freeze the SoC reading and badly skew the estimate. Cleared once a real value is entered via `edit_trip`. |
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
| `charging_location_breakdown` | Charging Location Breakdown | "Where does your charging come from" — state is home's share of total kWh. Attributes: `heim`/`fremd`, each with `kwh`, `kosten`, `kwh_anteil_pct`, `kosten_anteil_pct`, `preis_je_kwh` (only present once that location has a known, non-zero value); `heim` additionally gets `solar_pct` if evcc provides it (see `home_kwh` above). Top-level `eur_je_100km` is the vehicle-wide total cost ÷ km driven — deliberately **not** split per location, since you drive on a mix of both and kilometers can't be attributed to one charging source. Also `ac_dc` (only present with at least one classifiable external charge): `ac`/`dc` sub-breakdown of *external* charging only (home charging is practically always AC by construction), each with the same `kwh`/`kosten`/`anzahl`/`kwh_anteil_pct`/`kosten_anteil_pct`/`preis_je_kwh` shape — see `ac_charging_kwh`/`dc_charging_kwh` below for the classification method. Pure consolidation of numbers computed elsewhere — no new pricing/PV logic. `unknown` without any known charging at all. |
| `ac_charging_kwh` / `dc_charging_kwh` | External Charging AC/DC | kWh of external charging classified as AC/DC, derived from average power per charge (kWh ÷ duration) against a 22 kW threshold — there's no direct AC/DC signal anywhere in the data, 3-phase AC charging realistically can't exceed that. Charges missing kWh or duration (e.g. a fully manual entry without an end time) are excluded rather than guessed. `state_class: total` (can decrease if a charge is later edited/deleted). Attributes: `kosten`, `anzahl`, `kwh_anteil_pct`, `kosten_anteil_pct`, `preis_je_kwh` — same detail as the `ac`/`dc` sub-breakdown on `charging_location_breakdown` above, kept here too for direct dashboard/automation use without an attribute template. `unknown` without any classifiable charge in that category. |
| `co2_savings` | CO2 Savings vs. ICE Vehicle | Estimated CO2 saved vs. the combustion reference over km driven since setup: (combustion fuel use × its CO2 factor) − (EV kWh used × `co2_per_kwh_g`). Same energy balance as `vehicle_avg_consumption`. `unknown` until odometer and combustion consumption are configured. Attributes: `co2_ev_kg`, `co2_verbrenner_kg`, `co2_ersparnis_kg`. |
| `home_vs_external_price` | External vs. Home Charging Price Difference | Weighted average price paid for external charging minus the home electricity price (both €/kWh, since setup). Positive means external charging cost more per kWh — the usual case. `unknown` without a home electricity price or before any external charge is confirmed. Attributes: `heimladen_preis_kwh`, `fremdladen_preis_kwh`, `differenz_kwh`. |
| `cost_day` / `cost_week` / `cost_month` / `cost_year` | Cost (Today/Week/Month/Year) | Combined home + external charging cost within the current calendar period, same rollover pattern as the driven-km period sensors below. `unknown` before the period's baseline is established (right after setup); clamped to 0 rather than going negative if the total dips below the period baseline (e.g. the home-cost estimate's weighted-average price ticking down as a cheaper session is folded in). |
| `erstzulassung` | First Registration | First-registration date from step 1, exposed as a `date`-typed sensor. Diagnostic. |

### Leasing Mileage Budget

Purely additive — configure step 7 (`leasing_inkl_km` and `leasing_end_datum` both set) to activate; otherwise this sensor stays `unknown` and the Leasing panel tab shows a setup hint instead of any content.

| Key | Name | Description |
|-----|------|-------------|
| `leasing_km_vor_ruecklauf` | Kilometerbudget vor Rücklauf | How far ahead of (positive) or behind (negative) the straight-line contract plan you are, in km, against the contract's own starting odometer reading (`leasing_start_km`) — deliberately **not** the same "km driven" figure used by the sensors above, which only counts since this integration was set up. Attributes: the raw contract inputs echoed back for display (`vertrag_start_km`, `vertrag_start_datum`, `vertrag_end_datum`, `vertrag_inkl_km`, and `preis_mehr_km`/`preis_minder_km` if configured), `gefahrene_vertrags_km`, `resterlaubte_km` (kilometers still allowed until contract end, regardless of days remaining), `vertrag_tage`/`vergangene_tage`/`verbleibende_tage`, `soll_km_bis_heute` (target-to-date), `status` (`im_budget` / `knapp` / `ueber`, based on the linear projection with a small tolerance), `verbleibendes_tagesbudget_km` (only while contract days remain). Two independent end-of-contract projections, each present only when computable: `linear` (straight-line from the contract start — the stable reference) and `rollierend` (from your last 30 driving days — reacts faster to a recent change in habits), both with `tempo_km_pro_tag`, `erwartete_end_km`, `erwartete_mehr_bzw_minder_km`, and — only if the matching price is configured — `mehrkosten_eur` (overage) or `gutschrift_eur` (underage credit, only ever shown if `leasing_preis_minder_km` is set; most contracts don't refund unused km). |

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

EV Assistant registers a **sidebar panel** automatically — no extra setup beyond the integration itself. If you have more than one vehicle (i.e. more than one EV Assistant integration instance), a vehicle switcher appears in its own row above the tab bar; every tab shows the currently selected vehicle's data. With only one vehicle configured, the switcher is hidden entirely.

### Overview tab

Live energy-flow diagram showing current PV, grid, home, battery, and wallbox power. Displays the active charging session (mode, SOC, session energy, solar share, tariff) and any pending charges or trips waiting for confirmation. The SOC bar ("Fahrzeug-Akku") reads from the `soc_entity` configured in step 1, falling back to the evcc vehicle SOC if no `soc_entity` is set.

In **Away only** [charging mode](#charging-mode), this tab looks different: instead of the flow diagram and home/evcc cards, it shows spending over time (day/week/month/year), total kWh/cost/count, EUR/100 km, and the combustion-vehicle cost/CO2 comparison — the cards that are actually relevant without any home charging. In **Home only**/**Mixed** mode (the default, and how it's always worked), this tab is unchanged.

### Vehicle tab

Per-vehicle dashboard in a three-column layout:

| Column | Content |
|--------|---------|
| **Home Charging** | Home charging totals (kWh, EUR, session count, avg. solar share), last session KPIs, full evcc session history. Each entry shows SOC start→end, kWh, Ø charge power, EUR/kWh, cost, solar share, duration, and a SOC bar. |
| **External Charging** | External charge totals, last session KPIs, editable history. Each entry shows kWh, Ø charge power, cost, and a SOC bar; a `start_fee`, `block_fee`, and/or `time_fee` each show as their own separate line next to the price — some receipts list several at once (e.g. a flat start fee plus a blocking fee for overstaying after charging finished, or a time-based fee some fast-charging networks bill instead of/alongside kWh). A "Log manually" button next to the history heading opens a form to add a charge without any prior detection — start/end time, kWh, price, SoC start/end, and the optional fees. |
| **Trip Log** | Trip totals, last trip KPIs (km, route), editable trip history. Each entry with a known consumption shows both the trip's total kWh and its kWh/100km rate side by side, to avoid misreading the absolute figure as a rate. |

### Usage Profile tab

Answers "do I need to charge tonight, or can charging wait for tomorrow's solar surplus?" from your own driving history — no manual input needed. A bar chart shows the average kWh consumed per weekday (Mon–Sun), derived from the trip log: for each weekday, total kWh used on that weekday ÷ number of that weekday that have elapsed since your first logged trip (days without a trip still count as 0 kWh, so "rarely drives on Sundays" correctly pulls the Sunday average down instead of being ignored). Requires at least 7 days of trip-log history before it shows anything (see `usage_profile` below); today's and tomorrow's bars are highlighted. Below the chart: currently available battery kWh (from SoC × usable capacity), tomorrow's typical need plus your configured buffer, and a plain-language recommendation. If `pv_forecast_entity` is configured (see step 6), tomorrow's forecasted PV yield is also shown and factored into the recommendation — a shortfall the battery alone can't cover may still not need a grid charge if enough solar is expected tomorrow.

### Analyse tab

Longer-term signals that don't belong on the day-to-day vehicle card: the measured battery capacity trend and equivalent full cycles (see `battery_capacity`/`equivalent_full_cycles` above), the charging location breakdown (home vs. external — kWh, cost, share, price/kWh, home's solar share, and a vehicle-wide EUR/100km, see `charging_location_breakdown` above) including an AC/DC sub-breakdown of external charging once at least one charge can be classified, and — if `outside_temp_entity` is configured (step 6) — a bar chart of average consumption per temperature band, with the current outside temperature and its active band shown alongside.

**Vehicle card** (above the three columns): vehicle name, current SOC with colour-coded bar (red < 20 %, orange < 40 %, green otherwise), odometer, average consumption (kWh/100 km, from the overall energy balance — total charged kWh since setup ÷ km driven since setup), and charge efficiency. Below that, three columns: a compact km grid (driven km today/week/month/year on the left, rolling averages and projections on the right), a Cost column (combined home + external charging cost today/week/month/year, from the `cost_day`/`cost_week`/`cost_month`/`cost_year` sensors), and the ICE Comparison section (savings, EV cost, estimated combustion cost, cost per 100 km).

**Bar charts**: charging overview, cost overview, and solar share — switchable between week / month / year view with prev/next navigation. Hover over any bar to see its value in a tooltip (replacing the per-bar labels that overlapped in monthly view). Mobile-responsive: on screens ≤ 600 px the three charts stack vertically.

**Number formatting**: all values in the panel respect the HA locale setting (`Settings → Profile → Number format`) — no manual configuration needed.

### Leasing tab

Only shows content once the Leasing step is configured (see `leasing_km_vor_ruecklauf` above) — otherwise a plain "set this up in options" hint instead of empty cards. Shows the contract's start/end date, elapsed vs. remaining days, kilometers driven since contract start vs. the target-to-date, and kilometers still allowed until contract end, plus — if configured — the per-km overage/underage price. A progress bar shows the actual odometer progress against the total included mileage, with a marker for where the linear plan says you should be today. Below that, the linear and rolling projections side by side (Ø km/day, expected end-odometer, projected over/under-km, and — only if configured — the €-estimate), and the remaining daily budget. Missing values (e.g. no rolling pace yet, no price configured for a credit) are hidden rather than shown as 0 or "n/a".

---

## Services

All services require `config_entry_id` to target a specific vehicle when multiple entries are configured.

| Service | Parameters | Description |
|---------|-----------|-------------|
| `log_charge` | `config_entry_id`, `kwh`, `price_kwh`, `start_ts`*, `end_ts`*, `soc_start`*, `soc_end`*, `start_fee`*, `block_fee`*, `time_fee`* | Confirm a pending external charge with receipt values, or — if none is pending — log a completely standalone entry (same as the panel's "Log manually" button in the External Charging card). `start_ts` selects which pending charge (oldest if omitted); for a standalone entry it's the charge's start time. `end_ts`/`soc_start`/`soc_end` only take effect for a standalone entry (a confirmed pending charge keeps its own measured duration/SoC): `end_ts` combines with `start_ts` into the session duration, `soc_start`/`soc_end` combine into `delta_soc`. `start_fee`/`block_fee`/`time_fee` are optional flat fees some networks/chargers add on top of the kWh price (a start fee, a blocking fee for overstaying, and a time-based fee for charging duration) — kept as separate fields since a receipt can list several at once, default 0 each. |
| `discard_pending` | `config_entry_id`, `start_ts`* | Discard a pending external charge (false positive). |
| `edit_charge` | `config_entry_id`, `erfasst_ts`, `kwh`*, `price_kwh`*, `start_fee`*, `block_fee`*, `time_fee`*, `start_ts`*, `end_ts`*, `soc_start`*, `soc_end`* | Correct any field of an already-confirmed history entry, same "only given fields change" model as `edit_trip`. Running totals adjust by the difference when kWh/price/fees change; `soc_start`/`soc_end` changes recompute the SoC delta; `end_ts` is converted to a duration together with the (new or existing) `start_ts`. |
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
