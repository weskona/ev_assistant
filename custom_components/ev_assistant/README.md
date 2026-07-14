# EV Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Version](https://img.shields.io/github/v/release/weskona/ev_assistant)](https://github.com/weskona/ev_assistant/releases)

Detects EV charging sessions **away from your home wallbox** ("Fremdladung") from SoC telemetry, lets you log the actual kWh/price from the receipt, and can automatically calibrate the vehicle's charge efficiency from your real home-charging sessions. Manufacturer-independent — works with any HA entity or MQTT source (WiCAN Pro, evcc/Warp, Stellantis/VW cloud sensors, ...).

**[🇩🇪 Deutsche Version weiter unten](#-deutsch)**

---

## 🇬🇧 English

### Principle

- Home charging is already known via evcc/Warp (or any other "is charging at home" signal).
- **External charging = SoC rises while the home wallbox is NOT charging** (correlation signal `home_charging`). No GPS needed.
- The automatic kWh estimate is only a starting point — the receipt value is the source of truth.
- Charge efficiency (AC→battery) can be **calibrated automatically** from your real home-charging sessions instead of guessing a fixed value (see below).

### Installation

**Via HACS**
1. HACS → Integrations → ⋮ → **Custom repositories**
2. URL: `https://github.com/weskona/ev_assistant` — Category: **Integration**
3. Install EV Assistant, restart Home Assistant

**Manual**
1. Copy `custom_components/ev_assistant/` into `config/custom_components/`
2. Restart Home Assistant

### Configuration

Settings → Devices & Services → **Add integration** → "EV Assistant". Setup is a 5-step flow (also used identically when editing via **Configure**):

1. **Vehicle** — Manufacturer + model (required, e.g. "Peugeot" / "e-2008" — together they become the HA device name), first registration date (optional), usable battery capacity in kWh (required), charge efficiency (optional starting value, see calibration below).
2. **Basic signals** — SoC and home-charging source, each as **HA entity OR MQTT topic** (entity takes priority). At least one source per signal is required (marked with `*`). The SoC entity picker is filtered to `sensor` + `device_class: battery`; the home-charging entity picker to `sensor` + `device_class: power`. If your setup doesn't fit those (e.g. a `binary_sensor`), use the MQTT-topic field instead, or the template field to convert a raw value.
3. **Charging power** (optional) — improves the energy estimate of an external charge beyond plain SoC-delta. Also where you configure a **wallbox energy meter** (cumulative kWh counter) for automatic efficiency calibration.
4. **Output** — MQTT publish topic for detected charges, optional `notify.*` service.
5. **Detection fine-tuning** — thresholds of the underlying state machine (start threshold, noise tolerance, idle timeout, drop-ends threshold). Defaults work for most vehicles.

### Sources: manufacturer-independent

Each signal is fed from either an **HA entity** (e.g. a manufacturer integration) or **MQTT** (e.g. WiCAN Pro) — works with any manufacturer that exposes an SoC sensor in HA.

- **WiCAN Pro (MQTT):** SoC topic `<your_prefix>/telemetry/soc` (template `{{ value }}` or `{{ value_json.soc }}`).
- **Stellantis / VW / ... (entity):** SoC entity = `sensor.<car>_battery`. Cloud SoC is often coarse/infrequent — raise `start_delta` and `idle_timeout_s` accordingly; the power-based path is unavailable without real power data (falls back to SoC × efficiency).
- **Mixed** is fine: SoC from an entity, `home_charging` from evcc MQTT, etc.

An optional Jinja template per signal converts the raw value (`value` = state/payload, `value_json` = parsed JSON payload for MQTT).

### Automatic charge-efficiency calibration

Instead of a fixed manual efficiency value, EV Assistant can learn the real AC→battery efficiency from your own home-charging sessions:

- Configure a **wallbox energy meter** (cumulative kWh counter) in step 3.
- Every time you charge at home, the SoC delta (× usable kWh) is compared against the wallbox's measured AC energy for that same session.
- After **3 valid sessions**, the rolling average automatically replaces the manual value for all calculations — no restart needed. Implausible samples (too short a session, missing data, efficiency outside 50–100%) are discarded automatically.
- The manual value entered in step 1 remains the fallback until enough sessions have been observed.
- See sensor `... Ladewirkungsgrad (gemessen)` for the current calibration status.

### Entities

The HA device is named after the vehicle (`{Manufacturer} {Model}`), so entity names below appear as `{Device} {Entity}`, e.g. "Peugeot e-2008 Fremdladung Anzahl".

- `binary_sensor ... Fremdladung Erfassung offen` — pending, unconfirmed external charge (with attributes)
- `sensor ... Fremdladung Schätzung` — estimated kWh of the pending charge
- `sensor ... Fremdladung Kosten (letzte)`, `... kWh (letzte)`, `... Preis (letzter)`
- `sensor ... Fremdladung kWh (gesamt)`, `... Kosten (gesamt)`, `... Anzahl`
- `sensor ... Ladewirkungsgrad (gemessen)` — calibrated from real **home** charging sessions (not external charges); attributes include sample count, individual samples, and whether the measured value is currently in use

### Services

- `ev_assistant.log_charge` — `config_entry_id`, `kwh`, `price_kwh` (+ optional `start_ts`): confirm the pending charge and write it to history.
- `ev_assistant.discard_pending` — `config_entry_id`: discard the pending charge.
- `ev_assistant.simulate_event` — `config_entry_id`, `soc_start`, `soc_end` (+ `energy_source`): generate a **test event without a car** (triggers notification, MQTT, sensors).

All three services require `config_entry_id` to target a specific vehicle if you run more than one EV Assistant instance.

### Manual-entry UI (optional)

`packages/ev_assistant_ui.yaml` provides two input fields + save/discard buttons wired to the services above; `packages/ev_assistant_karte.yaml` is a matching Lovelace card. Copy into `config/packages/` (`homeassistant: packages: !include_dir_named packages`) and reload.

> **Known limitation:** these package files predate the multi-vehicle (`config_entry_id`) and vehicle-based-device-name changes — the automations don't pass `config_entry_id` yet, and the hardcoded entity id (`sensor.ev_assistant_letzter_preis`) assumes the old fixed device name "EV Assistant" rather than your vehicle's name. Adjust both before relying on this UI if you use it.

### Testing

**1) Logic only (no HA):**
```bash
cd <repo>
python -m pytest tests -q
```
**2) End-to-end in HA (no car needed):** Developer tools → Services → call `ev_assistant.simulate_event` with `config_entry_id`, `soc_start: 32`, `soc_end: 74`. Expect: a notification appears, `binary_sensor ... Fremdladung Erfassung offen` turns on, `sensor ... Fremdladung Schätzung` ≈ 21.5 kWh. Then enter kWh/price and call `ev_assistant.log_charge` (or the save button) — history/totals update, and a publish happens to `ev_assistant/ladung/extern/<entry_id>/erfasst`.

### Data record (history / MQTT `.../erfasst`)

Deliberately contains **both** the manually entered `kwh`/`preis_kwh`/`kosten` **and** the automatic `schaetzung_kwh` plus its `quelle` (`soc`/`power_ac`/`power_dc`) — so you can see over time how close the estimate gets, and adjust `charge_efficiency` accordingly (or just let the automatic calibration handle it).

### Structure

```
custom_components/ev_assistant/
  __init__.py        # setup, services, unload (reload-capable)
  manifest.json
  const.py
  engine.py           # pure logic (pytest-testable) — ChargeDetector + EfficiencyCalibrator
  coordinator.py      # entity/MQTT wiring, detection, calibration, persistence, notification
  config_flow.py      # config + options flow (5 steps)
  entity.py           # shared entity base (device grouping, vehicle-based device name)
  sensor.py
  binary_sensor.py
  services.yaml
  strings.json
  translations/{de,en}.json
packages/             # optional UI glue + Lovelace card (see known limitation above)
tests/                # pytest (engine.py)
```

### Requirements

- Home Assistant 2024.1+
- `mqtt` integration set up (dependency), even if you only use HA-entity sources

---

## 🇩🇪 Deutsch

### Prinzip

- Heim-Laden ist über evcc/Warp (oder ein beliebiges anderes "lädt gerade zuhause"-Signal) ohnehin bekannt.
- **Fremdladen = SoC steigt, während die Heim-Wallbox NICHT lädt** (Korrelationssignal `home_charging`). Kein GPS nötig.
- Die automatische kWh-Schätzung ist nur eine Vorbelegung — der Beleg-Wert ist die Wahrheit.
- Der Ladewirkungsgrad (AC→Batterie) kann **automatisch aus echten Heim-Ladesessions kalibriert werden**, statt einen festen Wert zu raten (siehe unten).

### Installation

**Über HACS**
1. HACS → Integrationen → ⋮ → **Benutzerdefinierte Repositories**
2. URL: `https://github.com/weskona/ev_assistant` — Kategorie: **Integration**
3. EV Assistant installieren, Home Assistant neu starten

**Manuell**
1. Ordner `custom_components/ev_assistant/` nach `config/custom_components/` kopieren
2. Home Assistant neu starten

### Konfiguration

Einstellungen → Geräte & Dienste → **Integration hinzufügen** → „EV Assistant". Die Einrichtung läuft in 5 Schritten (identisch auch beim Bearbeiten über **Konfigurieren**):

1. **Fahrzeug** — Hersteller + Modell (Pflicht, z.B. „Peugeot" / „e-2008" — ergeben zusammen den HA-Gerätenamen), Erstzulassung (optional), nutzbare Akku-Kapazität in kWh (Pflicht), Ladewirkungsgrad (optionaler Startwert, siehe Kalibrierung unten).
2. **Grundsignale** — SoC- und Heim-Laden-Quelle, jeweils als **HA-Entität ODER MQTT-Topic** (Entität hat Vorrang). Mindestens eine Quelle pro Signal ist Pflicht (mit `*` markiert). Der SoC-Entitäts-Picker ist auf `sensor` + `device_class: battery` gefiltert, der Heim-Laden-Picker auf `sensor` + `device_class: power`. Passt das nicht zu deinem Setup (z.B. ein `binary_sensor`), nutze stattdessen das MQTT-Topic-Feld oder das Template-Feld zur Umrechnung.
3. **Ladeleistung** (optional) — verbessert die Energie-Schätzung einer Fremdladung gegenüber der reinen SoC-Delta-Schätzung. Hier wird auch ein **Wallbox-Energiezähler** (kumulativer kWh-Zähler) für die automatische Ladewirkungsgrad-Kalibrierung hinterlegt.
4. **Ausgabe** — MQTT-Publish-Topic für erkannte Ladungen, optionaler `notify.*`-Dienst.
5. **Erkennungs-Feinjustierung** — Schwellwerte der zugrunde liegenden Zustandsmaschine (Start-Schwelle, Rausch-Toleranz, Timeout, Abfall-Schwelle). Die Standardwerte passen für die meisten Fahrzeuge.

### Quellen: herstellerunabhängig

Jedes Signal wird aus einer **HA-Entität** (z.B. Hersteller-Integration) oder aus **MQTT** (z.B. WiCAN Pro) gespeist — funktioniert mit jedem Hersteller, der einen SoC-Sensor in HA bereitstellt.

- **WiCAN Pro (MQTT):** SoC-Topic `<dein_prefix>/telemetrie/soc` (Template `{{ value }}` oder `{{ value_json.soc }}`).
- **Stellantis / VW / … (Entität):** SoC-Entität = `sensor.<auto>_battery`. Cloud-SoC ist oft grob/selten — dann `start_delta` höher und `idle_timeout_s` großzügiger; der Leistungs-Pfad entfällt mangels echter Leistungsdaten (Fallback auf SoC × Wirkungsgrad).
- **Gemischt** ist möglich: SoC aus Entität, `home_charging` aus evcc-MQTT usw.

Ein optionales Jinja-Template pro Signal rechnet den Rohwert um (`value` = Zustand/Payload, `value_json` = geparster JSON-Payload bei MQTT).

### Automatische Ladewirkungsgrad-Kalibrierung

Statt eines festen manuellen Werts kann EV Assistant den echten Ladewirkungsgrad (AC→Batterie) aus deinen eigenen Heim-Ladesessions lernen:

- Im Schritt „Ladeleistung" einen **Wallbox-Energiezähler** (kumulativer kWh-Zähler) hinterlegen.
- Bei jeder Heim-Ladung wird das SoC-Delta (× nutzbare Kapazität) gegen die vom Wallbox-Zähler gemessene AC-Energie derselben Session verglichen.
- Nach **3 gültigen Sessions** übernimmt der gleitende Durchschnitt automatisch alle Berechnungen — kein Neustart nötig. Unplausible Stichproben (Session zu kurz, Daten fehlen, Wirkungsgrad außerhalb 50–100 %) werden automatisch verworfen.
- Der in Schritt 1 eingetragene manuelle Wert bleibt Fallback, bis genug Sessions vorliegen.
- Siehe Sensor „… Ladewirkungsgrad (gemessen)" für den aktuellen Kalibrierungsstatus.

### Entitäten

Das HA-Gerät heißt wie das Fahrzeug (`{Hersteller} {Modell}`), Entitäten erscheinen daher als `{Gerät} {Entität}`, z.B. „Peugeot e-2008 Fremdladung Anzahl".

- `binary_sensor … Fremdladung Erfassung offen` — offene, unbestätigte Fremdladung (mit Attributen)
- `sensor … Fremdladung Schätzung` — geschätzte kWh der offenen Ladung
- `sensor … Fremdladung Kosten (letzte)`, `… kWh (letzte)`, `… Preis (letzter)`
- `sensor … Fremdladung kWh (gesamt)`, `… Kosten (gesamt)`, `… Anzahl`
- `sensor … Ladewirkungsgrad (gemessen)` — aus echten **Heim**-Ladesessions kalibriert (nicht aus Fremdladungen); Attribute enthalten Anzahl Stichproben, Einzelwerte und ob der gemessene Wert gerade verwendet wird

### Services

- `ev_assistant.log_charge` — `config_entry_id`, `kwh`, `price_kwh` (+ optional `start_ts`): offene Ladung bestätigen und in die Historie schreiben.
- `ev_assistant.discard_pending` — `config_entry_id`: offene Ladung verwerfen.
- `ev_assistant.simulate_event` — `config_entry_id`, `soc_start`, `soc_end` (+ `energy_source`): **Testereignis ohne Auto** erzeugen (löst Benachrichtigung, MQTT, Sensoren aus).

Alle drei Services benötigen `config_entry_id`, um bei mehreren EV-Assistant-Instanzen das richtige Fahrzeug anzusprechen.

### UI zur manuellen Eingabe (optional)

`packages/ev_assistant_ui.yaml` liefert zwei Eingabefelder + Speichern/Verwerfen-Buttons, die die obigen Services aufrufen; `packages/ev_assistant_karte.yaml` ist die passende Lovelace-Karte. Nach `config/packages/` kopieren (`homeassistant: packages: !include_dir_named packages`) und neu laden.

> **Bekannte Einschränkung:** Diese Package-Dateien stammen noch aus der Zeit vor Mehrfahrzeug-Unterstützung (`config_entry_id`) und dem fahrzeugbasierten Gerätenamen — die Automationen übergeben noch kein `config_entry_id`, und die fest eingetragene Entity-ID (`sensor.ev_assistant_letzter_preis`) geht vom alten, festen Gerätenamen „EV Assistant" statt deinem Fahrzeugnamen aus. Beides anpassen, falls du diese UI nutzt.

### Testen

**1) Logik (ohne HA):**
```bash
cd <repo>
python -m pytest tests -q
```
**2) Ende-zu-Ende in HA (ohne Auto):** Entwicklerwerkzeuge → Dienste → `ev_assistant.simulate_event` mit `config_entry_id`, `soc_start: 32`, `soc_end: 74` aufrufen. Erwartung: Benachrichtigung erscheint, `binary_sensor … Fremdladung Erfassung offen` = an, `sensor … Fremdladung Schätzung` ≈ 21,5 kWh. Dann kWh/Preis eintragen und `ev_assistant.log_charge` (oder Speichern-Button) — Historie/Summen aktualisieren sich, Publish auf `ev_assistant/ladung/extern/<entry_id>/erfasst`.

### Datensatz (Historie / MQTT `…/erfasst`)

Enthält bewusst **beides**: manuell `kwh`/`preis_kwh`/`kosten` **und** die Auto-`schaetzung_kwh` samt `quelle` (`soc`/`power_ac`/`power_dc`) — so siehst du über die Zeit, wie gut die Schätzung trifft, und kannst `charge_efficiency` nachziehen (oder die automatische Kalibrierung das übernehmen lassen).

### Struktur

```
custom_components/ev_assistant/
  __init__.py        # Setup, Services, Unload (reload-fähig)
  manifest.json
  const.py
  engine.py          # reine Logik (pytest) — ChargeDetector + EfficiencyCalibrator
  coordinator.py     # Entity-/MQTT-Verdrahtung, Erkennung, Kalibrierung, Persistenz, Notification
  config_flow.py     # Config- + Options-Flow (5 Schritte)
  entity.py          # gemeinsame Entity-Basis (Device-Gruppierung, fahrzeugbasierter Gerätename)
  sensor.py
  binary_sensor.py
  services.yaml
  strings.json
  translations/{de,en}.json
packages/            # optionales UI-Glue + Lovelace-Karte (siehe bekannte Einschränkung oben)
tests/               # pytest (engine.py)
```

### Anforderungen

- Home Assistant 2024.1+
- `mqtt`-Integration eingerichtet (Dependency), auch wenn nur HA-Entitäten als Quelle genutzt werden

---

## Lizenz / License

MIT © [weskona](https://github.com/weskona)
