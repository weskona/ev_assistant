# Changelog

All notable changes to the EV Assistant integration. Format inspired by [Keep a Changelog](https://keepachangelog.com/), versioning in `manifest.json`.

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
