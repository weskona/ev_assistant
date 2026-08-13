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
- **Kostenvergleich** — vergleicht die gesamten EV-Ausgaben (Heimladen + Fremdladung) mit einem gleichwertigen Verbrenner; wird live in der Fahrzeugkarte angezeigt. Kraftstoffpreis kann ein fester Wert, eine Live-Entität oder automatische Tankerkönig-Tankstellenabfrage sein (günstigste geöffnete Station), mit stabilem Fallback, falls die Preisquelle mal ausfällt.
- **Fahrtenbuch-Import** — historische Fahrten aus einer anderen Fahrtenbuch-App/einem Export per Service-Aufruf in einem Rutsch importieren, für einen einmaligen Rückstand ohne die Kilometerstand-Erkennung.
- **Vollständiges Seitenleisten-Panel** — ein eingebautes EV-Dashboard; kein Lovelace-Karten-Setup erforderlich.
- **Mehrfahrzeug-Unterstützung** — pro Fahrzeug einen Integrationseintrag konfigurieren; das Panel zeigt Tabs zum Wechsel zwischen den Fahrzeugen.
- **Diagnose** — lädt eine anonymisierte Config- und Zustands-Momentaufnahme herunter (Einstellungen → Geräte & Dienste → EV Assistant → ⋮ → Diagnose herunterladen), für Fehlersuche oder Bug-Reports.
- **Repair-Hinweise bei hängenden Sensoren** — fällt eine konfigurierte Quell-Entität (SoC, Kilometerstand, Stecker-Sensor, ...) für mindestens 30 Minuten aus oder wird entfernt, zeigt ein Repair-Hinweis (Einstellungen → System → Repariere) genau, was betroffen ist, statt dass Schätzungen unbemerkt mit veralteten Daten weiterlaufen.

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
| 4 — Benachrichtigungen | Push-Zielgeräte (`notify.*`-Entitäten, Mehrfachauswahl) und welche Ereignisse einen Push auslösen: Fremdladung erkannt, SoC-Schwelle erreicht, Fahrt erkannt, Tankerkönig nicht verfügbar. SoC-Schwellenwerte (50/60/70/80/90/100 %) lösen einmal pro Ladevorgang — Heim- oder Fremdladung — aus, wenn der Akku sie erreicht. Eine persistente HA-Benachrichtigung für Fremdladung/Fahrt/Tankerkönig erscheint unabhängig von diesem Schritt immer. |
| 5 — Erkennung | Feinjustierung der Erkennungs-Zustandsmaschine: `start_delta` (minimaler SoC-Anstieg zum Auslösen), `noise` (Jitter-Toleranz, muss < `start_delta` sein), `idle_timeout_s` (Sitzungsende-Timeout), `drop_ends` (SoC-Abfall, der eine Sitzung sofort beendet). Standardwerte funktionieren für die meisten Fahrzeuge. Optional: `plug_entity` (ein Stecker-/Connectivity-`binary_sensor`) und `plug_debounce_s` — wenn gesetzt, überstimmt ein bestätigtes „eingesteckt" `idle_timeout_s` komplett (keine Fehl-Splits mehr bei grob gemeldetem SoC), ein bestätigtes „ausgesteckt" (muss `plug_debounce_s` lang anhalten, zur Absicherung gegen kurze Fehlmeldungen) beendet die Sitzung sofort, und ein SoC-Anstieg bei bestätigt ausgestecktem Fahrzeug startet gar keine Sitzung mehr (verhindert, dass ein Rekuperations-Anstieg beim Fahren fälschlich als Fremdladung gewertet wird). |
| 6 — Fahrtenbuch | Optional: `trip_min_km` (Mindestfahrstrecke), `trip_idle_timeout_s` (Standzeit bis Fahrtende), `gps_entity` (person-, device_tracker- oder sensor-Entität für Ortsvorschläge). Ebenfalls optional: `motor_entity` (ein Motor-/Fahr-`binary_sensor`, z.B. Zündung/„Ready“) und `motor_debounce_s` — ein zweites Signal für Fahrzeuge, deren Kilometerstand zu grob/selten aktualisiert wird, um Fahrtbeginn/-ende direkt daraus abzuleiten. Ein bestätigtes „fährt“ startet/verlängert eine Fahrt auch ohne frischen Kilometerstand; `trip_idle_timeout_s` toleriert weiterhin kurze Stopps (z.B. Ampel). Die Strecke stammt trotzdem immer aus dem Kilometerstand. Ein weiterer optionaler Schalter, `trip_auto_confirm`, übernimmt eine erkannte Fahrt sofort ins Fahrtenbuch statt auf eine manuelle Start-/Zielort-Bestätigung zu warten — der Ort kommt dabei aus `gps_entity`, falls konfiguriert, sonst bleibt er leer (später per `edit_trip` nachtragbar). Ein weiteres optionales Feld, `usage_profile_buffer_pct` (Standard 20), legt den Sicherheitspuffer auf den historischen Wochentags-Schnitt für den "morgen benötigt"-Wert im Nutzungsprofil-Tab fest. Ein weiteres optionales Feld, `pv_forecast_entity`, verweist auf eine beliebige Sensor-Entität mit der PV-Ertragsprognose für morgen (z.B. von Solcast oder Forecast.Solar, in kWh oder Wh) — damit darf die morgen erwartete PV-Erzeugung eine Lücke schließen, die der aktuelle Akkustand allein nicht abdeckt; ohne sie vergleicht die Lade-Empfehlung nur den aktuellen Akkustand gegen den typischen Bedarf von morgen. Ein weiteres optionales Feld, `outside_temp_entity` (ein normaler Temperatursensor oder eine `weather.*`-Entität), gruppiert den Fahrtenbuch-Verbrauch in vier Temperaturbänder (<0°C, 0–10°C, 10–20°C, >20°C) — sobald ein Band mindestens 3 Fahrten hat, nutzt `range_estimate` dessen Schnitt statt des rollierenden Gesamtwerts, für eine realistischere Schätzung bei Kälte. |
| 7 — Kostenvergleich | Optional: Verbrenner-Referenzverbrauch (L/100 km), Kraftstoffpreis, Heimstrompreis. Kraftstoffpreis-Priorität: Tankerkönig-Auto-Erkennung (Kraftstoffsorte wählen, günstigste offene Tankstelle gewinnt) > Live-Entität > fester Wert. Heimstrompreis: Live-Entität (kWh-gewichteter Durchschnitt) > fester Wert. Ebenfalls optional: `co2_per_kwh_g` (Netzstrom-CO2-Intensität, g/kWh, Standard 380 — eine grobe Schätzung für den deutschen Strommix, an den eigenen Versorger/Tarif anpassen) für den CO2-Vergleichssensor. |

---

## Sensoren

Das HA-Gerät heißt `{Hersteller} {Modell}` (z. B. „VW ID.4"), Entitätsnamen erscheinen daher als `{Gerät} {Sensor}`.

### Fremdladung

| Key | Name | Beschreibung |
|-----|------|--------------|
| `pending` | Fremdladung Erfassung offen | Binary Sensor — **on**, solange ≥ 1 Ladung auf Bestätigung wartet. Attribute: `anzahl_offen`, `offene_ladungen`. |
| `pending_estimate` | Fremdladung ausstehend | Geschätzte kWh der ältesten offenen Ladung. `unknown`, wenn nichts aussteht. |
| `last_kwh` | Fremdladung kWh (letzte) | kWh aus dem Kassenbon der zuletzt bestätigten Ladung. |
| `last_cost` | Fremdladung Kosten (letzte) | Kosten der zuletzt bestätigten Ladung (kWh × Preis, zzgl. eventueller `start_fee`). |
| `last_price` | Fremdladung Preis (letzter) | Eingegebener Preis pro kWh der letzten Ladung. |
| `last_duration` | Fremdladung Ladezeit (letzte) | Dauer der erkannten Sitzung in Minuten. |
| `last_charge_power` | Fremdladung Ø Leistung (letzte) | Durchschnittliche Ladeleistung (kW) der zuletzt bestätigten Ladung, aus kWh ÷ Dauer. Sitzungen < 5 min oder mit unplausibler Leistung (< 1 kW oder > 350 kW) liefern `unknown`. |
| `total_kwh` | Fremdladung kWh (gesamt) | Laufende Summe aller bestätigten Fremdladungs-kWh (`state_class: total_increasing`). |
| `total_cost` | Fremdladung Kosten (gesamt) | Laufende Summe aller bestätigten Fremdladungskosten. |
| `count` | Fremdladung Anzahl | Gesamtanzahl aller bestätigten Fremdladungen. |

### Heimladen

| Key | Name | Beschreibung |
|-----|------|--------------|
| `home_kwh` | Heimladen kWh (gesamt) | Gesamt-kWh Heimladen — vollständige kumulative evcc-Historie. Bevorzugt evccs eigene Fahrzeug-Session-Daten, dann evccs standortweite „gesamt geladene Energie"-Statistik (nur wenn für dieses Fahrzeug auch ein Wallbox-Zähler konfiguriert ist — diese Statistik ist nicht pro Fahrzeug), sonst Fallback auf den Wallbox-Energiezähler-Delta seit EV-Assistant-Einrichtung. `unknown` ohne konfigurierten Zähler. |
| `home_cost` | Heimladen Kosten (gesamt) | Heimlade-Kosten — vollständige kumulative evcc-Historie. Bevorzugt die von evcc direkt gemeldeten Fahrzeugkosten (`sensor.evcc_charging_sessions_vehicles`, am genauesten — evcc wendet den tatsächlichen Sitzungstarif an), dann evccs standortweite Durchschnittspreis-Statistik × kWh (gleiche Fahrzeug-Absicherung wie oben), sonst Fallback auf kWh × Heimstrompreis (kWh-gewichtet, wenn der Preis aus einer Live-Entität kommt — eine Preisspitze ohne jede Ladung verzerrt den Durchschnitt dann nicht). `unknown` ohne Zähler oder Preis. |
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
| `last_trip_km` | Fahrt km (letzte) | Strecke der zuletzt bestätigten Fahrt. Attribut `fahrtenbuch` enthält die vollständige Historie. Einträge ohne direkt gemeldeten Verbrauch erhalten ihren `verbrauch_kwh`-Wert aus dem SoC-Abfall während der Fahrt geschätzt; liegt diese Schätzung außerhalb eines plausiblen Bands von ca. 8–40 kWh/100 km (Fahrten unter 5 km sind ausgenommen), wird der Eintrag mit `verbrauch_unsicher: true` markiert — im Panel mit ⚠️ angezeigt — da eine Verbindungslücke zum Fahrzeug während der Fahrt den SoC-Wert einfrieren und die Schätzung stark verzerren kann. Wird zurückgesetzt, sobald über `edit_trip` ein echter Wert eingetragen wird. |
| `trip_count` | Fahrtenbuch Anzahl | Gesamtanzahl aller bestätigten Fahrten (`state_class: total_increasing`). |
| `total_trip_km` | Fahrtenbuch km (gesamt) | Laufende Summe aller bestätigten Fahrstrecken (`state_class: total_increasing`). |
| `trip_avg_consumption` | Fahrtenbuch Durchschnittsverbrauch | Durchschnittlicher Verbrauch in kWh pro Fahrt, über alle Fahrten mit bekanntem Verbrauch (direkt importiert oder aus dem SoC-Delta erkannter Fahrten abgeleitet). `unknown` ohne nutzbare Daten. |

### Kostenvergleich

| Key | Name | Beschreibung |
|-----|------|--------------|
| `savings` | Ersparnis ggü. Verbrenner | Geschätzte Ersparnis gegenüber dem Verbrenner-Referenzfahrzeug über die seit Einrichtung gefahrenen km. `unknown`, bis Kilometerstand, Verbrenner-Verbrauch und Kraftstoffpreis konfiguriert sind. Attribute: `gefahrene_km`, `heimladen_kosten` (Heimlade-Kosten seit EV-Assistant-Einrichtung — separate Basislinie, unabhängig vom vollen evcc-Gesamtwert des Anzeigesensors), `kosten_ev_gesamt`, `kosten_verbrenner_geschaetzt`, `kraftstoffpreis_live` (Live-/Auto-Kraftstoffpreis aktiv), `heimstrompreis_live`. |
| `verbrenner_price_selected` | Kraftstoffpreis (ausgewählt) | Der aktuell geltende Rohpreis (Tankerkönig / Live-Entität / fester Wert), mit dem Attribut `quelle`, das die aktive Quelle benennt. Über HA Long-Term Statistics historisierbar. |
| `vehicle_avg_consumption` | Fahrzeug Durchschnittsverbrauch | Gesamt-Durchschnittsverbrauch in kWh/100 km seit Einrichtung, aus der Energiebilanz: geladene kWh gesamt (Heim + Fremd) ÷ gefahrene km. `unknown` ohne Kilometerstand-Tracking. |
| `range_estimate` | Geschätzte Reichweite | Aktueller SoC × nutzbare Akkukapazität ÷ tatsächlicher Verbrauch (kWh/100 km) — nutzt den Schnitt des aktuellen Temperaturbands, falls genug Fahrten vorliegen (siehe `outside_temp_entity`, Schritt 6), sonst den rollierenden 30-Tage/50-km-Fahrtenbuch-Schnitt, sonst den Lebenszeit-Schnitt `vehicle_avg_consumption`. Attribute: `verbrauch_kwh_100km` (verwendeter Verbrauchswert), `aussentemperatur`/`temperaturband_aktuell` (aktuelle Temperatur und ihr Band, falls `outside_temp_entity` konfiguriert), `verbrauch_nach_temperatur` (vollständige Aufschlüsselung je Band). `unknown` ohne SoC oder ohne jeden Verbrauchswert. |
| `battery_capacity` | Batteriekapazität (gemessen) | Rollierender Schnitt der impliziten Akkukapazität aus der eigenen Ladehistorie: Fremdladungen mit ≥20 Prozentpunkten SoC-Hub (kWh von der Rechnung ÷ SoC-Delta), plus Heim-Ladesessions, sobald ein gemessener Ladewirkungsgrad vorliegt (Wallbox-kWh × Wirkungsgrad ÷ SoC-Delta). Der absolute Wert liegt typischerweise *über* der echten nutzbaren Kapazität — Ladeverluste werden nicht herausgerechnet, dafür gibt es keinen unabhängigen zweiten Messwert (anders als beim AC-Wirkungsgrad beim Heimladen). Über Monate/Jahre beobachten, um Alterung zu erkennen — ein Absinken ist das eigentliche Signal, nicht die einzelne aktuelle Zahl. `unknown` bei weniger als 2 qualifizierenden Sessions. |
| `co2_savings` | CO2-Ersparnis ggü. Verbrenner | Geschätzte CO2-Ersparnis gegenüber dem Verbrenner-Referenzfahrzeug über die seit Einrichtung gefahrenen km: (Verbrenner-Kraftstoffverbrauch × dessen CO2-Faktor) − (EV-kWh-Verbrauch × `co2_per_kwh_g`). Dieselbe Energiebilanz wie `vehicle_avg_consumption`. `unknown`, bis Kilometerstand und Verbrenner-Verbrauch konfiguriert sind. Attribute: `co2_ev_kg`, `co2_verbrenner_kg`, `co2_ersparnis_kg`. |
| `home_vs_external_price` | Preisunterschied Fremd- vs. Heimladen | Gewichteter Durchschnittspreis für Fremdladen minus Heimstrompreis (beide €/kWh, seit Einrichtung). Positiv heißt Fremdladen war pro kWh teurer — der Normalfall. `unknown` ohne Heimstrompreis oder solange noch keine Fremdladung bestätigt wurde. Attribute: `heimladen_preis_kwh`, `fremdladen_preis_kwh`, `differenz_kwh`. |
| `cost_day` / `cost_week` / `cost_month` / `cost_year` | Kosten (heute/Woche/Monat/Jahr) | Kombinierte Heim- + Fremdladekosten innerhalb des aktuellen Kalender-Zeitraums, gleiches Rollover-Muster wie die Kilometer-Perioden-Sensoren unten. `unknown`, solange die Perioden-Basislinie noch nicht gesetzt ist (direkt nach Einrichtung); auf 0 geklemmt statt negativ zu werden, wenn die Gesamtkosten kurz unter die Perioden-Basislinie fallen (z.B. wenn der gewichtete Durchschnittspreis der Heimladen-Schätzung durch eine neue, günstigere Session leicht sinkt). |
| `erstzulassung` | Erstzulassung | Erstzulassungsdatum aus Schritt 1, als `date`-typisierter Sensor. Diagnostisch. |

### Nutzungsprofil

Siehe „Nutzungsprofil-Tab" oben für die zugrundeliegende Idee.

| Key | Name | Beschreibung |
|-----|------|--------------|
| `usage_profile` | Nutzungsprofil | Durchschnittlicher kWh-Verbrauch am heutigen Wochentag, aus dem Fahrtenbuch (`verbrauch_kwh` pro Fahrt, falls bekannt, sonst deren `km` × `vehicle_avg_consumption` als Schätzung). Attribute: `montag`…`sonntag` (alle 7 Wochentags-Schnitte). `unknown` bei weniger als 7 Tagen Fahrtenbuch-Historie (garantiert, dass jeder Wochentag mindestens einmal beobachtet wurde). |
| `usage_profile_tomorrow` | Nutzungsprofil (morgen benötigt) | Morgiger Wochentags-Schnitt zzgl. `usage_profile_buffer_pct` Puffer — direkt mit `available_kwh` vergleichbar. Attribute: `wochentag`, `roh_kwh` (ungepuffert), `puffer_prozent`, `benoetigt_kwh` (identisch mit dem Zustand). |
| `available_kwh` | Verfügbare kWh | Aktueller SoC × nutzbare Akkukapazität. |
| `binary_sensor … Laden vor PV empfehlenswert` | **On**, wenn `available_kwh` kleiner ist als der gepufferte Wert von `usage_profile_tomorrow` — d.h. jetzt laden (z.B. aus dem Netz) ist sinnvoller, als auf den PV-Überschuss von morgen zu warten. Falls `pv_forecast_entity` konfiguriert ist, wird die morgige PV-Ertragsprognose vor diesem Vergleich zu `available_kwh` addiert — eine Lücke, die der Akku allein nicht deckt, kann so trotzdem unkritisch sein, wenn genug Sonne erwartet wird. Attribute: `verfuegbare_kwh`, `benoetigt_morgen_kwh`, `pv_prognose_morgen_kwh` (nur vorhanden, wenn `pv_forecast_entity` konfiguriert und auflösbar ist). `unknown` unter denselben Bedingungen wie `usage_profile`. |

---

## Panel / Dashboard

EV Assistant registriert automatisch ein **Seitenleisten-Panel** — keine zusätzliche Einrichtung über die Integration selbst hinaus erforderlich.

### Tab „Übersicht"

Live-Energieflussdiagramm mit aktueller PV-, Netz-, Haus-, Speicher- und Wallbox-Leistung. Zeigt die aktive Ladesitzung (Modus, SOC, Sitzungsenergie, Solaranteil, Tarif) sowie ausstehende Fremdladungen oder Fahrten, die auf Bestätigung warten. Der SOC-Balken („Fahrzeug-Akku") liest die in Schritt 1 konfigurierte `soc_entity`; Fallback auf den evcc-Fahrzeug-SOC, wenn keine `soc_entity` gesetzt ist.

### Tab „Fahrzeuge"

Fahrzeugspezifisches Dashboard in einem Drei-Spalten-Layout:

| Spalte | Inhalt |
|--------|--------|
| **Heimladen** | Heimlade-Gesamtwerte (kWh, EUR, Sitzungsanzahl, Ø Solaranteil), letzte Sitzungs-KPIs, vollständige evcc-Sitzungshistorie. Jeder Eintrag zeigt SOC Start→Ende, kWh, Ø Ladeleistung, EUR/kWh, Kosten, Solaranteil, Dauer und einen SOC-Balken. |
| **Fremdladung** | Fremdladungs-Gesamtwerte, letzte Sitzungs-KPIs, editierbare Historie. Jeder Eintrag zeigt kWh, Ø Ladeleistung, Kosten und einen SOC-Balken; Einträge mit `start_fee` zeigen diese zusätzlich als eigene Zeile neben dem Preis. |
| **Fahrtenbuch** | Fahrt-Gesamtwerte, letzte Fahrt-KPIs (km, Route), editierbare Fahrthistorie. |

### Nutzungsprofil-Tab

Beantwortet "muss ich heute nachladen, oder reicht es, bis zum PV-Überschuss von morgen zu warten?" — komplett aus der eigenen Fahrhistorie, ohne manuelle Eingabe. Ein Balkendiagramm zeigt den durchschnittlichen kWh-Verbrauch pro Wochentag (Mo–So), aus dem Fahrtenbuch abgeleitet: für jeden Wochentag Gesamt-kWh an diesem Wochentag ÷ Anzahl der seit der ersten erfassten Fahrt verstrichenen Tage dieses Wochentags (Tage ohne Fahrt zählen weiterhin mit 0 kWh, damit "fährt selten sonntags" den Sonntags-Schnitt korrekt nach unten zieht statt ignoriert zu werden). Braucht mindestens 7 Tage Fahrtenbuch-Historie, bevor überhaupt etwas angezeigt wird (siehe `usage_profile` unten); der heutige und der morgige Balken sind hervorgehoben. Unter dem Diagramm: aktuell verfügbare Akku-kWh (aus SoC × nutzbarer Kapazität), der typische Bedarf für morgen zzgl. konfiguriertem Puffer, und eine Klartext-Empfehlung. Falls `pv_forecast_entity` konfiguriert ist (siehe Schritt 6), wird zusätzlich die morgige PV-Ertragsprognose angezeigt und in die Empfehlung einbezogen — eine Lücke, die der Akku allein nicht deckt, muss dann nicht zwingend per Netzladung geschlossen werden, wenn genug Sonne erwartet wird.

### Analyse-Tab

Längerfristige Signale, die nicht auf die Fahrzeugkarte für den Alltag gehören: der Trend der gemessenen Batteriekapazität (siehe `battery_capacity` oben), und — falls `outside_temp_entity` konfiguriert ist (Schritt 6) — ein Balkendiagramm des Durchschnittsverbrauchs je Temperaturband, mit der aktuellen Außentemperatur und ihrem aktiven Band daneben.

**Fahrzeugkarte** (über den drei Spalten): Fahrzeugname, aktueller SOC mit farbkodiertem Balken (rot < 20 %, orange < 40 %, sonst grün), Kilometerstand, Durchschnittsverbrauch (kWh/100 km, aus der gesamten Energiebilanz seit Einrichtung — geladene kWh gesamt ÷ gefahrene km) und Ladewirkungsgrad. Darunter drei Spalten: ein kompaktes km-Grid (gefahrene km heute/Woche/Monat/Jahr links, gleitende Durchschnitte und Projektionen rechts), eine Kosten-Spalte (kombinierte Heim- + Fremdladekosten heute/Woche/Monat/Jahr, aus den Sensoren `cost_day`/`cost_week`/`cost_month`/`cost_year`) sowie der Verbrenner-Vergleich (Ersparnis, EV-Kosten, Verbrenner-Kosten, Kosten pro 100 km).

**Balkendiagramme**: Ladeübersicht, Kostenübersicht und Solaranteil — umschaltbar zwischen Wochen-, Monats- und Jahresansicht mit Vor-/Zurück-Navigation. Beim Hovern über einen Balken erscheint ein Tooltip mit dem Wert (ersetzt die früheren Beschriftungen über den Balken, die in der Monatsansicht überlappten). Mobil-responsiv: auf Bildschirmen ≤ 600 px stapeln sich die drei Diagramme vertikal.

**Zahlenformatierung**: Alle Werte im Panel richten sich nach der HA-Locale-Einstellung (`Einstellungen → Profil → Zahlenformat`) — keine manuelle Konfiguration nötig.

---

## Dienste

Alle Dienste benötigen `config_entry_id`, um bei mehreren konfigurierten Einträgen das richtige Fahrzeug anzusprechen.

| Dienst | Parameter | Beschreibung |
|--------|-----------|--------------|
| `log_charge` | `config_entry_id`, `kwh`, `price_kwh`, `start_ts`*, `start_fee`* | Ausstehende Fremdladung mit Kassenbon-Werten bestätigen. `start_ts` wählt die Ladung aus (älteste, wenn weggelassen). `start_fee` ist eine optionale Pauschalgebühr mancher Ladenetze/-punkte zusätzlich zum kWh-Preis (z.B. Start- oder Blockiergebühr), Standard 0. |
| `discard_pending` | `config_entry_id`, `start_ts`* | Ausstehende Fremdladung verwerfen (Fehlalarm). |
| `edit_charge` | `config_entry_id`, `erfasst_ts`, `kwh`*, `price_kwh`*, `start_fee`*, `start_ts`*, `end_ts`*, `soc_start`*, `soc_end`* | Beliebiges Feld eines bereits bestätigten Historieneintrags korrigieren, gleiches "nur mitgegebene Felder ändern sich"-Modell wie `edit_trip`. Gesamtsummen werden bei kWh/Preis/Gebühr-Änderung um die Differenz angepasst; `soc_start`/`soc_end`-Änderungen berechnen das SoC-Delta neu; `end_ts` wird zusammen mit dem (neuen oder bisherigen) `start_ts` in eine Dauer umgerechnet. |
| `delete_charge` | `config_entry_id`, `erfasst_ts` | Bestätigten Historieneintrag entfernen. **Nicht rückgängig machbar.** |
| `simulate_event` | `config_entry_id`, `soc_start`, `soc_end`, `energy_source`* | Test-Fremdladungsereignis ohne Auto auslösen. |
| `log_trip` | `config_entry_id`, `start_ort`, `end_ort`, `start_ts`* | Ausstehende Fahrt mit Start-/Zielort bestätigen. |
| `discard_pending_trip` | `config_entry_id`, `start_ts`* | Ausstehende Fahrt verwerfen. |
| `edit_trip` | `config_entry_id`, `erfasst_ts`, `start_ort`*, `end_ort`*, `start_ts`*, `end_ts`*, `km`*, `odo_start`*, `odo_end`*, `soc_start`*, `soc_end`*, `verbrauch_kwh`* | Beliebige Felder eines bestätigten Fahrtenbucheintrags korrigieren, inklusive Datum/Uhrzeit. Nur mitgegebene Felder ändern sich. |
| `delete_trip` | `config_entry_id`, `erfasst_ts` | Bestätigten Fahrtenbucheintrag entfernen. **Nicht rückgängig machbar.** |
| `export_fahrtenbuch` | `config_entry_id` | Vollständige Fahrthistorie als CSV in `www/ev_assistant_fahrtenbuch_<entry_id>.csv` schreiben. |
| `import_fahrtenbuch` | `config_entry_id`, `trips` | Historische Fahrten aus einer anderen Fahrtenbuch-App/einem Export importieren (Liste von `{start, start_ort, ende, ziel_ort, strecke, ...}`), ohne die Kilometerstand-Erkennung. Gefahrlos mehrfach aufrufbar — bereits vorhandene Einträge werden übersprungen. |
| `simulate_trip` | `config_entry_id`, `km` | Test-Fahrtereignis ohne Auto auslösen. |

*optional

---

## Wie die Fremdladungserkennung funktioniert

EV Assistant benötigt kein GPS, keine Hersteller-API und keine Ladesäulenliste. Das Prinzip in einem Satz: **Steigt der Batterie-SoC, während das Heimlade-Signal inaktiv ist, muss das Auto woanders laden**.

Eine kleine Zustandsmaschine (`engine.py::ChargeDetector`) überwacht jeden SoC-Messwert. Sie verfolgt den letzten Ruhepunkt als „Anker". Sobald der SoC *ohne aktives Heimlade-Signal* um ≥ `start_delta` über den Anker gestiegen ist, beginnt eine Sitzung — außer `plug_entity` ist konfiguriert und bestätigt, dass das Fahrzeug ausgesteckt ist; dann verschiebt der Anstieg (z.B. ein paar Punkte durch Rekuperation beim Fahren) nur den Anker nach oben, statt eine Sitzung zu starten. Sie endet, wenn das Heimlade-Signal aktiv wird, der SoC um > `drop_ends` unter den verfolgten Höchstwert fällt, `idle_timeout_s` ohne neuen Höchstwert verstreicht, oder (falls `plug_entity` konfiguriert ist) ein bestätigtes Ausstecken erkannt wird.

Die Energie wird aus SoC-Delta × nutzbarem Akku ÷ Ladewirkungsgrad geschätzt — oder, wenn ein Fahrzeug-Ladeleistungssensor konfiguriert ist, aus der integrierten Leistungskurve (genauer, funktioniert auch unterwegs ohne Wallbox-Daten).

Fahrzeuge, die den SoC nur grob oder selten melden (manche Hersteller-Cloud-APIs), können `idle_timeout_s` zwischen zwei SoC-Meldungen derselben, eigentlich durchgehenden Ladung auslösen und sie so in mehrere "offene" Einträge zerteilen. Zwei Absicherungen fangen das ab: neu erkannte Ladungen werden mit der vorherigen offenen zusammengeführt, wenn dazwischen kein SoC-Abfall lag (ein echter Abfall bedeutet, dass gefahren wurde, also tatsächlich getrennte Ladestopps); und falls ein `plug_entity` konfiguriert ist, überstimmt ein bestätigtes „eingesteckt" `idle_timeout_s` komplett, sodass die Sitzung einfach nie endet, solange das Auto verbunden bleibt.

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
