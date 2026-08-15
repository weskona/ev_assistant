# Changelog

All notable changes to the EV Assistant integration. Format inspired by [Keep a Changelog](https://keepachangelog.com/), versioning in `manifest.json`.

## [0.58.0] - 2026-08-15

### Changed

- **Trip history now shows kWh/100km alongside the absolute kWh figure**. Each trip in the trip log only showed its total consumption for that trip (e.g. "4.0 kWh" for a 25 km trip) with nothing indicating it wasn't a per-100km rate — easy to misread as one. Now both numbers are shown side by side (here: "4.0 kWh" and "16.0 kWh/100km").

## [0.57.1] - 2026-08-15

### Fixed

- **Push/email notifications for external-charge and trip detection weren't arriving at all** — neither the mobile push nor the email. `notify.send_message`'s current schema only accepts `message`/`title`; the extra `data` payload these two notification types sent (an actionable "Enter" button, a tag, `persistent: true`) is no longer accepted at all, and made the *entire* service call fail with a 400 before it reached any target. SoC-threshold and leasing-budget notifications were unaffected since they never sent `data`. The action button and tag-based replacement/grouping for these two notification types are gone as a result — the persistent in-HA notification (Settings → Notifications) still carries the same information and is unaffected.

## [0.57.0] - 2026-08-15

### Changed

- **Global vehicle switcher for multi-vehicle setups**. If you have more than one vehicle configured, the picker to switch between them used to live only inside the "Fahrzeug" tab, even though it silently affected every other tab (Übersicht, Nutzungsprofil, Analyse, Leasing) too — there was just no visible way to change vehicles from those tabs. It's now its own row above the tab bar, always visible, and switching vehicles now fully rebuilds whichever tab you're currently looking at instead of only the "Fahrzeug" tab. Renamed that tab from "Fahrzeuge" to "Fahrzeug" (singular) to match — it shows one vehicle's details, the switcher (not the tab) is what handles multiple. With only one vehicle configured, nothing changes: no switcher row, no extra space, panel looks exactly as before.

### Fixed

- **Config flow could fail on a brand-new vehicle at the notifications step.** `DEFAULT_NOTIFY_EVENTS`/`DEFAULT_SOC_THRESHOLDS` were tuples (intentionally, to avoid a shared mutable default across config entries), but the multi-select fields backing them require a list, and reject a tuple outright — surfaced while testing the vehicle switcher above with a freshly added second vehicle. In practice this never affected the real setup wizard in a browser (the form always submits an explicit list, even for pre-checked defaults), only a fully scripted/automated flow submission — but it's now fixed regardless.

## [0.56.0] - 2026-08-15

### Changed

- **Leasing tab: more context, clearer labels**. Live testing of 0.55.0's leasing tracker showed the tab wasn't self-explanatory enough on its own, so it now also shows: the contract's start/end date and how many days have elapsed vs. remain, the odometer reading at contract start, the total included mileage, kilometers driven since contract start, the target-to-date, kilometers still allowed until contract end, and — if configured — the per-km overage price and/or underage credit price. The ambiguous "Tempo" label is now "Ø km/Tag", and the two projection columns are labeled "Linear — Ø seit Vertragsbeginn" / "Rollierend — Ø letzte 30 Fahrtage" instead of the previous shorthand. The progress bar now shows the actual odometer progress against the total included mileage (e.g. "235 von 700 km, 33.6 %") with a marker for where the linear plan says you should be today, instead of an abstract pace percentage.
- `sensor.<vehicle>_kilometerbudget_vor_rucklauf` now also exposes the raw contract inputs as attributes (`vertrag_start_km`, `vertrag_start_datum`, `vertrag_end_datum`, `vertrag_inkl_km`, `preis_mehr_km`/`preis_minder_km` if set) and a new `resterlaubte_km` (kilometers still allowed until contract end, independent of remaining days) — so the panel (and anything else reading the sensor) doesn't need to look up the config separately.

## [0.55.0] - 2026-08-15

### Added

- **Leasing mileage budget tracker**: new optional setup step ("Leasing-Kilometerbudget") lets you enter your contract's starting odometer reading, start/end date, included total mileage, and (optionally) a per-km price for overage and/or credit for underage. Purely additive — leave it empty and nothing changes: no new sensor state, no panel content. Once configured, a new `sensor.<vehicle>_kilometerbudget_vor_rucklauf` reports how far you are ahead of or behind the straight-line plan (`km_vor_ruecklauf`), with the full breakdown as attributes: km driven under the contract (against the contract's own starting odometer — deliberately **not** the same "km driven" figure used elsewhere, which only counts since this integration was set up), the target-to-date, two independent end-of-contract projections (linear from the contract start, and rolling from your last 30 driving days), the projected over/under-mileage and €-estimate for each, remaining daily budget, and a status (`im_budget` / `knapp` / `ueber`).
- **New "Leasing" panel tab**: Soll/Ist bar plus both projections side by side. Shows a plain "set this up in options" hint instead of empty cards until the feature is configured; missing values (e.g. no rolling pace yet, no price configured) are hidden rather than shown as 0 or "n/a".
- **Optional push notification** (`leasing`, not enabled by default — opt in via the notify-events step) when the linear projection first crosses into "knapp" or "ueber", with hysteresis so a projection hovering near the line doesn't re-notify on every update; a contract identity change (different start-km/end-date) resets the notification state.

**Limits, on purpose**: both projections are estimates, not guarantees — linear smooths over your whole contract to date, rolling reacts faster to a recent change in driving habits but overreacts to short blips; the status/notification threshold is based on the linear projection only. An under-mileage credit only ever shows up if you've entered a price for it — many leasing contracts simply don't refund unused kilometers, and the tracker doesn't assume one where you haven't said so. Everything is km-based against the same odometer entity as the rest of the integration; if your odometer reports in miles, the existing mi→km conversion applies, but the contract fields themselves are entered in your odometer's unit.

## [0.54.0] - 2026-08-14

### Added

- **"So verteilt sich deine Ladung" — charging location breakdown**: new `sensor.<vehicle>_ladeort_aufschlusselung` (state: home's share of total kWh) with the full split as attributes — kWh, cost, share (%), and price/kWh for home and external charging separately, home's solar share (evcc-sourced, see 0.53.0), and a vehicle-wide EUR/100km figure. No new pricing/PV/tariff logic — this purely consolidates numbers `home_kwh`/`home_cost`/the confirmed external-charge totals already compute elsewhere. Shown on the Analyse tab. **Limits, on purpose**: solar share only covers home charging evcc actually controlled (external charging never has a solar share); EUR/100km is deliberately vehicle-wide, never per location — you drive on a mix of both, so kilometers can't be attributed to one charging source; home cost is only as accurate as evcc's own data (or the configured home price as a fallback).

## [0.53.0] - 2026-08-14

### Added

- **evcc-sourced solar share and cost for home charging**: `home_kwh` now carries `evcc_solaranteil_pct` (kWh-weighted solar share), `evcc_kosten_gesamt` (summed session cost), and `evcc_preis_je_kwh` (derived from the two) as attributes, sourced from evcc's own per-session `session_energy`/`session_solar_percentage`/`session_price` entities (configured in step 2, if evcc exposes them for your setup). No pricing/tariff/PV logic of our own — we only read what evcc already computed. **Only covers home charging that evcc actually controlled**: external charges never populate these fields, and a session without a matching evcc entity (or one evcc doesn't expose for your setup) simply doesn't contribute — no zeros, no guessing. Session cost is evcc's `sessionPrice` (verified against evcc_intg's own source: a separate `sessionPricePerKWh` field exists for the per-kWh price, so this one is treated as a session total and summed, not multiplied by kWh).

## [0.52.0] - 2026-08-14

### Added

- **Equivalent full cycles sensor**: new `sensor.<vehicle>_aquivalente_vollzyklen`, summing SoC throughput from your trip log (discharge) and both external and home charging (charge) into a single "equivalent full cycles" count (0%→100%→0% counts as 1 cycle) — the complement to `battery_capacity`, since real battery warranties are usually specified in both cycles and years. Shown on the Analyse tab next to battery capacity.

## [0.51.0] - 2026-08-13

### Added

- **Temperature-aware range estimate**: an optional `outside_temp_entity` (step 6 — Trip Log; accepts a plain temperature sensor or a `weather.*` entity) groups your trip consumption into four bands (<0°C, 0–10°C, 10–20°C, >20°C). Once a band has at least 3 trips, `range_estimate` uses that band's average instead of the flat rolling 30-day figure — the current temperature, its consumption band, and the full per-band breakdown are exposed as attributes (`aussentemperatur`, `temperaturband_aktuell`, `verbrauch_nach_temperatur`).
- **New "Analyse" panel tab**: the measured battery capacity sensor (moved off the vehicle card) and the new temperature/consumption breakdown now live on their own tab, keeping the main vehicle card focused on day-to-day numbers.

## [0.50.0] - 2026-08-13

### Added

- **Measured battery capacity sensor**: new `sensor.<vehicle>_batteriekapazitat_gemessen`, a rolling average of implied battery capacity derived from your own charging history — from external charges with a wide SoC swing (≥20 percentage points), and from home charging sessions once a measured charge efficiency is available. The absolute value typically runs above the vehicle's real usable capacity (charging losses aren't modeled — there's no independent second measurement to calibrate them out, unlike AC efficiency for home sessions), so it's not meant to be compared 1:1 against a spec sheet; a decline over months/years is the actual aging signal to watch, not the single current value. Requires at least 2 qualifying sessions before showing anything.

## [0.49.0] - 2026-08-11

### Added

- **Estimated range sensor**: new `sensor.<vehicle>_geschatzte_reichweite`, calculated from the current SoC and your actual rolling 30-day consumption (falls back to the lifetime average until 30 days/50 km of trip history are available) instead of a generic manufacturer figure. Shown alongside CO₂ savings on the vehicle card in the panel.
- **Plausibility flag for SoC-delta-estimated trip consumption**: when a trip has no directly-reported consumption, it's estimated from the SoC drop during the trip — but that estimate is only as good as the SoC readings at trip start/end, and a temporary vehicle connectivity gap can freeze one of them at trip start or end, producing a wildly wrong number. Trips whose resulting estimate falls outside a plausible ~8–40 kWh/100km band (trips under 5 km are exempt — whole-percent SoC quantization alone distorts the ratio at that distance) are now marked `verbrauch_unsicher` and shown with a ⚠️ in the panel's trip history, instead of being displayed as if certain. Manually entering a real consumption value (e.g. from the vehicle's app) always clears the flag.

### Fixed

- **The estimated range sensor (and other live-SoC-dependent values) could show a stale reading**: the coordinator only pushed an update to entities after a charge event fully finished, not on every routine SoC sample — so a value depending directly on the *current* SoC (rather than an accumulated total) could lag behind the real state by a long margin. Routine detection runs now always push the update.

## [0.48.0] - 2026-08-11

### Added

- **Repair issues for stuck source entities**: if a configured source entity (vehicle SOC, odometer, plug/motor sensor, wallbox charge power, vehicle charge power, wallbox energy meter, location suggestion, home electricity/fuel price) is unavailable, unknown, or removed for at least 30 minutes, a Repair issue now appears (Settings → System → Repairs) explaining exactly what's affected, instead of the integration silently continuing to compute estimates from stale data. Clears automatically once the entity recovers.
- **Duplicate-vehicle protection**: adding a vehicle now sets a unique ID from its SoC entity, so accidentally configuring the same vehicle twice is rejected with a clear message. Existing installs are migrated automatically (no action needed).
- Set up [ruff](https://docs.astral.sh/ruff/) linting (`pyproject.toml`) and added it as a third CI check alongside HACS and hassfest validation.

### Fixed

- **Two test functions silently never ran**: `test_get_state_load_state_ueberlebt_simulierten_neustart` and `test_load_state_ohne_gespeicherten_zustand_ist_no_op` each existed twice (once for `ChargeDetector`, once for `TripDetector`) — Python silently keeps only the last definition of a duplicate top-level function name, so the `ChargeDetector` versions were replaced by the `TripDetector` versions and never executed. Found by the new ruff CI check. Renamed so both run; both pass.
- `zip()` without `strict=True` in the Tankerkönig price-averaging loop (harmless in practice since both lists are always the same length by construction, but now explicit).
- `async_unload_entry` used `.pop(entry.entry_id)` without a default, which would raise `KeyError` instead of failing gracefully in the unlikely case it's called for an entry that never finished setup.

## [0.47.0] - 2026-08-11

### Added

- **Diagnostics support**: Settings → Devices & Services → EV Assistant → ⋮ → Download Diagnostics now works. Includes the full config and coordinator state for troubleshooting; trip-log locations (`start_ort`/`end_ort`/`trip_start_zone`) are redacted, and the trip/charge history is capped to the newest 20 entries (with a total count alongside) to keep the file a reasonable size.
- CI now also runs [hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest/) validation on every push/PR, in addition to the existing HACS validation.

### Fixed

- **A HA crash exactly in the few seconds after a trip started could lose the trip's start location/SoC** (introduced in 0.44.0's delayed-write change): the routine per-sample trip-detector save was batched, but freezing the start location suggestion and start SoC at the idle→driving transition needs to save immediately — losing it would silently attribute the *previous* trip's start location/SoC to this one once it's confirmed. Now saves immediately at that specific moment; the routine per-sample mirror in between stays batched.
- `manifest.json`: declared `http`/`recorder` as `after_dependencies` (used defensively for the sidebar panel and long-term-statistics queries; hassfest was flagging their absence) and sorted manifest keys alphabetically as hassfest requires.

## [0.46.0] - 2026-08-10

### Fixed

- **A pending batched write (from 0.44.0's delayed-save change) could be lost on a config entry reload**: Home Assistant's own delayed-save protection only flushes on a full HA shutdown, not when a single entry is unloaded/reloaded — which happens on every Configure/Reconfigure. `async_shutdown()` now explicitly flushes any pending write first, so a reconfigure right after a routine sensor update (SoC/odometer/wallbox-energy) can no longer drop it.

## [0.45.0] - 2026-08-10

### Changed

- **Trip-log aggregate calculations (average consumption, daily kWh, weekday usage profile) are now cached instead of recomputed from the full trip log on every single coordinator update** (every SoC/odometer/wallbox-energy sample) — since the trip log has grown unbounded and without a size cap since 0.20.1, this was doing full-list work far more often than needed. Results are now cached and only recomputed when a trip is actually added, edited, deleted, or imported (or, for the usage profile, once per calendar day). No behavior change for users — trip log entries are still kept indefinitely, nothing is capped or dropped.
- Removed the unused `HISTORY_MAX` constant, a leftover from before 0.20.1 removed the (now long-gone) 100-entry history cap.

## [0.44.0] - 2026-08-10

### Fixed

- **SoC threshold notifications (added in 0.43.0) fired retroactively for every already-passed threshold at the start of a charging session**: e.g. plugging in at 85% with thresholds at 50/60/70/80/90/100% immediately notified for 50/60/70/80% at once, even though those had been reached in a previous session, not just now. Thresholds already at or below the current SoC when a session starts are now silently seeded as "already notified" instead — only thresholds actually crossed after that point fire a notification.
- **Bulk trip import (`import_fahrtenbuch`) could give multiple imported trips the same `erfasst_ts`**, since it read `int(time.time())` fresh in a tight loop with no delay between rows — `erfasst_ts` is the sole lookup key for `edit_trip`/`delete_trip`, so editing/deleting one imported trip could silently affect a different one. Each imported row now gets a unique offset from a single base timestamp.
- **Auto-discovered evcc entities (PV power, grid power, session data, etc.) were never removed from the stored configuration once evcc stopped reporting them** (e.g. after renaming/removing a loadpoint in evcc) — they'd persist as stale, dead entity references indefinitely. Reconfigure now drops any previously-discovered evcc key that isn't found again this run, as long as evcc discovery found at least one entity (so a temporary evcc outage doesn't wipe everything).
- **Five statistics sensors used the wrong state class for values that can decrease**: `total_kwh`, `total_cost`, `count`, `trip_count`, and `total_trip_km` were `total_increasing`, but `edit_charge`/`delete_charge`/`edit_trip`/`delete_trip` can lower their backing totals — Home Assistant's recorder treats a decrease on a `total_increasing` sensor as a meter reset, which can corrupt long-term statistics. Changed to `total` (no reset semantics). The two sensors that mirror genuinely monotonic physical counters (odometer, raw wallbox energy meter) were left unchanged.
- **The "external charge open"/"trip open" binary sensors could miss UI updates** when only the open count changed (e.g. 1 → 2 simultaneously open external charges) without the on/off state itself changing — added `force_update`, matching the existing fix on the sibling `pending_estimate` sensor.
- **A brief odometer sensor glitch while parked (e.g. briefly reporting 0) could corrupt the next trip's distance**: `TripDetector` tracked the resting-position anchor without a floor while idle, unlike the guard already in place while driving. The anchor can no longer drop below the last confirmed odometer value.
- **`noise` could be configured `>=` `start_delta`**, silently breaking charge detection (every reading would look like a charge start) despite the setup text saying it must always be smaller. Now validated on save, with a clear error instead of a silent footgun.

### Changed

- **Persistence writes are now batched for frequent, non-critical state** (sensor mirror values, plug/motor debounce state, daily rollovers, price-averaging bookkeeping, the routine per-sample detector snapshots) using a 10s delayed write instead of writing to disk immediately on every single update — previously every SoC/odometer/wallbox-energy sample triggered an immediate synchronous save. Actually important events (new/edited/deleted charges and trips, pending confirmations, imports) still save immediately; Home Assistant still flushes pending writes on an orderly shutdown.

## [0.43.0] - 2026-08-10

### Fixed

- **Clearing an optional entity field via Configure (e.g. vehicle charge-power or wallbox energy meter) didn't actually remove it**: the options flow only ever wrote the new values into the config entry's `options`, while every read site falls back to `options.get(key) or data.get(key)` — so a field cleared in the form correctly disappeared from `options`, but the original value set during initial setup remained in `data` and kept being used regardless. The options flow now writes the fully-resolved configuration directly into `data` (fields outside the 7-step forms, e.g. legacy template overrides, are preserved untouched) and clears `options`, so a cleared field is actually gone afterwards.

### Added

- **Reworked notifications (step 4, "Notifications")**: the old free-text `notify_service` field is replaced by `notify_entities`, a multi-select picker for one or more modern `notify.*` target devices (phone, tablet, email, ...), sent via the unified `notify.send_message` service instead of the legacy per-service `notify.<name>` call. A new `notify_events` multi-select chooses which events additionally push to those devices — external charge detected (the previous, now-optional default), SoC threshold reached, trip detected, Tankerkönig unavailable. The persistent HA notification for external-charge/trip/Tankerkönig events keeps appearing automatically regardless of this selection.
- **SoC threshold notifications**: a new `soc_thresholds` multi-select (50/60/70/80/90/100%) fires a notification once per threshold as the battery crosses it during any charging session in progress — home or external. The set of already-notified thresholds is persisted and resets once the session ends, so a restart mid-session doesn't cause repeats and a new session re-arms all thresholds.

### Changed

- Expanded the config-flow help text for `power_is_ac`, the wallbox charge-power entity (step 2), and the wallbox energy meter (step 3) to explain exactly when each setting has an effect (only with a vehicle charge-power sensor configured; only a home-charging on/off signal, never an energy value; only evaluated during home charging for efficiency calibration and price weighting).

## [0.42.0] - 2026-08-08

### Fixed

- **A brief regenerative-braking SoC uptick while driving (unplugged) could be misdetected as the start of an external charge**: the charge detector only checked the confirmed plug state (`plug_entity`) when deciding whether to *end* a session, not when deciding whether to *start* one — so a few percentage points of recovered SoC from regen braking, with no external charger involved at all, could kick off a spurious "Fremdladung". With a `plug_entity` configured, a SoC rise now only starts a new detection while the vehicle is confirmed plugged in; a rise while confirmed unplugged just moves the internal reference point forward instead (so the same recovered SoC isn't re-evaluated on the next reading). Setups without `plug_entity` configured are unaffected — SoC rises still start detection as before.

## [0.41.0] - 2026-08-06

### Added

- **Cost column in the vehicle card**: a new column between the km grid and the ICE comparison shows combined home + external charging cost for today/week/month/year, from the existing `cost_day`/`cost_week`/`cost_month`/`cost_year` sensors (introduced in 0.36.0, not previously surfaced in the panel).

## [0.40.0] - 2026-08-06

### Changed

- **`edit_charge` now supports correcting any field of an external-charge history entry, not just kWh/price**: `kwh`/`price_kwh` are now optional (only given fields change, same model as `edit_trip`), and new optional fields `start_ts`, `end_ts`, `soc_start`, `soc_end` were added. `kosten` is always re-derived from the effective kWh/price/fee; `soc_start`/`soc_end` changes recompute `delta_soc`; `end_ts` is converted to `dauer_min` together with the effective `start_ts`. The panel's history edit form gained matching Start/End/SoC fields.

## [0.39.0] - 2026-08-06

### Added

- **External charging start/blocking fee**: new optional `start_fee` field on `log_charge` and `edit_charge` — some charging networks/points bill a flat fee on top of the kWh price (e.g. a start or blocking fee). New `engine.charge_cost()` adds it to the stored cost; entries carry a `startgebuehr` value (0 for older entries or when none is entered). The panel's pending-charge confirmation form and history edit form both gained an optional "Startgebühr" input; history entries with a fee show it as a separate line next to the price.

## [0.38.0] - 2026-08-06

### Added

- **Usage Profile PV forecast**: new optional config field `pv_forecast_entity` (step 6) — point it at any sensor entity providing tomorrow's solar-yield forecast (e.g. Solcast's "Forecast Tomorrow" or Forecast.Solar's "Estimated Energy Production - Tomorrow"; kWh or Wh, auto-converted). With it configured, `Charge Before Solar Recommended` lets tomorrow's expected PV generation cover a shortfall the current battery charge alone can't, instead of only comparing the battery charge to tomorrow's typical need. New `pv_prognose_morgen_kwh` attribute on the binary sensor; shown as an extra KPI in the "Usage Profile" panel tab when configured. Without this field, behavior is unchanged from 0.37.0.

## [0.37.0] - 2026-08-06

### Added

- **Usage Profile**: a new `weekday_usage_profile()` calculation buckets the trip log's kWh consumption by weekday and averages it over how often that weekday has occurred since your first logged trip, answering "do I need to charge tonight, or can charging wait for tomorrow's solar surplus?" purely from your own driving history. New sensors `Usage Profile` (today's weekday average, with all 7 weekday averages as attributes) and `Usage Profile (Needed Tomorrow)` (tomorrow's average plus a configurable safety buffer), a new `Available kWh` sensor (SoC × usable battery capacity), and a new `Charge Before Solar Recommended` binary sensor that turns on when available kWh is below tomorrow's buffered need. New optional config field `usage_profile_buffer_pct` (default 20 %) in step 6.
- **New "Usage Profile" panel tab**: a bar chart of average kWh per weekday (today and tomorrow highlighted), plus available kWh, tomorrow's need, and a plain-language charge-tonight-or-wait recommendation.

## [0.36.0] - 2026-08-06

### Added

- **New `CO2 Savings vs. ICE Vehicle` sensor**: parallel to the existing cost comparison, estimates kg CO2 saved vs. the reference combustion car — `(combustion fuel use × its CO2 factor) − (EV kWh used × co2_per_kwh_g)`. New optional config field `co2_per_kwh_g` (grid CO2 intensity, g/kWh, default 380 — a rough German-grid-average estimate) in step 7. The combustion-side CO2 factor is a fixed constant per fuel type (taken from `tankerkoenig_fuel_type` if set, otherwise gasoline).
- **New `External vs. Home Charging Price Difference` sensor**: the weighted-average price actually paid for external charging minus the home electricity price (both €/kWh, since setup) — a direct answer to "how much more does charging away from home cost me per kWh".
- **New `Cost (Today/Week/Month/Year)` sensors**: combined home + external charging cost within the current calendar period, using the same period-baseline-and-rollover mechanism already used for the driven-km period sensors.

## [0.35.0] - 2026-08-05

### Fixed

- **`Home Charging kWh (total)` and `Home Charging Cost (total)` now show the full evcc cumulative history, not just since the ev_assistant upgrade**: v0.33.0 introduced a reference-delta mechanism to normalise evcc's own cumulative counters so that `Vehicle Avg Consumption` reflected only the period since ev_assistant was set up. That was correct for the consumption calculation, but the same subtraction was mistakenly also applied to the display sensors — so after upgrading to v0.33.0 both sensors showed only the kWh/cost accumulated since the upgrade, losing all earlier evcc history. The display sensors now return evcc's raw cumulative value without any subtraction.
- **Savings and kWh/100 km use a separate "since ev_assistant setup" baseline**: the per-setup normalisation that v0.33.0 intended is now stored in two new fields (`savings_home_kwh_start` / `savings_home_cost_start`), captured once the first time the coordinator runs after installation. The display sensors show the full evcc total; the cost comparison and average consumption calculation accumulate from the point ev_assistant was first configured. For new installations this is automatic. Existing installations that upgraded through v0.33.0 have the baseline set at upgrade time — the display sensors now show the correct full history, and savings/kWh100km accumulate from the upgrade point onward (no further action required).

## [0.34.0] - 2026-08-05

### Fixed

- **`edit_trip` failed with "extra keys not allowed @ data['start_ts']" when correcting a trip's date/time**: the service's actual validation schema (registered in `__init__.py`) was never updated to accept `start_ts`/`end_ts` when that capability was added in 0.31.0 — only `services.yaml` (UI documentation) and the coordinator/panel side were. The handler now also accepts and forwards both fields. Verified live (edited and reverted a real trip's `start_ts`). Audited all other services' schemas against `services.yaml` for the same class of mismatch — none found.

## [0.33.0] - 2026-08-05

### Fixed

- **`Vehicle Avg Consumption` (and home-charging cost) could be wildly inflated when using evcc's own cumulative statistics for home kWh/cost** (evcc's site-wide total-charged-kWh statistic, or its per-vehicle `chargedEnergy`/`cost` session statistic). Those are evcc's own counters, running since evcc itself was set up — not since EV Assistant was configured. Used directly, a counter that's been running far longer than EV Assistant's own km-driven tracking produces a home-kWh figure for a much longer period than the km in the denominator, wildly overstating kWh/100 km (reported case: 980 kWh/100 km instead of the correct ~20). All three of these now establish a reference value the first time they're read (same principle already used for the wallbox-energy-meter fallback) and only count the delta since then. Note: for existing installations this resets the affected figure to 0 at upgrade time — there's no way to recover what evcc's counter was at EV Assistant's actual setup time, so it starts accumulating fresh from the upgrade.

## [0.32.0] - 2026-08-05

### Fixed

- **evcc vehicle auto-detection (used when `evcc_vehicle_name` isn't set) no longer parses the config entry title**: same underlying issue as the panel vehicle name fix in 0.31.0 — the title-parsing regex only handled the current `"EV Assistant (Manufacturer Model)"` format, not older entries created without parentheses. Now built directly from the manufacturer/model configuration instead.

## [0.31.0] - 2026-08-05

### Added

- **New optional `trip_auto_confirm` setting**: a detected trip is added to the trip log immediately instead of waiting as a "pending" entry for manual start/end-location confirmation. Start/end location come from the GPS location suggestion (`gps_entity`) if configured, otherwise stay empty (still editable later via `edit_trip`).

### Fixed

- **Panel vehicle name no longer shows a leftover "EV Assistant" prefix**: the name was previously parsed out of the config entry's title with a regex that only handled the current `"EV Assistant (Manufacturer Model)"` format — entries created under an older title format (`"EV Assistant Manufacturer Model"`, no parentheses) still showed the full un-stripped title. The panel now gets the vehicle name directly from the same manufacturer/model configuration the HA device name is already built from, independent of the entry title's format.

## [0.30.0] - 2026-08-04

### Added

- **`gps_entity` (trip log location suggestion) now also accepts plain `sensor` entities**, not just `person`/`device_tracker`. Its state is used the same way as before: resolved against a matching `zone.*` entity for a friendly name if possible, otherwise used as-is — so a `sensor` whose state is already a readable location name (e.g. a vehicle-reported location) works directly.

## [0.29.0] - 2026-08-04

### Added

- **Optional motor/driving sensor (`motor_entity`, `motor_debounce_s`) for trip detection**: a second signal for vehicles whose odometer updates too coarsely/infrequently for the existing standstill-timeout detection to reliably derive trip start/end. When configured, a confirmed "driving" state starts/continues a trip even without a fresh odometer reading, and a confirmed "not driving" is treated the same as "no odometer movement" — `trip_idle_timeout_s` still provides the grace period for brief stops (e.g. stop-start at a red light), so a momentary motor-off reading mid-trip does not end it. Distance is always taken from the odometer regardless of this signal; a genuine odometer increase is never ignored even if the motor signal says otherwise. Debounced (default 60 s, configurable) against brief flaky readings from the source — shorter than the plug sensor's default, since the actual tolerance for normal driving pauses already comes from `trip_idle_timeout_s`.
- Internally renamed `PlugDebouncer` to `SignalDebouncer` in `engine.py`, since it's now shared between the plug and motor signals (no functional change).

## [0.28.0] - 2026-08-04

### Fixed

- **External charges on vehicles with coarse/infrequent SoC reporting no longer split into multiple pending entries**: `idle_timeout_s` finalizes a session once no new SoC peak has been seen for that long — vehicles whose SoC only ticks every 10-20+ minutes (e.g. some manufacturer cloud APIs) could trip that timeout mid-charge, splitting one continuous external charge into several separate "pending" entries. A newly detected charge is now merged into the previous still-open one whenever there was no SoC drop in between (a real drop only happens if the car was actually driven, i.e. genuinely separate charge stops) — independent of the vehicle's reporting cadence.

### Added

- **Optional plug/connectivity sensor (`plug_entity`, `plug_debounce_s`)**: a more direct alternative to the fix above, for vehicles that expose a plug-state `binary_sensor` (e.g. via an OBD/CAN dongle). When configured, a confirmed "plugged in" overrides `idle_timeout_s` entirely — the session never times out while the car stays connected — and a confirmed "unplugged" ends it immediately. Debounced (default 300 s, configurable) against brief flaky readings from the source before either state is trusted.
- **`edit_trip` service can now correct any field of a confirmed trip log entry**, including its date/time (`start_ts`/`end_ts`), distance (`km`), odometer readings (`odo_start`/`odo_end`), SoC (`soc_start`/`soc_end`), and consumption (`verbrauch_kwh`) — previously only the start/end location could be corrected. Changing `km` adjusts the running trip-log total by the difference; changing `start_ts` also updates the entry's `datum` (used by the CSV export); changing `soc_start`/`soc_end` recomputes `delta_soc` and, unless given explicitly, `verbrauch_kwh`. The panel's trip-history edit form now has date/time fields alongside the existing ones.

## [0.27.0] - 2026-08-03

### Added

- **New sensor `Trip Log Avg Consumption`**: average kWh consumed per trip,
  across all trip-log entries with known consumption — either imported
  directly (`verbrauch_kwh`) or derived from SoC delta for detected trips.
- **New sensor `Vehicle Avg Consumption`**: overall average consumption in
  kWh/100 km since setup, from the energy balance (total charged kWh, home +
  external, ÷ km driven) — a distance-weighted figure independent of
  whether every individual trip was confirmed in the trip log. Shown in the
  vehicle card next to the odometer.
- **Detected trips now record consumption too**: previously only imported
  trips carried a `verbrauch_kwh` value; detected trips only had the raw
  `delta_soc`. Confirming a detected trip now also computes and stores
  `verbrauch_kwh` (`delta_soc × usable battery kWh`, clamped to ≥ 0), so
  every trip-log entry — detected or imported — has a consistent
  consumption figure. The panel's trip history now shows this per-entry.
- Root README (EN + DE) documentation updated to match: Tankerkönig
  auto-detection, `import_fahrtenbuch`, and the full evcc-based home
  kWh/price priority chain were previously undocumented there.

## [0.26.0] - 2026-08-03

### Fixed

- **SOC bar in Übersicht now reads from configured `soc_entity`**: previously
  the bar read from `evcc_vehicle_soc` (the evcc vehicle SOC entity). It now
  reads from the separately configured `soc_entity`, falling back to
  `evcc_vehicle_soc` if no `soc_entity` is set.

## [0.25.0] - 2026-08-03

### Fixed

- **Home charging cost now uses evcc's per-vehicle cost directly**: when
  `sensor.evcc_charging_sessions_vehicles` is available (evcc tracks cost
  per vehicle with the actual per-session tariff), that cost is used
  directly instead of multiplying kWh × the site-wide average price — the
  site-wide average blends in sessions from other vehicles at the same
  site, systematically underestimating the effective price for the vehicle
  in question.
- **Active charging session no longer appears in home charging history**:
  evcc creates a session record as soon as charging starts (with `finished`
  = null); the history list now filters out sessions without a finished
  timestamp so only completed sessions are shown.
- **Cost/100 km now uses odometer-based km (gefahrene_km) instead of trip
  log km**: the savings sensor's `gefahrene_km` attribute (odometer delta
  since setup) is the correct denominator — trip log km only counts
  confirmed trips and will always be lower, making the per-100-km costs
  appear inflated.

### Added

- **Locale-aware number formatting throughout the panel**: all displayed
  numbers (kWh, EUR, kW, km, €/kWh, chart axes) now respect the HA locale
  setting (`Settings → Profile → Number format`). German users see commas
  as decimal separators (e.g. `11,40`), US users see dots — without any
  manual configuration.
- **Bar chart value labels replaced by hover tooltip**: bar charts no
  longer show per-bar value labels (which overlapped in monthly view with
  30 bars). Hovering over any bar now shows a floating tooltip with the
  formatted value above it.
- **Cost-per-100-km labels renamed** from "/100km EV" / "/100km Verb." to
  "Kosten/100km EV" / "Kosten/100km Verb." for clarity.

## [0.24.0] - 2026-08-03

### Fixed

- **Home-charging price used time-weighted averaging, which is wrong for
  home charging**: a fluctuating home electricity price was averaged by how
  long each value was in effect — fine for fuel (driving doesn't correlate
  with fuel-price swings), but wrong for home charging, since smart/tariff-
  scheduled charging (e.g. via evcc) deliberately happens during cheap
  windows. The old approach blended in expensive hours where zero charging
  happened, systematically overestimating the effective price paid. Now
  kWh-weighted: each price is weighted by how much was actually charged
  while it was in effect (via the wallbox energy meter), so periods with no
  charging contribute zero weight.
- **Home-charging kWh/cost now prefer evcc's own statistics when
  available**: `sensor.evcc_stat_total_charged_kwh` /
  `sensor.evcc_stat_total_avg_price` (auto-discovered from the evcc
  integration) take priority over the wallbox-meter-based calculation when
  present — evcc already tracks and weights this correctly itself. Guarded
  by requiring a wallbox energy meter to also be configured for that
  vehicle, since these evcc statistics are site-wide, not per vehicle —
  without the guard, a second vehicle at the same evcc site would wrongly
  inherit the first vehicle's home-charging total.

## [0.23.0] - 2026-08-03

### Added

- **`import_fahrtenbuch` service**: bulk-import historical trips from another
  trip-log app/export directly into the trip log, bypassing the odometer
  detector entirely. Each entry: local-time `start`/`ende`, `start_ort`,
  `ziel_ort`, `strecke` (km), optionally `verbrauch_kwh`/`avg_verbrauch`/
  `avg_speed`. Odometer values stay empty (the source has none). Re-running
  the same import is safe — entries already present (same start time) are
  skipped rather than duplicated. Accepts either a plain list or the whole
  source file's `{"trips": [...]}` shape directly, since pasting the full
  file as-is into the field is an easy mistake.

### Fixed

- **"km driven today/this week/..." didn't reset at midnight if the car
  didn't drive right away**: the day/week/month/year baselines only rolled
  over as a side effect of a *new* odometer reading, so a parked car kept
  showing yesterday's distance until its first reading of the new day. A
  daily check (already scheduled for the LTS statistics refresh) now rolls
  the baselines over using the last known odometer value, independent of
  whether the car has moved yet.
- Trip log CSV export showed the literal text `None` for the odometer
  columns of imported trips (which have no odometer values) — now left
  blank instead.

## [0.22.0] - 2026-08-03

### Added

- **Time-weighted fuel/home-electricity price averaging**: when the fuel price or home
  electricity price comes from a live entity, the cost comparison no longer applies its
  current instantaneous reading to the entire distance/energy tracked since setup. Every
  reading is now weighted by how long it was actually in effect, so a price that fluctuates
  (e.g. a dynamic tariff or fuel-price tracker) is averaged correctly over time instead of
  distorting the whole comparison with whatever value happens to be live right now.
- **Tankerkönig auto-detection for the fuel price**: pick a fuel type (`super`, `super_e10`,
  `diesel`) in step 7 and EV Assistant automatically discovers every station configured in
  the core Tankerkönig integration, always using the cheapest currently *open* one — no
  manual price entity or custom template sensor needed. Takes priority over a manually
  linked fuel-price entity, which in turn takes priority over a fixed value.
- **Graceful degradation when Tankerkönig becomes unavailable**: the comparison keeps
  calculating with the last known good price rather than dropping out entirely. A persistent
  notification appears in Home Assistant for as long as Tankerkönig can't produce a single
  valid reading (fuel type never found, integration removed, ...), and is dismissed
  automatically once a valid price returns.
- New sensor `... Fuel Price (Selected)`: shows the raw price currently in effect for the
  comparison (whichever of the three sources — Tankerkönig, entity, or fixed — is active),
  with a `quelle` attribute naming the active source. Historized via Long-Term Statistics.

## [0.21.3] - 2026-08-02

### Fixed

- **Scrolling any history card in the panel could still jump the page back to the top** —
  the 0.21.2 `overscroll-behavior` fix addressed scroll-chaining at a list's boundary, but the
  actual root cause was that `hass` is set extremely often (near-every sensor change in the
  whole HA instance), and each update rebuilds list DOM when its content changed — including
  mid-scroll, which reset the scroll container. Scroll position is now captured before every
  reactive update and corrected back **only when it actually changed** as a side effect of that
  update, not written unconditionally on every tick.
- **First attempt at the above fixed the jump but introduced scroll stutter/jank**: writing
  `scrollTop`/`window.scrollY` back on every single `hass` update — even unchanged — was
  fighting the browser's native momentum-scroll animation on mobile. Now a no-op on the vast
  majority of updates (nothing rebuilt), only intervening on the rare tick that actually reset
  the scroll position.

## [0.21.2] - 2026-08-02

### Fixed

- **Vehicle card SOC was never shown**: it read exclusively from the optional `evcc_vehicle_soc`
  entity, auto-discovered from evcc — but that discovery only recognized one evcc naming scheme
  (loadpoint-prefixed, `sensor.{loadpoint}_vehicle_soc`) and silently found nothing on installs
  where evcc exposes vehicle data under a `configvehicle` namespace instead
  (`sensor.evcc_{vehicle}_configvehicle_soc`). The vehicle card now reads SOC from the vehicle's
  own `soc_entity` (step 1, always configured, the same source the detection engine already
  trusts) instead of depending on evcc auto-discovery at all.
- **evcc auto-discovery missed vehicle SOC/limit-SOC on `configvehicle`-style evcc_intg setups**:
  added recognition for `sensor.evcc_{vehicle}_configvehicle_soc` /
  `..._configvehicle_limitsoc`, alongside the existing loadpoint-based pattern. Fixes the
  Übersicht tab's live SOC bar for these installs too.
- **Confirmed trips never got a SOC value**: the trip detector snapshotted the start/end
  location for the GPS suggestion, but never actually captured the vehicle's SOC at trip
  start/end — the history display and `log_trip` handling for `soc_start`/`soc_end`/`delta_soc`
  (added in 0.21.1) had nothing to read, since the snapshot itself was never implemented. Now
  captured the same restart-safe way as the location suggestion. Takes effect from the next
  detected trip onward — already-confirmed trips are unaffected.
- **Scrolling the trip-log (or any expanded history) card on mobile could bounce the whole page
  back to the top**: classic scroll-chaining — reaching the end of the inner scrollable list
  without `overscroll-behavior: contain` let the scroll gesture propagate to the outer page.
  Added `overscroll-behavior: contain` (+ `-webkit-overflow-scrolling: touch`) to the expanded
  history list and the panel's main scroll container.
- **`NameError: name 'dt_util' is not defined`** on every coordinator update, breaking the
  "expected km/year since first registration" sensor (`odo_annual_from_reg`) added in 0.21.0 —
  `homeassistant.util.dt` was used but never imported in `sensor.py`.

## [0.21.1] - 2026-08-02

### Fixed

- **Trip log history entries** now display correctly as cards — matching the visual style of home and external charging history entries (card background, border, border-radius).
- **Date/time formatting** in trip entries now uses the proper German locale format (`dd.MM.yyyy HH:mm`) from the actual `start_ts` Unix timestamp, replacing the raw ISO date string. The end time (`bis HH:MM`) and trip duration are shown inline.
- **Trip route** (`start_ort → end_ort`) moved to its own last line, consistent with the requested layout.

### Added

- **SOC consumption in trip history**: confirmed trip records now store `soc_start`, `soc_end`, and `delta_soc` from the detected pending trip. The history entry shows the SOC drop (e.g. `85 → 63% (−22%)`), a teal SOC consumption bar, and average speed (km/h) computed from start/end timestamps.
- **German README** (`README.de.md`) — full German translation with language switcher. The English `README.md` links to it below the badge row.

## [0.21.0] - 2026-08-02

### Added

- **`last_charge_power` sensor** — average charge power (kW) for the most recently confirmed external charge, calculated from kWh ÷ duration. Sessions shorter than 5 minutes are excluded; implausible values outside 1–350 kW are suppressed and the sensor returns `unknown`.
- **Ø charge power in external charging history** — each external charge history entry in the panel now shows the average charge power (kW) next to the kWh figure, computed from the same kWh/duration data.
- **Ø charge power in home charging history** — same Ø power column added to the evcc home-charging session history in the panel.
- **Odometer period sensors** (all `entity_category: diagnostic`, `state_class` set for LTS): `odo_day_km`, `odo_week_km`, `odo_month_km`, `odo_year_km` — km driven since the start of the current day / ISO week / calendar month / calendar year. Period baselines are stored persistently in coordinator storage and update on rollover. Glitch-protected: backwards odometer jumps and implausibly large forward jumps are silently rejected.
- **LTS-based average and projection sensors** (all `entity_category: diagnostic`, `state_class: measurement`): `odo_avg_day`, `odo_avg_week`, `odo_avg_month`, `odo_avg_year` (rolling averages from 30/30/90/365-day LTS sum deltas), `odo_year_projected` (calendar-year extrapolation from Jan 1; returns `unknown` until ≥ 7 days into the year), `odo_annual_from_reg` (annual rate since the first-registration date configured in step 1). These sensors query `statistics_during_period` from the HA recorder at 00:05 each day; they require the configured odometer entity to have recorded Long-Term Statistics in HA.
- **All sensors now carry `state_class`** — enabling Long-Term Statistics recording for every EV Assistant sensor. Previously several sensors lacked a `state_class` and were therefore not included in LTS.
- **Verbrenner-Vergleich section in vehicle card** — below the km grid, a second column now shows Ersparnis (total savings, green), EV costs, estimated combustion cost, and cost per 100 km for both EV and combustion reference. Values are read directly from the `savings` sensor attributes; no new backend sensors required.

### Changed

- **Renamed sensors**: `pending_estimate` (previously "Fremdladung Schätzung") is now **"Fremdladung ausstehend"**; `trip_pending_estimate` (previously "Fahrt Schätzung") is now **"Fahrt ausstehend"**. Translation keys are unchanged; HA entity IDs are unaffected.
- **Vehicle card km section redesigned** — replaced the three stacked KPI rows with a compact 2-column grid: driven km per period (today / week / month / year) on the left, average and projected km on the right. The overall vehicle card now uses a side-by-side layout with km on the left and the Verbrenner-Vergleich on the right, separated by a vertical divider.
- **Chart card is now mobile-responsive** — on screens ≤ 600 px the three charts (charging overview, cost overview, solar share) stack vertically with horizontal dividers between them. The chart card header is reorganised: period pills and the week/month navigation now sit in a flex-column block, keeping the header compact on narrow screens.

## [0.20.2] - 2026-08-02

### Fixed

- Removed `evcc_intg` from `dependencies` in `manifest.json` — HA cannot resolve custom (HACS) integrations as hard dependencies, causing ev_assistant and potentially other integrations to fail loading entirely.

## [0.20.1] - 2026-08-02

### Fixed

- External charge history and trip log no longer drop old entries — the 100-entry cap (`HISTORY_MAX`) has been removed. All records are kept indefinitely in HA storage.

## [0.20.0] - 2026-08-02

### Changed

- **Config flow reduced from 9 to 7 steps**: the `grundsignale` step (SOC entity, home-charging entity) and the `wallbox` step (evcc live entities) have been removed. SOC entity is now in step 1 (vehicle details) and is a **required** field; home-charging entity (wallbox charge power) moved to step 2 alongside the evcc vehicle name.
- **All evcc entities auto-discovered**: `evcc_intg` is now declared as a Home Assistant dependency. During setup the integration automatically reads all enabled entities from the evcc integration config entry and maps them to the corresponding `CONF_EVCC_*` keys — no manual entity selection needed for PV, grid, battery, tariff, and loadpoint entities.
- **Step 2 (evcc) simplified**: only two optional fields remain — the vehicle name in evcc (for filtering home-charging history) and the wallbox charge power entity (yes/no signal for "currently charging at home").
- **All template fields removed** (`soc_template`, `home_template`, `power_template`, `wallbox_energy_template`) — direct entity selection is now used exclusively.
- Translation files (`de.json`, `en.json`, `strings.json`) completely rewritten to match the new 7-step structure with updated step numbers and labels.

### Added

- **Home charging kWh via evcc vehicle statistics**: the coordinator now reads `sensor.evcc_charging_sessions_vehicles` to get per-vehicle total home-charging energy directly from evcc. Falls back to wallbox energy meter delta if the evcc vehicle key cannot be resolved.
- **Auto-detection of evcc vehicle key**: if no vehicle name is configured manually, the coordinator attempts to match the config entry title (e.g. `EV Assistant (VW ID4)`) against the vehicle keys in the evcc charging-sessions sensor attributes.

### Fixed

- `verbrenner_price_entity` in the cost-comparison step was using the home-price entity selector instead of its own dedicated entity selector.

## [0.19.0] - 2026-08-01

### Added

- **Fully redesigned Fahrzeuge panel — a complete EV dashboard**: the Fahrzeuge tab is now a three-column vehicle dashboard: home charging (evcc sessions), external charging, and trip log. Each column shows overall totals, the last session, and the full history — all in one merged card. When more than one vehicle is configured, pill-style tabs appear to switch between them.
- **Vehicle card with SOC and name**: the vehicle overview now shows the vehicle name and current SOC as a large number with a color-coded bar (red < 20 %, orange < 40 %, green otherwise), sourced from the configured evcc vehicle SoC entity.
- **Home charging history** (evcc sessions) now includes SOC (start → end + delta), price per kWh, and a SOC progress bar per entry.
- **SOC progress bar in external charging history**: same bar as in home charging, colored in grid blue.
- **Color-coded card design** following HA energy dashboard colors: PV amber (`#ff9800`) for home charging, grid blue (`#488fc2`) for external charging, teal (`#14b8a6`) for the trip log — with a color top border, icon background, and tinted KPI values.
- **"Last session" section as a tinted block**: the last session's KPIs are grouped in a distinct `--bg-2` block within the summary card.
- **KPI improvements**: values are centered and distributed evenly across the full card width; vertical dividers between individual KPIs.
- **Tab switch animation**: switching between vehicles triggers a smooth fade-in transition.
- **Hover effects** on all history entries.
- **Summary and history merged into one card**: no separate history card — the history section flows directly below the summary within the same card.

### Changed

- Vehicle card icon changed from `mdi:car-info` to `mdi:car-electric`.

## [0.18.2] - 2026-08-01

### Added

- **Multi-vehicle tab support in the Fahrzeuge view**: when more than one EV Assistant config entry is configured, pill-style tabs appear at the top of the Fahrzeuge view to switch between vehicles. Each tab shows the vehicle name (extracted from the entry title). Switching tabs resets per-vehicle state (pending forms, history, filters) while keeping shared state (evcc session cache). The backend now collects all ev_assistant config entries into a `vehicles` array in the panel config so the frontend has complete entity maps and config IDs for each vehicle. Unloading one entry re-registers the panel with the remaining entries.

## [0.18.1] - 2026-07-31

### Fixed

- **Confirming a pending external charge in the panel could silently do nothing**: clicking
  "Bestätigen" while the price field was still empty (only kWh gets prefilled with the
  estimate, price never does) just no-op'd with zero feedback — easy to mistake for a broken
  button. The confirm button is now disabled until both kWh and price are valid numbers (with
  a tooltip explaining why), for both the pending-charge and pending-trip forms, instead of
  silently rejecting the click.

### Changed

- **Redesigned the pending-charge/pending-trip capture cards** ("Laufende Erfassung") to match
  the visual polish of the history cards: icon + title + date/duration at the top, the
  estimate (kWh + SoC range, or km) shown prominently, then the input fields, then clearly
  separated actions — replacing the previous plain single-row layout.
- **Wired up the GPS/zone location suggestion for pending trips** in the panel
  (`start_ort_vorschlag`/`end_ort_vorschlag`, added in 0.15.0) — previously only used by the
  Lovelace card, the panel's trip form now prefills Start-/Zielort from it too when available.

## [0.18.0] - 2026-07-31

### Removed

- **MQTT support removed entirely** — breaking change if you configured any signal (SoC,
  home-charging, vehicle charging power, wallbox energy meter) via its MQTT-topic field, or
  relied on the outbound event-publish MQTT topic. Every signal must now come from an HA entity
  instead. If your source is MQTT-based (e.g. WiCAN Pro), set up Home Assistant's own `mqtt`
  integration to expose it as a `sensor` entity first, then point EV Assistant at that entity —
  the per-signal Jinja template field still works exactly as before for unit conversions. The
  `mqtt` integration is no longer a hard dependency of EV Assistant.

### Changed

- **Config/options flow: "Wallbox" and "evcc" are now two separate steps** instead of one mixed
  step — no more mixing this vehicle's live loadpoint state with site-wide evcc data in a single
  form. **Wallbox** (step 8) covers this vehicle's live charging state at the evcc charge point
  (power, status, mode, phases, vehicle SoC, limit SoC, session energy/solar/price, duration).
  **evcc** (step 9) covers data that applies to the whole evcc installation, not just this charge
  point (PV/grid/home-battery power, tariffs, all-time statistics), plus the new **vehicle name in
  evcc** field (see below). All 9 steps are renumbered consistently (previously drifted between
  "N/7" and "N/8" after the trip-log step was added in an earlier release).

### Added

- **Heimladen-Historie (home-charging history)** in the panel's Fahrzeuge tab: evcc's own
  charging-session log, fetched live via evcc_intg's `sessions` websocket command — no new
  backend service needed, and no separate configuration beyond evcc_intg itself being set up.
  Read-only (evcc owns this data), same last-5/expand/scroll card layout as the external-charge
  history.
  - **Vehicle name in evcc** (new optional config field, step 9): if evcc manages more than one
    vehicle, the panel's Heimladen-Historie gets a dropdown filter (defaulting to this configured
    vehicle, still freely switchable in the panel itself) instead of showing every vehicle's home
    charges mixed together.
  - **Solar-share evaluation**: each session shows its own solar percentage (when evcc reports
    one), plus an energy-weighted average across the currently visible/filtered sessions.
- **Fremdladung-Historie (external-charge history)** in the panel gained several refinements:
  - Start/end SoC shown per entry, with the delta (e.g. "41% → 82% (+41%)"), for automatically
    detected charges.
  - End time and charge duration shown next to the (start-time-based) date, when the underlying
    detection data is available.
  - Deleting an entry now opens an expanding confirm panel with explicit "Löschen"/"Abbrechen"
    buttons, matching the editing interaction, instead of an inline double-click guard on the
    delete icon.
  - The list now shows the last 5 by default with an "show all / show less" toggle that expands
    the list into a scrollable area — no entries are ever removed from the underlying history,
    only the display is affected. Toggling no longer jumps the page/panel scroll position.

## [0.16.1] - 2026-07-26

### Added

- **Donut charge power gauge** in the Übersicht hero card: an SVG ring shows the current
  wallbox charge power relative to the dynamic maximum (`phases_active × 3.68 kW` at 16 A).
  The arc is split into solar (green) and grid (blue) segments based on the session's
  solar percentage. When the wallbox is idle the ring is empty.

## [0.16.0] - 2026-07-26

### Added

- **Sidebar panel**: EV Assistant now registers a custom sidebar panel automatically when the
  integration is set up — no manual dashboard setup required. The panel uses the same
  registration approach as omnibattery (`panel_custom.async_register_panel`).
  - **Übersicht tab**: Wallbox system status (WARP 3 Pro via evcc) — connection state,
    charge mode badge, phase badge, SOC bar with limit marker, live KPIs (charge power,
    session kWh, solar %, session price, duration), current tariff (grid / feed-in), and
    all-time wallbox statistics.
  - **Fahrzeuge tab**: Per-vehicle detail — external charging (totals + last session),
    home charging totals, trip log (last trip, count, total km), vehicle info
    (odometer, charging efficiency, savings vs. combustion), and a running-session
    estimate card shown only when a charge or trip is actively being recorded.
- **Panel cache-busting**: module URL includes the JS file's mtime so browser always
  picks up updates after an integration reload without a version bump.

## [0.15.3] - 2026-07-24

### Fixed

- **Notification titles/messages (detected external charge, detected trip, CSV export) were
  hardcoded German text regardless of the HA UI language** — unlike entity names and config-flow
  text, free-form notification bodies aren't covered by `strings.json`/`translations/*.json`, so
  they always read in German even on an English-locale install. The coordinator now picks
  English or German wording based on `hass.config.language`, matching whichever language the
  rest of the UI already shows.
- **README's English section still showed old German entity-name fragments** (e.g.
  `sensor ... Heimladen kWh (gesamt)`, `binary_sensor ... Fremdladung Erfassung offen`) left over
  from before the 0.15.2 translation fix, plus some narrative prose still in German ("Fremdladung",
  "Fahrtenbuch" used as English words). Updated throughout to the new English entity names and
  terminology — the German section is untouched, this only affects the 🇬🇧 half of the README.

## [0.15.2] - 2026-07-24

### Fixed

- **`translations/en.json` was a byte-for-byte copy of the German `strings.json`/`de.json`**,
  so English-locale HA installs saw German config-flow titles/descriptions and German entity
  names (e.g. "Heimladen kWh (gesamt)" instead of "Home Charging kWh (Total)"). Replaced with an
  actual English translation, same keys/structure as `strings.json`. Purely a display-text
  change — `entity_id`/`unique_id` are unaffected (translation_key-based names resolve live per
  UI language and are never baked into the registry unless manually renamed), so already-created
  devices/entities keep working exactly as before, just with correct English labels for English
  UI users.

## [0.15.1] - 2026-07-24

### Fixed

- **"Heimladen kWh (gesamt)" (and the analogous km-driven comparison) could show a large,
  meaningless negative value after swapping the underlying wallbox-energy or odometer entity**:
  both `wallbox_energy_start` and `odo_start` are reference values frozen on the very first valid
  reading and never touched again, by design (see the original comments) — but if you later
  reconfigure `wallbox_energy_entity`/`odo_entity` to point at a *different* entity (e.g. a
  placeholder/dummy sensor while no wallbox exists yet), the old reference still refers to the
  previous entity's absolute value. `current(new entity) - reference(old entity)` then produces
  an arbitrary, often deeply negative number instead of "unknown". The coordinator now also
  remembers which entity/topic each reference was captured against
  (`wallbox_energy_start_source`/`odo_start_source`) and re-captures the reference automatically
  the next time the configured source no longer matches. Existing installs upgrading to this
  version keep their current reference as-is (no source recorded yet ⇒ no forced reset) — only a
  reconfiguration *after* upgrading triggers a fresh capture. Does not retroactively fix a value
  that's already gone negative from a swap made before this update; use
  `ev_assistant.simulate_event`/a manual data correction for that.

## [0.15.0] - 2026-07-24

### Added

- **Automatic start/end location suggestion for the Fahrtenbuch**: a new optional `gps_entity`
  config field (step 6, "Fahrtenbuch") accepts a `person` or `device_tracker` entity (e.g. the
  driver's phone). When a trip starts and ends, the entity's current HA zone (e.g. "Home") is
  captured as a `start_ort_vorschlag`/`end_ort_vorschlag` suggestion on the pending trip —
  exposed as attributes on the existing pending-trip sensor/binary sensor. This does **not**
  replace manual confirmation via `log_trip`: it's a prefill suggestion, not an automatic
  entry, so a typo-prone or momentarily out-of-zone location can still be corrected by hand.
  Falls back to no suggestion (empty, as before) if `gps_entity` isn't configured or the
  location isn't inside any known zone. `engine.py::TripDetector` gained a public `active`
  property so the coordinator can detect the idle→driving transition and snapshot the location
  at that exact moment, without teaching the (deliberately GPS-agnostic) detector about zones.

## [0.14.1] - 2026-07-20

### Added

- **`edit_trip`/`delete_trip` services for the Fahrtenbuch**, completing the CRUD set introduced
  in 0.14.0 (`edit_charge`/`delete_charge` already existed for external charges). `edit_trip`
  corrects the start/end location of an already-confirmed entry (distance/odometer stay
  detector-only, not editable). `delete_trip` fully removes an entry and adjusts the running
  totals — not reversible, mirroring `delete_charge`.

## [0.14.0] - 2026-07-20

### Added

- **Fahrtenbuch (trip log)**: trips are now detected automatically from the same odometer
  entity/sensor used for the cost comparison (step 1), no GPS needed — a new `TripDetector`
  (`engine.py`) segments the monotonically increasing odometer into individual trips, separated
  by stationary periods, mirroring the existing `ChargeDetector` architecture (state persists
  across restarts the same way). Each detected trip is confirmed manually via the new
  `ev_assistant.log_trip` service with a start/end location; `ev_assistant.discard_pending_trip`
  discards a false positive, and `ev_assistant.simulate_trip` creates a synthetic one for testing.
  New sensors: trip pending estimate/binary sensor, last trip distance, trip count, total
  logged km. A new config-flow step ("Fahrtenbuch", step 6/7) tunes the minimum trip distance
  and the stationary timeout that ends a trip. `ev_assistant.export_fahrtenbuch` writes the full
  history as a CSV file to `www/` for download/tax purposes. No purpose (business/private) or
  comment field by design — this is a plain distance/location log, not a compliance tool.

## [0.13.0] - 2026-07-20

### Changed

- **Rewrote every config flow step's description and field labels for clarity**, continuing the 0.12.1/0.12.2 charging-power/wallbox-meter clarification across the whole flow: usable battery capacity now explicitly says it means the *net* value, not a manufacturer's larger gross/factory figure; first-registration date and odometer entity now say they're display-only (except the odometer's role as the cost-comparison distance basis); the home-charging signal (step 2) now explicitly disambiguates itself from the unrelated charging-power field in step 3; step 4's output fields now explain that a persistent notification always appears regardless, with `notify.*`/MQTT being additive; step 5's fields now explain what each detection threshold actually does and the `noise` < `start_delta` requirement inline instead of only in the README. The README's setup walkthrough was updated to match.

## [0.12.2] - 2026-07-20

### Changed

- **Clarified the wallbox energy meter's field label/description too**, as the counterpart to 0.12.1's charging-power clarification: it explicitly says it's a *cumulative* kWh counter of your *own* wallbox (never a momentary reading), relevant only while charging at home — as opposed to the charging-power field, which is a momentary vehicle-telemetry reading relevant during external charges. Step 3's description now spells out both fields side by side so the contrast is explicit.

## [0.12.1] - 2026-07-20

### Changed

- **Clarified what "Ladeleistung" (charging power, step 3) actually means**: the field name/description previously didn't say where the reading should come from, which read as if it should be your home wallbox's power sensor. It's actually read from the vehicle's own telemetry — `power_kw` is only integrated by the detector *during an external charge*, i.e. exactly when the car isn't plugged into your wallbox, so a wallbox-sourced reading would report nothing during the scenario this field exists for. Relabeled the field ("Fahrzeug-Ladeleistung") and reworded the step 3 description, the "power is AC-side" toggle, and the related README sections (energy estimation methods, worked examples) to say so explicitly.

## [0.12.0] - 2026-07-20

### Added

- **Home electricity price can now be a live entity, not just a fixed value**: the cost comparison's `home_price_kwh` (step 6) gets a sibling `home_price_entity` field, mirroring how the fuel price already works — link it to a dynamic-tariff sensor and it takes precedence over the fixed value whenever both are set. Its last known good value is persisted and restored on restart/outage, same as the fuel price. The `... Ersparnis ggü. Verbrenner` sensor gets a new `heimstrompreis_live` attribute alongside the existing `kraftstoffpreis_live`.

### Changed

- **`Ladewirkungsgrad (gemessen)` is now a diagnostic entity**: it reflects the calibration status of a config-flow-provided setting (`charge_efficiency`) rather than a core charge-tracking metric, matching the existing diagnostic treatment of `Kilometerstand` and `Erstzulassung`.

## [0.11.1] - 2026-07-20

### Fixed

- **Fuel-price entity's value wasn't remembered across restarts**: if `verbrenner_price_entity` went `unavailable` right after a restart (before reporting a fresh value), the savings comparison had nothing to fall back to until the entity reported again — even though the entity's last known value was perfectly usable. The last valid reading is now persisted and restored on startup, so the comparison keeps working through brief entity outages and restarts.

## [0.11.0] - 2026-07-19

### Added

- **A running (not-yet-finalized) Fremdladung detection now survives HA restarts**: the detector's anchor/peak/session state was only ever kept in memory, so any restart silently discarded an in-progress detection — a genuine external charge in progress could be lost without a trace. This state is now persisted (`engine.py::ChargeDetector.get_state()`/`load_state()`) alongside history/pending, and restored automatically on setup. Verified with a test that simulates a restart mid-session and confirms the resulting `ChargeEvent` is identical to one without a restart in between.

## [0.10.1] - 2026-07-19

### Changed

- **`start_delta` default lowered from 3 % to 1 %**: 3 percentage points turned out to be too insensitive for slower-updating or coarser SoC sources (e.g. some cloud-based telemetry), where a real external charge could go unnoticed for a while. 1 % is more responsive while still safely above the `noise` default (0.5 %) — keep `start_delta` above `noise` to avoid false detections from ordinary sensor jitter (now called out explicitly in the README).

## [0.10.0] - 2026-07-16

### Added

- **Cost comparison vs. a combustion car**: new step 6 in the config flow (`home_price_kwh`, `verbrenner_l_100km`, `verbrenner_price_per_liter`, and an optional `verbrenner_price_entity` that overrides the fixed fuel price when set). Distance driven is tracked via the odometer entity from step 1 (delta since first seen); home-charging kWh via the wallbox energy meter from step 3 (same delta pattern). All inputs are optional — the new sensors simply show `unknown` until their required data is available.
- New sensors: `... Heimladen kWh (gesamt)`, `... Heimladen Kosten (gesamt)`, and the headline `... Ersparnis ggü. Verbrenner` (with `gefahrene_km`, `heimladen_kosten`, `fremdladen_kosten`, `kosten_ev_gesamt`, `kosten_verbrenner_geschaetzt`, `kraftstoffpreis_live` attributes).
- New pure function `engine.py::calculate_savings` (unit-tested) for the underlying math.

## [0.9.0] - 2026-07-15

### Added

- **Charging duration**: new `... Fremdladung Ladezeit (letzte)` sensor shows how long the most recently confirmed external charge took (detection start to end, in minutes). Previously `duration_min` was computed by the detector but discarded once a charge was confirmed — it's now carried into the history record (`dauer_min`) instead of being lost.

## [0.8.3] - 2026-07-15

### Fixed

- **`idle_timeout_s` never fired if the SoC value stopped changing entirely** (e.g. battery reaches 100 % and the source sensor only reports on change): detection re-evaluation only ran when a *new* SoC sample arrived, so an active session's idle-timeout condition was never checked once the last SoC update happened. Added a periodic 60 s re-check (using the last known signal values) so a stuck-at-plateau session still finalizes on schedule instead of staying silently active forever.

## [0.8.2] - 2026-07-15

### Fixed

- **Home-charging entity picker was filtered to `device_class: power` (e.g. a wallbox's charging-power sensor) but the parsing logic only matched text/boolean values (`"on"`, `"charging"`, ...)** — a numeric power reading like `"7.4"` never matched, so home-charging was silently never detected for anyone using a real power sensor as recommended by the picker. Numeric values are now compared against a 0.1 kW threshold; non-numeric values still fall back to the original text match (e.g. evcc's own `"charging"`/`"on"` status), so existing setups keep working unchanged.

## [0.8.1] - 2026-07-15

### Fixed

- **Editing/deleting a non-newest history entry didn't show up in the UI without a manual reload**: `edit_charge`/`delete_charge` on an older entry (not the most recent charge) correctly updated the stored data, but the last-cost sensor's `historie` attribute — which the [EV Assistant Card](https://github.com/weskona/ev-assistant-card)'s History list reads — didn't get pushed to Home Assistant's state machine, since the sensor's own `native_value` (tied to only the newest entry) hadn't changed. Added `force_update` to the affected sensors so attribute-only changes are always written through. Verified live: repeated the exact failing scenario before and after the fix.

## [0.8.0] - 2026-07-15

### Added

- **Odometer entity picker** in the Vehicle step (step 1): pick your car's mileage sensor (filtered to `device_class: distance`) to have it mirrored on the EV Assistant device itself, grouped with the rest of the vehicle's sensors instead of living only on the source integration's device. Purely a display passthrough — no detection logic depends on it. Optional, no MQTT topic alternative (it's not a detection signal).
- New `... Kilometerstand` sensor (mirrors the configured odometer entity's value and unit) and `... Erstzulassung` sensor (exposes the first-registration date already collected in step 1 as a proper `date`-typed sensor instead of only living in config). Both are diagnostic entities.

## [0.7.0] - 2026-07-15

### Added

- **`ev_assistant.delete_charge` service**: fully removes an already-confirmed history entry (e.g. a falsely detected charge that wasn't actually an external charge), identified by its `erfasst_ts` attribute. Running totals (kWh/cost/count) are adjusted by the removed amount; if the deleted entry was the most recent one, `last_price` resets to the new most recent entry's price (or 0.0 if history is now empty). Not reversible.

## [0.6.2] - 2026-07-14

### Fixed

- **0.6.1's `zip_release` broke HACS's ability to see/install the release entirely**: the release zip wrapped everything under `custom_components/ev_assistant/` (plus `hacs.json`/`README.md`/`LICENSE` at the root), but HACS's `zip_release` mode expects the integration's files directly at the zip root (verified byte-for-byte against HACS's own `hacs.zip` release asset, which has `manifest.json` etc. at the top level, no `custom_components/hacs/` wrapper). The release workflow now zips the *contents* of `custom_components/ev_assistant/` directly.

## [0.6.1] - 2026-07-14

### Fixed

- **HACS download counter always showed 0**: `hacs.json` didn't set `zip_release`/`filename`, so HACS silently fell back to GitHub's auto-generated source archive for each release instead of the `ev_assistant.zip` asset our release workflow uploads — and GitHub only tracks download counts for actual uploaded release assets, not auto-generated source archives. Added `"zip_release": true, "filename": "ev_assistant.zip"` so HACS fetches the tracked asset.

## [0.6.0] - 2026-07-14

### Added

- **`ev_assistant.edit_charge` service**: corrects the kWh/price of an already-confirmed history entry (e.g. a typo noticed after the fact), identified by its `erfasst_ts` attribute. Running totals (kWh/cost) are adjusted by the difference rather than recomputed from the full history, so older entries that have aged out of the stored history (see `HISTORY_MAX`) don't distort the totals.
- The last-cost sensor now also exposes a `historie` attribute with the full stored history list, so tools like the [EV Assistant Card](https://github.com/weskona/ev-assistant-card) can list and select any past entry to correct.

## [0.5.1] - 2026-07-14

### Fixed

- Added the required `brand/icon.png` so the repository passes HACS's brand-assets validation check (previously failed with "does not provide brand assets and is not listed in the Home Assistant brands repository").

## [0.5.0] - 2026-07-14

### Fixed

- **Data loss when a second external charge was detected before the first was confirmed**: `pending` was a single record that got silently overwritten by the next detection (e.g. two charging stops on a road trip before you got around to confirming either) — the first charge's estimate was lost with no notification, no history entry, nothing. `pending` is now a list; detections are appended, never overwritten.

### Added

- `ev_assistant.log_charge` and `ev_assistant.discard_pending` now accept an optional `start_ts` to pick which of several simultaneously pending charges to act on (the value comes from that charge's own `start_ts` attribute). Without it, the oldest pending charge is used (FIFO) — existing automations that don't pass `start_ts` keep working unchanged.
- The pending-charge notification now lists **all** currently open charges (not just the newest) when there's more than one, still using a single notification that replaces itself rather than spamming multiple.
- `binary_sensor ... Fremdladung Erfassung offen` and `sensor ... Fremdladung Schätzung` gained `anzahl_offen` (count) and `offene_ladungen` (the full list) attributes; the oldest charge's own fields remain flattened at the top level for backward compatibility.
- Existing stored data (single dict or `None`) is migrated automatically to the new list format on first startup after upgrading — verified with the exact scenario that surfaced this gap (a real pending charge survived the migration with all its data intact).

## [0.4.3] - 2026-07-14

### Added

- **[EV Assistant Card](https://github.com/weskona/ev-assistant-card)**: a new dedicated Lovelace card, recommended over the `packages/ev_assistant_ui.yaml` helper-entity approach. README updated to point to it.

### Changed

- Sensors now use `_attr_translation_key` instead of hardcoded `_attr_name` (matching the sibling `tariffy` integration's pattern), with the same display text as before — no user-visible change, but this makes the sensors' role machine-discoverable by translation key/unique_id for tools like the new card above.

## [0.4.2] - 2026-07-14

### Documentation

- Substantially expanded README (English first, then German): a detailed "how it works" explanation of the detection state machine, a full worked walkthrough of what happens step by step when an external charge is detected, an "energy estimation methods" reference table for the three calculation sources (`soc`/`power_ac`/`power_dc`), a `Sensors in detail` table replacing the old plain entity list, and a dedicated "example calculations" section covering all four calculations the integration performs (external-charge SoC estimate, power-sensor estimate, efficiency-calibration sample, and logging the real receipt) — all worked examples verified against the actual `engine.py` logic, not just hand-calculated.
- Fixed a small ASCII-transliteration typo in the pending-charge notification text (`geschaetzt` → `geschätzt`).

## [0.4.1] - 2026-07-14

### Fixed

- **`packages/ev_assistant_ui.yaml` broken since v0.4.0's multi-vehicle support**: the bundled save/discard automations never passed `config_entry_id`, which became a required field in `ev_assistant.log_charge`/`discard_pending` — so pressing those buttons always failed validation. The `ev_assistant_pending`/`ev_assistant_logged` events (and the MQTT `.../erfasst` payload) now include `config_entry_id`, and the package automations capture it from the triggering event via a new `input_text.ev_assistant_config_entry_id` helper.
- Removed the price prefill step in that same package, which read a hardcoded entity id (`sensor.ev_assistant_letzter_preis`) that no longer matches the vehicle-based device name — `input_number` already retains its last entered value across restarts, so the prefill was redundant as well as broken.

## [0.4.0] - 2026-07-14

### Added

- **Config flow redesign**: initial setup and editing (Configure) now walk through the same 5 focused steps — Vehicle, Basic signals, Charging power, Output, Detection fine-tuning — instead of a 2-step setup followed by a single 17-field options mega-page.
- **Automatic charge-efficiency calibration**: a new optional wallbox energy meter field (cumulative kWh counter) lets EV Assistant learn the real AC→battery efficiency from your own home-charging sessions (SoC delta vs. measured wallbox energy). After 3 valid sessions the rolling average automatically replaces the manual value for all calculations, live, no restart needed. New sensor `... Ladewirkungsgrad (gemessen)`.
- **Vehicle-based device name**: the HA device is now named after the vehicle (`{Manufacturer} {Model}`, e.g. "Peugeot e-2008") instead of the generic hardcoded "EV Assistant". Existing entries are migrated automatically.
- **Entity pickers filtered by device class**: SoC entity picker restricted to `sensor` + `device_class: battery`; charging-power/home-charging pickers to `power`; the new wallbox energy meter picker to `energy` — much less scrolling through unrelated entities.
- `config_entry_id` is now included in the `ev_assistant_pending`/`ev_assistant_logged` events and in the MQTT `.../erfasst` payload, so automations (including the bundled `packages/ev_assistant_ui.yaml`) can tell which vehicle a charge belongs to when running more than one instance.

### Changed

- Manufacturer + model are now required fields (previously optional free text), as are vehicle and usable battery capacity — SoC and home-charging fields are visually marked as required (`*`) even though they technically allow either an entity or an MQTT topic.
- Sensors renamed with a `Fremdladung` prefix (e.g. "Anzahl Ladungen" → "Fremdladung Anzahl") to distinguish them from the new, unrelated efficiency-calibration sensor, which is derived from home charging, not external charging.
- Proper German umlauts throughout entity friendly names and config-flow text (previously ASCII transliterations like `Schaetzung`, `Entitaet`).
- `packages/ev_assistant_ui.yaml` updated to pass the now-required `config_entry_id` to `log_charge`/`discard_pending`, captured automatically from the triggering event; the fragile prefill of the last price from a hardcoded entity id was removed in favor of `input_number`'s own built-in value persistence.

### Removed

- **KBA/HSN/TSN manufacturer lookup**: only identified the manufacturer from the official German vehicle registry list, not the actual model/variant, so it added a config step without adding real value. Replaced by simple, direct manufacturer/model text fields.

### Documentation

- Bilingual README (English first, then German), including a documented known limitation for the bundled UI package files.
- Added `tests/test_engine.py` coverage for the new `EfficiencyCalibrator`/`average_efficiency` logic (8 new tests, 17 total, all pure-Python/pytest, no Home Assistant dependency).
