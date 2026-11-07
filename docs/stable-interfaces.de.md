# Stabile Schnittstellen

Diese Seite listet die Schnittstellen, die innerhalb von 1.x stabil bleiben (siehe *Status & bekannte Grenzen* in der [README](../README.de.md)). **Sie wird aus dem Code erzeugt** (`.github/scripts/gen_interfaces.py`); ein Test schlägt fehl, wenn Code und Seite auseinanderlaufen. Wer hier etwas hinzufügt, umbenennt oder entfernt, führt `python3 .github/scripts/gen_interfaces.py` aus und prüft den Diff dieser Seite: ein entfernter oder umbenannter Eintrag ist ein **inkompatibler Bruch** und braucht eine neue Hauptversion und einen CHANGELOG-Eintrag.

## Was „stabil“ heißt

- **Additive Änderungen sind erlaubt** in 1.x: neue Dienste, neue optionale Dienstfelder, neue Entitäten, neue Attribute, neue Config-Schlüssel mit Standardwert.
- **Nicht erlaubt** in 1.x: einen Eintrag unten entfernen oder umbenennen, die Bedeutung eines Feldes ändern, ein optionales Feld zum Pflichtfeld machen, den `unique_id`-Schlüssel einer Entität ändern.
- **Attribute** der Entitäten: die Zusage gilt für die auf der Wiki-Seite [Sensoren & Entitäten](https://github.com/weskona/ev_assistant/wiki/Sensors-and-Entities-DE) dokumentierten Attribute; nicht dokumentierte können sich ändern.
- **Nicht Teil der Zusage:** die Testwerkzeuge `simulate_event` und `simulate_trip`, die Zahlen hinter der automatischen Steuerung (Schwellen, Schätzungen, Empfehlungen) und die Glow-Karte selbst.

## Dienste

Domain `ev_assistant`. Ein angehängtes `?` kennzeichnet ein optionales Feld, alle anderen sind Pflicht; jeder Dienst nimmt zusätzlich `config_entry_id` (das Fahrzeug).

| Dienst | Felder | Status |
|---|---|---|
| `add_ladekarte` | `name`, `monatliche_gebuehr`, `start_datum`, `end_datum?` | stabil |
| `add_ladekarte_preisstufe` | `karte_id`, `gebuehr`, `ab_datum` | stabil |
| `add_maintenance` | `name?`, `preset?`, `km_intervall?`, `zeit_intervall_monate?`, `festes_datum?`, `kosten?`, `last_done_km?`, `last_done_datum?`, `reminder_monate?`, `reminder_km?`, `erst_km_intervall?`, `erst_zeit_intervall_monate?` | stabil |
| `clear_evcc_charge_plan` | – | stabil |
| `clear_evcc_manual_mode` | – | stabil |
| `clear_vehicle_image` | – | stabil |
| `delete_charge` | `erfasst_ts` | stabil |
| `delete_ladekarte` | `karte_id` | stabil |
| `delete_ladekarte_preisstufe` | `karte_id`, `ab_datum` | stabil |
| `delete_maintenance` | `wartung_id` | stabil |
| `delete_trip` | `erfasst_ts` | stabil |
| `discard_pending` | `start_ts?` | stabil |
| `discard_pending_trip` | `start_ts?` | stabil |
| `edit_charge` | `erfasst_ts`, `kwh?`, `price_kwh?`, `start_fee?`, `block_fee?`, `time_fee?`, `start_ts?`, `end_ts?`, `soc_start?`, `soc_end?`, `karte_id?`, `anbieter?` | stabil |
| `edit_ladekarte` | `karte_id`, `name?`, `monatliche_gebuehr?`, `start_datum?`, `end_datum?` | stabil |
| `edit_maintenance` | `wartung_id`, `name?`, `km_intervall?`, `zeit_intervall_monate?`, `festes_datum?`, `kosten?`, `last_done_km?`, `last_done_datum?`, `aktiv?`, `reminder_monate?`, `reminder_km?`, `erst_km_intervall?`, `erst_zeit_intervall_monate?`, `erledigt_anzahl?` | stabil |
| `edit_trip` | `erfasst_ts`, `start_ort?`, `end_ort?`, `start_ts?`, `end_ts?`, `km?`, `odo_start?`, `odo_end?`, `soc_start?`, `soc_end?`, `verbrauch_kwh?` | stabil |
| `export_backup` | – | stabil |
| `export_event_log` | – | stabil |
| `export_fahrtenbuch` | – | stabil |
| `import_fahrtenbuch` | `trips` | stabil |
| `log_charge` | `kwh`, `price_kwh`, `start_ts?`, `end_ts?`, `soc_start?`, `soc_end?`, `start_fee?`, `block_fee?`, `time_fee?`, `karte_id?`, `anbieter?` | stabil |
| `log_trip` | `start_ort`, `end_ort`, `start_ts?` | stabil |
| `mark_maintenance_done` | `wartung_id`, `km?`, `datum?` | stabil |
| `rebuild_departure_profile` | `home_ort?` | stabil |
| `reset_lifetime_kpis` | `home_kwh_since_setup?`, `home_cost_since_setup?`, `km_driven?` | stabil |
| `restore_backup` | `backup_data` | stabil |
| `set_evcc_charge_plan` | `target_soc`, `target_time` | stabil |
| `set_evcc_charge_plan_range_km` | `target_range_km`, `target_time` | stabil |
| `set_evcc_manual_mode` | `mode` | stabil |
| `set_evcc_mode_control_pause` | `paused` | stabil |
| `set_evcc_mode_control_target_soc_max` | `target_soc_max?` | stabil |
| `set_evcc_realtime_override_min_solar_share` | `min_solar_share?` | stabil |
| `set_usage_profile_buffer_km` | `buffer_km?` | stabil |
| `set_vehicle_image` | `file_id` | stabil |
| `set_weekly_full_charge_enabled` | `enabled?` | stabil |
| `simulate_event` | `soc_start`, `soc_end`, `energy_source?` | nicht Teil der Zusage (Testwerkzeug) |
| `simulate_trip` | `km` | nicht Teil der Zusage (Testwerkzeug) |
| `urlaub_seit` | `seit_ts` | stabil |

## Entitäten

Die `unique_id` jeder Entität ist `<config_entry_id>_<Schlüssel>`. Der Schlüssel ist stabil; die Entity-ID (`sensor.<name>`) folgt dem übersetzten Namen und den eigenen Umbenennungen des Nutzers.

| Plattform | Schlüssel (unique_id-Suffix) | Name (en) |
|---|---|---|
| binary_sensor | `charge_before_pv_recommended` | Charge Before Solar Recommended |
| binary_sensor | `pending` | External Charge Capture Open |
| binary_sensor | `trip_pending` | Trip Capture Open |
| image | `vehicle_image` | Vehicle image |
| sensor | `ac_charging_kwh` | External Charging AC |
| sensor | `available_kwh` | Available kWh |
| sensor | `battery_capacity` | Battery Capacity (Measured) |
| sensor | `charging_location_breakdown` | Charging Location Breakdown |
| sensor | `co2_savings` | CO2 Savings vs. ICE Vehicle |
| sensor | `cost_day` | Cost (Today) |
| sensor | `cost_month` | Cost (Month) |
| sensor | `cost_week` | Cost (Week) |
| sensor | `cost_year` | Cost (Year) |
| sensor | `count` | External Charge Count |
| sensor | `dc_charging_kwh` | External Charging DC |
| sensor | `equivalent_full_cycles` | Equivalent Full Cycles |
| sensor | `erstzulassung` | First Registration |
| sensor | `evcc_charge_plan` | evcc Charge Plan |
| sensor | `evcc_mode_control` | evcc Mode Control |
| sensor | `home_cost` | Home Charging Cost (total) |
| sensor | `home_kwh` | Home Charging kWh (total) |
| sensor | `home_vs_external_price` | External vs. Home Charging Price Difference |
| sensor | `house_usage_profile` | House Usage Profile |
| sensor | `kwh_day` | kWh (Today) |
| sensor | `kwh_month` | kWh (Month) |
| sensor | `kwh_week` | kWh (Week) |
| sensor | `kwh_year` | kWh (Year) |
| sensor | `ladekarten_kosten` | Charging Card Costs |
| sensor | `last_charge_power` | External Charge Avg Power (last) |
| sensor | `last_cost` | External Charge Cost (last) |
| sensor | `last_duration` | External Charge Duration (last) |
| sensor | `last_kwh` | External Charge kWh (last) |
| sensor | `last_price` | External Charge Price (last) |
| sensor | `last_trip_km` | Trip km (last) |
| sensor | `leasing_km_vor_ruecklauf` | Mileage budget vs. plan |
| sensor | `measured_efficiency` | Charging Efficiency (measured) |
| sensor | `morning_departure` | Typical morning departure |
| sensor | `odo` | Odometer |
| sensor | `odo_annual_from_reg` | Projected km/year (since registration) |
| sensor | `odo_avg_day` | Avg km/day |
| sensor | `odo_avg_month` | Avg km/month |
| sensor | `odo_avg_week` | Avg km/week |
| sensor | `odo_avg_year` | Avg km/year |
| sensor | `odo_day_km` | km driven (today) |
| sensor | `odo_month_km` | km driven (month) |
| sensor | `odo_week_km` | km driven (week) |
| sensor | `odo_year_km` | km driven (year) |
| sensor | `odo_year_projected` | Projected km (calendar year) |
| sensor | `pending_estimate` | External Charge Pending |
| sensor | `plug_window` | Plug Time Window |
| sensor | `range_estimate` | Estimated Range |
| sensor | `savings` | Savings vs. ICE Vehicle |
| sensor | `total_cost` | External Charge Cost (total) |
| sensor | `total_kwh` | External Charge kWh (total) |
| sensor | `total_trip_km` | Trip Log km (total) |
| sensor | `trip_avg_consumption` | Trip Log Avg Consumption |
| sensor | `trip_count` | Trip Log Count |
| sensor | `trip_pending_estimate` | Trip Pending |
| sensor | `usage_profile` | Usage Profile |
| sensor | `usage_profile_tomorrow` | Usage Profile (Needed Tomorrow) |
| sensor | `vehicle_avg_consumption` | Vehicle Avg Consumption |
| sensor | `vehicle_discharge_total` | Live SoC Consumption Total |
| sensor | `verbrenner_price_selected` | Fuel Price (Selected) |
| sensor | `wartung_faellig` | Maintenance Due |

## Config-Flow- und Optionsschlüssel

Gespeichert im Config-Entry (`data`/`options`). Bestehende Installationen laufen ohne Neukonfiguration weiter: Schlüssel werden nicht ohne Migration umbenannt.

| Schritt | Schlüssel | Pflicht |
|---|---|---|
| comparison | `co2_per_kwh_g` | – |
| comparison | `tankerkoenig_fuel_type` | – |
| comparison | `verbrenner_l_100km` | – |
| comparison | `verbrenner_price_entity` | – |
| comparison | `verbrenner_price_per_liter` | – |
| detection | `drop_ends` | – |
| detection | `idle_timeout_s` | – |
| detection | `noise` | – |
| detection | `plug_debounce_s` | – |
| detection | `plug_entity` | – |
| detection | `start_delta` | – |
| evcc | `battery_charge_entity` | – |
| evcc | `evcc_battery_priority_enabled` | – |
| evcc | `evcc_departure_entity` | – |
| evcc | `evcc_departure_fallback_enabled` | – |
| evcc | `evcc_departure_fallback_time` | – |
| evcc | `evcc_host` | – |
| evcc | `evcc_mode_control_enabled` | – |
| evcc | `evcc_mode_control_target_soc_max` | – |
| evcc | `evcc_realtime_override_min_solar_share` | – |
| evcc | `evcc_soft_recharge_enabled` | – |
| evcc | `evcc_vehicle_name` | – |
| evcc | `home_consumption_entity` | – |
| evcc | `pv_forecast_today_remaining_entity` | – |
| evcc | `urlaub_entity` | – |
| evcc | `wallbox_min_power_w` | – |
| evcc | `weekly_full_charge_enabled` | – |
| evcc | `weekly_full_charge_interval_days` | – |
| evcc_loadpoint | `evcc_loadpoint_title` | – |
| heimladen | `battery_charge_entity` | – |
| heimladen | `home_consumption_entity` | – |
| heimladen | `home_feedin_price_entity` | – |
| heimladen | `home_feedin_price_kwh` | – |
| heimladen | `home_price_entity` | – |
| heimladen | `home_price_kwh` | – |
| heimladen | `pv_generation_entity` | – |
| heimladen | `wallbox_charging_entity` | – |
| heimladen | `wallbox_connected_entity` | – |
| heimladen | `wallbox_energy_entity` | – |
| leasing | `leasing_end_datum` | – |
| leasing | `leasing_inkl_km` | – |
| leasing | `leasing_preis_mehr_km` | – |
| leasing | `leasing_preis_minder_km` | – |
| leasing | `leasing_start_datum` | – |
| leasing | `leasing_start_km` | – |
| leasing | `leasing_toleranz_mehr_km` | – |
| leasing | `leasing_toleranz_minder_km` | – |
| modus | `home_charging_method` | ja |
| modus | `lade_modus` | ja |
| output | `notify_entities` | – |
| output | `notify_events` | – |
| output | `soc_thresholds` | – |
| power | `home_entity` | – |
| power | `power_entity` | – |
| power | `power_is_ac` | – |
| trip | `gps_entity` | – |
| trip | `motor_debounce_s` | – |
| trip | `motor_entity` | – |
| trip | `outside_temp_entity` | – |
| trip | `precondition_start_entity` | – |
| trip | `precondition_status_entity` | – |
| trip | `precondition_stop_entity` | – |
| trip | `pv_forecast_entity` | – |
| trip | `trip_auto_confirm` | – |
| trip | `trip_idle_timeout_s` | – |
| trip | `trip_min_km` | – |
| trip | `usage_profile_buffer_km` | – |
| vehicle | `charge_efficiency` | – |
| vehicle | `erstzulassung` | – |
| vehicle | `odo_entity` | – |
| vehicle | `soc_entity` | ja |
| vehicle | `usable_kwh` | ja |
| vehicle | `vehicle_hersteller` | ja |
| vehicle | `vehicle_modell` | ja |

## WebSocket-Befehle

Jeder Befehl nimmt `config_entry_id`. Sie sind die Schnittstelle von Panel und Glow-Karte.

- `ev_assistant/charges`
- `ev_assistant/evcc_sessions`
- `ev_assistant/event_log`
- `ev_assistant/trips`

## Panel-Konfiguration

Das Panel reicht diese Konfiguration an die Glow-Karte weiter. `api_version` wird bei jeder inkompatiblen Änderung der Felder unten, der WebSocket-Befehle oder von `evcc_live` erhöht; die Karte vergleicht sie mit der erwarteten Version und warnt bei Abweichung.

- Aktuelle `api_version`: **1**
- Schlüssel der obersten Ebene: `api_version`, `config_entry_id`, `entities`, `evcc_vehicle_name`, `name`, `title`, `vehicles`
- Schlüssel von `entities` (neben den `unique_id`-Schlüsseln oben, die vorhanden sind, wenn die Entität existiert): `gps_entity`, `home_entity`, `motor_entity`, `odo_entity`, `outside_temp_entity`, `plug_entity`, `power_entity`, `precondition_start_entity`, `precondition_status_entity`, `precondition_stop_entity`, `soc_entity`, `wallbox_charging_entity`, `wallbox_connected_entity`, `wallbox_energy_entity`
