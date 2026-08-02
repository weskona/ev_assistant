# EV Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/v/release/weskona/ev_assistant)](https://github.com/weskona/ev_assistant/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![HA min version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io)

[English](README.md)

Eine umfassende **EV-Monitoring-Integration für Home Assistant**. EV Assistant deckt Heimladen (über evcc), automatische Fremdladungserkennung und -protokollierung, Fahrtenbuch, Ladewirkungsgrad-Kalibrierung, Kostenvergleich gegenüber einem Verbrenner und ein vollständiges EV-Dashboard als dediziertes Seitenleisten-Panel ab. Funktioniert mit jedem Fahrzeug, das einen SoC-Sensor in HA bereitstellt — herstellerunabhängig.

---

## Funktionen

- **Heimladen-Überwachung** — erfasst kWh und Kosten über den Wallbox-Energiezähler und die evcc-Ladehistorie; zeigt die Sitzungshistorie mit SOC-Balken, Solaranteil und Ø-Ladeleistung pro Sitzung.
- **Fremdladungserkennung** — erkennt Ladungen außerhalb des Hauses rein über SoC-Telemetrie (kein GPS, keine Ladesäulenliste). Fordert zur Eingabe der tatsächlichen kWh/Kosten aus dem Kassenbon auf.
- **Automatisches Fahrtenbuch** — erkennt Fahrten anhand des Kilometerstands; Start- und Zielort werden manuell bestätigt. CSV-Export inklusive.
- **Ladewirkungsgrad-Kalibrierung** — lernt den echten AC→Batterie-Wirkungsgrad des Fahrzeugs aus Heimlade-Sitzungen und wendet ihn automatisch auf alle Schätzungen an.
- **Kilometerstand-Statistik** — gefahrene km pro Tag/Woche/Monat/Jahr sowie gleitende Durchschnitte und Kalenderjahrprojektion, basierend auf HA Long-Term Statistics.
- **Kostenvergleich** — vergleicht die gesamten EV-Ausgaben (Heimladen + Fremdladung) mit einem gleichwertigen Verbrenner; wird live in der Fahrzeugkarte angezeigt.
- **Vollständiges Seitenleisten-Panel** — ein eingebautes EV-Dashboard; kein Lovelace-Karten-Setup erforderlich.
- **Mehrfahrzeug-Unterstützung** — pro Fahrzeug einen Integrationseintrag konfigurieren; das Panel zeigt Tabs zum Wechsel zwischen den Fahrzeugen.

---

## Installation

### Über HACS (empfohlen)

1. **HACS** → Integrationen → ⋮ → **Benutzerdefinierte Repositories**
2. URL hinzufügen: `https://github.com/weskona/ev_assistant` — Kategorie: **Integration**
3. **EV Assistant** installieren, dann Home Assistant neu starten.

### Manuell

1. `custom_components/ev_assistant/` in das Verzeichnis `config/custom_components/` kopieren.
2. Home Assistant neu starten.

---

## Konfiguration

**Einstellungen → Geräte & Dienste → Integration hinzufügen → „EV Assistant"**

Die Einrichtung läuft als 7-schrittiger Assistent (derselbe Assistent wird beim Bearbeiten über **Konfigurieren** verwendet):

| Schritt | Was konfiguriert wird |
|---------|-----------------------|
| 1 — Fahrzeug | Hersteller + Modell (Pflicht), Erstzulassungsdatum, Kilometerstand-Entität, nutzbare Akkukapazität in kWh (netto, nicht brutto) und ein Startwert für den Ladewirkungsgrad (wird später automatisch kalibriert). |
| 2 — evcc & Wallbox | Fahrzeugname in evcc (für den Heimladen-Historienfilter) und die Wallbox-Ladeleistungs-Entität (dient als Heimlade-Signal — jeder Wert > 0,1 kW gilt als „lädt zuhause"). |
| 3 — Ladeleistung | Optionaler Fahrzeug-Ladeleistungssensor (verbessert Fremdladungsschätzungen) und Wallbox-Energiezähler (kumulativer kWh-Zähler für Wirkungsgrad-Kalibrierung und Heimlade-Kosten). |
| 4 — Benachrichtigungen | Optionaler `notify.*`-Dienst für Push-Benachrichtigungen bei erkannten Fremdladungen. Eine persistente HA-Benachrichtigung erscheint unabhängig davon immer. |
| 5 — Erkennung | Feinjustierung der Erkennungs-Zustandsmaschine: `start_delta` (minimaler SoC-Anstieg zum Auslösen), `noise` (Jitter-Toleranz, muss < `start_delta` sein), `idle_timeout_s` (Sitzungsende-Timeout), `drop_ends` (SoC-Abfall, der eine Sitzung sofort beendet). Standardwerte funktionieren für die meisten Fahrzeuge. |
| 6 — Fahrtenbuch | Optional: `trip_min_km` (Mindestfahrstrecke), `trip_idle_timeout_s` (Standzeit bis Fahrtende), `gps_entity` (person/device_tracker für Ortsvorschläge). |
| 7 — Kostenvergleich | Optional: Verbrenner-Referenzverbrauch (L/100 km), Kraftstoffpreis, Heimstrompreis — jeweils als fester Wert oder als Live-HA-Entität. |

---

## Sensoren

Das HA-Gerät heißt `{Hersteller} {Modell}` (z. B. „VW ID.4"), Entitätsnamen erscheinen daher als `{Gerät} {Sensor}`.

### Fremdladung

| Key | Name | Beschreibung |
|-----|------|--------------|
| `pending` | Fremdladung Erfassung offen | Binary Sensor — **on**, solange ≥ 1 Ladung auf Bestätigung wartet. Attribute: `anzahl_offen`, `offene_ladungen`. |
| `pending_estimate` | Fremdladung ausstehend | Geschätzte kWh der ältesten offenen Ladung. `unknown`, wenn nichts aussteht. |
| `last_kwh` | Fremdladung kWh (letzte) | kWh aus dem Kassenbon der zuletzt bestätigten Ladung. |
| `last_cost` | Fremdladung Kosten (letzte) | Kosten der zuletzt bestätigten Ladung (kWh × Preis). |
| `last_price` | Fremdladung Preis (letzter) | Eingegebener Preis pro kWh der letzten Ladung. |
| `last_duration` | Fremdladung Ladezeit (letzte) | Dauer der erkannten Sitzung in Minuten. |
| `last_charge_power` | Fremdladung Ø Leistung (letzte) | Durchschnittliche Ladeleistung (kW) der zuletzt bestätigten Ladung, aus kWh ÷ Dauer. Sitzungen < 5 min oder mit unplausibler Leistung (< 1 kW oder > 350 kW) liefern `unknown`. |
| `total_kwh` | Fremdladung kWh (gesamt) | Laufende Summe aller bestätigten Fremdladungs-kWh (`state_class: total_increasing`). |
| `total_cost` | Fremdladung Kosten (gesamt) | Laufende Summe aller bestätigten Fremdladungskosten. |
| `count` | Fremdladung Anzahl | Gesamtanzahl aller bestätigten Fremdladungen. |

### Heimladen

| Key | Name | Beschreibung |
|-----|------|--------------|
| `home_kwh` | Heimladen kWh (gesamt) | Gesamt-kWh seit Einrichtung, aus dem Wallbox-Energiezähler. `unknown` ohne konfigurierten Zähler. |
| `home_cost` | Heimladen Kosten (gesamt) | Heimlade-kWh × Heimstrompreis. `unknown` ohne Zähler oder Preis. |
| `measured_efficiency` | Ladewirkungsgrad (gemessen) | Live-kalibrierter AC→Batterie-Wirkungsgrad aus Heimlade-Sitzungen. Attribute: `anzahl_sessions`, `benoetigte_sessions` (3), `einzelwerte_prozent`, `wird_verwendet`, `manueller_wert_prozent`. Diagnostisch. |

### Kilometerstand & gefahrene Kilometer

Alle Kilometerstand-Sensoren sind `entity_category: diagnostic`. Die Perioden- und LTS-Sensoren setzen voraus, dass die Kilometerstand-Entität in Schritt 1 konfiguriert ist und Long-Term Statistics in HA aufgezeichnet hat.

| Key | Name | Beschreibung |
|-----|------|--------------|
| `odo` | Kilometerstand | Spiegelt die konfigurierte Kilometerstand-Entität auf das EV-Assistant-Gerät. |
| `odo_day_km` | Gefahrene km (heute) | Km seit Beginn des aktuellen Kalendertags. |
| `odo_week_km` | Gefahrene km (Woche) | Km seit Beginn der aktuellen ISO-Woche. |
| `odo_month_km` | Gefahrene km (Monat) | Km seit Beginn des aktuellen Kalendermonats. |
| `odo_year_km` | Gefahrene km (Jahr) | Km seit Beginn des aktuellen Kalenderjahres. |
| `odo_avg_day` | Ø km/Tag | Gleitender 30-Tage-Durchschnitt der täglichen km (aus LTS-Summen-Deltas). |
| `odo_avg_week` | Ø km/Woche | 30-Tage-Durchschnitt, auf pro Woche skaliert. |
| `odo_avg_month` | Ø km/Monat | 90-Tage-Durchschnitt, auf pro Monat skaliert. |
| `odo_avg_year` | Ø km/Jahr | 365-Tage-Durchschnitt, auf pro Jahr skaliert. |
| `odo_year_projected` | Erwartete km (Kalenderjahr) | Extrapoliert km ab dem 1. Januar auf das volle Kalenderjahr. Liefert `unknown`, bis ≥ 7 Tage ins Jahr vergangen sind. |
| `odo_annual_from_reg` | Erwartete km/Jahr (seit Erstzulassung) | Jährliche Rate seit dem in Schritt 1 eingetragenen Erstzulassungsdatum. |

### Fahrtenbuch

| Key | Name | Beschreibung |
|-----|------|--------------|
| `trip_pending` | Fahrt Erfassung offen | Binary Sensor — **on**, solange ≥ 1 erkannte Fahrt auf Start-/Zielort wartet. |
| `trip_pending_estimate` | Fahrt ausstehend | Strecke (km) der ältesten offenen Fahrt. |
| `last_trip_km` | Fahrt km (letzte) | Strecke der zuletzt bestätigten Fahrt. Attribut `fahrtenbuch` enthält die vollständige Historie. |
| `trip_count` | Fahrtenbuch Anzahl | Gesamtanzahl aller bestätigten Fahrten (`state_class: total_increasing`). |
| `total_trip_km` | Fahrtenbuch km (gesamt) | Laufende Summe aller bestätigten Fahrstrecken (`state_class: total_increasing`). |

### Kostenvergleich

| Key | Name | Beschreibung |
|-----|------|--------------|
| `savings` | Ersparnis ggü. Verbrenner | Geschätzte Ersparnis gegenüber dem Verbrenner-Referenzfahrzeug über die seit Einrichtung gefahrenen km. `unknown`, bis Kilometerstand, Verbrenner-Verbrauch und Kraftstoffpreis konfiguriert sind. Attribute: `gefahrene_km`, `heimladen_kosten`, `kosten_ev_gesamt`, `kosten_verbrenner_geschaetzt`, `kraftstoffpreis_live`, `heimstrompreis_live`. |
| `erstzulassung` | Erstzulassung | Erstzulassungsdatum aus Schritt 1, als `date`-typisierter Sensor. Diagnostisch. |

---

## Panel / Dashboard

EV Assistant registriert automatisch ein **Seitenleisten-Panel** — keine zusätzliche Einrichtung über die Integration selbst hinaus erforderlich.

### Tab „Übersicht"

Live-Energieflussdiagramm mit aktueller PV-, Netz-, Haus-, Speicher- und Wallbox-Leistung. Zeigt die aktive Ladesitzung (Modus, SOC, Sitzungsenergie, Solaranteil, Tarif) sowie ausstehende Fremdladungen oder Fahrten, die auf Bestätigung warten.

### Tab „Fahrzeuge"

Fahrzeugspezifisches Dashboard in einem Drei-Spalten-Layout:

| Spalte | Inhalt |
|--------|--------|
| **Heimladen** | Heimlade-Gesamtwerte (kWh, EUR, Sitzungsanzahl, Ø Solaranteil), letzte Sitzungs-KPIs, vollständige evcc-Sitzungshistorie. Jeder Eintrag zeigt SOC Start→Ende, kWh, Ø Ladeleistung, EUR/kWh, Kosten, Solaranteil, Dauer und einen SOC-Balken. |
| **Fremdladung** | Fremdladungs-Gesamtwerte, letzte Sitzungs-KPIs, editierbare Historie. Jeder Eintrag zeigt kWh, Ø Ladeleistung, Kosten und einen SOC-Balken. |
| **Fahrtenbuch** | Fahrt-Gesamtwerte, letzte Fahrt-KPIs (km, Route), editierbare Fahrthistorie. |

**Fahrzeugkarte** (über den drei Spalten): Fahrzeugname, aktueller SOC mit farbkodiertem Balken (rot < 20 %, orange < 40 %, sonst grün), Kilometerstand und Ladewirkungsgrad. Darunter: ein kompaktes km-Grid (gefahrene km heute/Woche/Monat/Jahr links, gleitende Durchschnitte und Projektionen rechts) sowie der Verbrenner-Vergleich (Ersparnis, EV-Kosten, Verbrenner-Kosten, Kosten pro 100 km).

**Balkendiagramme**: Ladeübersicht, Kostenübersicht und Solaranteil — umschaltbar zwischen Wochen-, Monats- und Jahresansicht mit Vor-/Zurück-Navigation. Mobil-responsiv: auf Bildschirmen ≤ 600 px stapeln sich die drei Diagramme vertikal.

---

## Dienste

Alle Dienste benötigen `config_entry_id`, um bei mehreren konfigurierten Einträgen das richtige Fahrzeug anzusprechen.

| Dienst | Parameter | Beschreibung |
|--------|-----------|--------------|
| `log_charge` | `config_entry_id`, `kwh`, `price_kwh`, `start_ts`* | Ausstehende Fremdladung mit Kassenbon-Werten bestätigen. `start_ts` wählt die Ladung aus (älteste, wenn weggelassen). |
| `discard_pending` | `config_entry_id`, `start_ts`* | Ausstehende Fremdladung verwerfen (Fehlalarm). |
| `edit_charge` | `config_entry_id`, `erfasst_ts`, `kwh`, `price_kwh` | kWh/Preis eines bereits bestätigten Historieneintrags korrigieren. Gesamtsummen werden um die Differenz angepasst. |
| `delete_charge` | `config_entry_id`, `erfasst_ts` | Bestätigten Historieneintrag entfernen. **Nicht rückgängig machbar.** |
| `simulate_event` | `config_entry_id`, `soc_start`, `soc_end`, `energy_source`* | Test-Fremdladungsereignis ohne Auto auslösen. |
| `log_trip` | `config_entry_id`, `start_ort`, `end_ort`, `start_ts`* | Ausstehende Fahrt mit Start-/Zielort bestätigen. |
| `discard_pending_trip` | `config_entry_id`, `start_ts`* | Ausstehende Fahrt verwerfen. |
| `edit_trip` | `config_entry_id`, `erfasst_ts`, `start_ort`, `end_ort` | Start-/Zielort eines bestätigten Fahrtenbucheintrags korrigieren. |
| `delete_trip` | `config_entry_id`, `erfasst_ts` | Bestätigten Fahrtenbucheintrag entfernen. **Nicht rückgängig machbar.** |
| `export_fahrtenbuch` | `config_entry_id` | Vollständige Fahrthistorie als CSV in `www/ev_assistant_fahrtenbuch_<entry_id>.csv` schreiben. |
| `simulate_trip` | `config_entry_id`, `km` | Test-Fahrtereignis ohne Auto auslösen. |

*optional

---

## Wie die Fremdladungserkennung funktioniert

EV Assistant benötigt kein GPS, keine Hersteller-API und keine Ladesäulenliste. Das Prinzip in einem Satz: **Steigt der Batterie-SoC, während das Heimlade-Signal inaktiv ist, muss das Auto woanders laden**.

Eine kleine Zustandsmaschine (`engine.py::ChargeDetector`) überwacht jeden SoC-Messwert. Sie verfolgt den letzten Ruhepunkt als „Anker". Sobald der SoC *ohne aktives Heimlade-Signal* um ≥ `start_delta` über den Anker gestiegen ist, beginnt eine Sitzung. Sie endet, wenn das Heimlade-Signal aktiv wird, der SoC um > `drop_ends` unter den verfolgten Höchstwert fällt oder `idle_timeout_s` ohne neuen Höchstwert verstreicht.

Die Energie wird aus SoC-Delta × nutzbarem Akku ÷ Ladewirkungsgrad geschätzt — oder, wenn ein Fahrzeug-Ladeleistungssensor konfiguriert ist, aus der integrierten Leistungskurve (genauer, funktioniert auch unterwegs ohne Wallbox-Daten).

---

## Automatische Wirkungsgrad-Kalibrierung

Einen **Wallbox-Energiezähler** konfigurieren (Schritt 3 — kumulativer kWh-Zähler). Für jede Heimlade-Sitzung erfasst EV Assistant die bezogene Wallbox-Energie und den SoC-Gewinn und berechnet:

```
Wirkungsgrad = (SoC-Gewinn% × nutzbare_kWh) ÷ Wallbox_kWh_Delta
```

Nach 3 gültigen Sitzungen (≥ 5 Prozentpunkte SoC-Gewinn, Ergebnis im Bereich 50–100 %) wird der Durchschnitt der letzten 10 Messwerte gebildet und automatisch angewendet — kein Neustart erforderlich. Der Sensor `Ladewirkungsgrad (gemessen)` zeigt den aktuellen Wert und seinen Status.

---

## Voraussetzungen

- **Home Assistant 2024.1** oder neuer
- **evcc_intg** — optional, aber erforderlich für die Heimladen-Historie und Live-Energieflussdaten im Panel
- Beliebiges Fahrzeug mit SoC-Sensor in HA (WiCAN Pro / MQTT, Hersteller-Cloud-Integrationen, evcc-Fahrzeugsensoren, ...)

---

## Testen

**Unit-Tests (kein HA erforderlich):**
```bash
python -m pytest tests -q
```

**End-to-End in HA (kein Auto erforderlich):**
- Fremdladung: `ev_assistant.simulate_event` aufrufen mit `config_entry_id`, `soc_start: 32`, `soc_end: 74`. Eine Benachrichtigung und `binary_sensor ... Fremdladung Erfassung offen` sollten aktiv werden. Im Panel bestätigen.
- Fahrt: `ev_assistant.simulate_trip` aufrufen mit `config_entry_id`, `km: 12.5`. Im Panel bestätigen, dann `export_fahrtenbuch` aufrufen und die CSV in `www/` prüfen.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
