# ev_assistant — Fremdladung erfassen (fahrzeugunabhaengig)

Erkennt Ladevorgänge **außerhalb des Eigenheims** aus der SoC-Telemetrie
(WiCAN Pro) und lässt dich die am Ladepunkt abgerechneten **kWh und den Preis
pro kWh manuell erfassen**. Persistenz via HA Store, Sensoren, MQTT-Publish,
Benachrichtigung. Erkennungslogik (`engine.py`) ist HA-frei und per `pytest`
testbar.

## Prinzip
- Heim-Laden ist über evcc/Warp ohnehin bekannt.
- **Fremdladen = SoC steigt, während die Heim-Wallbox nicht lädt**
  (Korrelationssignal `home_charging`). Kein GPS nötig.
- Automatische kWh-Schätzung ist nur Vorbelegung — dein Beleg-Wert ist die Wahrheit.

## Installation
1. Ordner `custom_components/ev_assistant/` nach `config/custom_components/` kopieren.
2. Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → **Integration hinzufügen** → „EV Assistant".
4. Quelle je Signal wählen — **HA-Entität ODER MQTT-Topic** (Entität hat Vorrang):
   - SoC (Pflicht): entweder eine Entität oder ein Topic
   - Heim-Laden (evcc/Warp): „on/true/1/charging" = lädt
   - Ladeleistung (optional)
   - Publish-Topic: `ev_assistant/ladung/extern`, notify-Service optional
   - Nutzbare kWh: `45`, Wirkungsgrad: `0.88`, Ladeleistung AC-seitig: an/aus

Alle Felder (auch Quellen) sind später über **Konfigurieren** (Options-Flow)
änderbar — so lässt sich die Quelle jederzeit umschalten.

## Quellen: herstellerunabhängig
Jedes Signal wird aus einer **HA-Entität** (z.B. Hersteller-Integration) oder
aus **MQTT** (z.B. WiCAN Pro) gespeist. So funktioniert es mit jedem Hersteller,
der einen SoC-Sensor in HA bereitstellt.

- **WiCAN Pro (MQTT):** SoC-Topic `<dein_prefix>/telemetrie/soc`
  (Template `{{ value }}` oder `{{ value_json.soc }}`).
- **Stellantis / VW / … (Entität):** SoC-Entität = `sensor.<auto>_battery`.
  Cloud-SoC ist grob/selten — dann `start_delta` höher und `idle_timeout_s`
  großzügiger; der Leistungs-Pfad entfällt mangels Leistungsdaten (SoC×η).
- **Gemischt** möglich: SoC aus Entität, `home_charging` aus evcc-MQTT usw.

Bei Bedarf ein optionales Template pro Signal (`value` = Zustand/Payload,
`value_json` = geparster JSON-Payload bei MQTT).

## UI (manuelle Eingabe)
`packages/ev_assistant_ui.yaml` nach `config/packages/` legen
(`homeassistant: packages: !include_dir_named packages`) und HA neu laden.
Liefert zwei Eingabefelder + Speichern/Verwerfen-Buttons, die die Services
aufrufen. `packages/ev_assistant_karte.yaml` als Karte einfügen.
Hinweis: Entity-IDs der Sensoren entstehen aus dem Gerätenamen
„EV Assistant" (z.B. `sensor.ev_assistant_letzter_preis`) —
bei abweichender Benennung in der Karte/Automation anpassen.

## Services
- `ev_assistant.log_charge` — `kwh`, `price_kwh` (+ optional `start_ts`): offene
  Ladung bestätigen und in die Historie schreiben.
- `ev_assistant.discard_pending` — offene Ladung verwerfen.
- `ev_assistant.simulate_event` — `soc_start`, `soc_end` (+ `energy_source`):
  **Testereignis ohne Auto** erzeugen (löst Notification, MQTT, Sensoren aus).

## Testen
**1) Logik (ohne HA):**
```bash
cd <repo>
python -m pytest tests -q
```
**2) Ende-zu-Ende in HA (ohne Auto):** Entwicklerwerkzeuge → Dienste →
`ev_assistant.simulate_event` mit `soc_start: 32`, `soc_end: 74` aufrufen.
Erwartung: Benachrichtigung erscheint, `binary_sensor …erfassung_offen` = an,
`sensor …schaetzung_offen` ≈ 21,5 kWh. Dann kWh/Preis eintragen und
`ev_assistant.log_charge` (oder Speichern-Button) — Historie/Summen aktualisieren
sich, Publish auf `ev_assistant/ladung/extern/erfasst`.

## Entitäten
- `binary_sensor …erfassung_offen` — offene, unbestätigte Ladung (mit Attributen)
- `sensor …schaetzung_offen` — geschätzte kWh der offenen Ladung
- `sensor …letzte_kosten`, `…letzte_kwh`, `…letzter_preis`
- `sensor …kwh_gesamt`, `…kosten_gesamt`, `…anzahl_ladungen`

## Datensatz (Historie / MQTT `…/erfasst`)
Enthält bewusst **beides**: manuell `kwh`/`preis_kwh`/`kosten` **und** die
Auto-`schaetzung_kwh` samt `quelle` (`soc`/`power_ac`/`power_dc`) — so siehst du
über die Zeit, wie gut die Schätzung trifft, und kannst `charge_efficiency`
nachziehen.

## Struktur
```
custom_components/ev_assistant/
  __init__.py        # Setup, Services, Unload (reload-fähig)
  manifest.json
  const.py
  engine.py          # reine Logik (pytest) — teilbar mit ev_profile
  coordinator.py     # MQTT-Abo, Erkennung, Persistenz, Notification
  config_flow.py     # Config- + Options-Flow
  entity.py          # gemeinsame Entity-Basis (Device-Gruppierung)
  sensor.py
  binary_sensor.py
  services.yaml
  strings.json
  translations/{de,en}.json
packages/            # optionales UI-Glue + Lovelace-Karte
tests/               # pytest (engine)
```
