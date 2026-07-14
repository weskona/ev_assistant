# Changelog

All notable changes to the EV Assistant integration. Format inspired by [Keep a Changelog](https://keepachangelog.com/), versioning in `manifest.json`.

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
