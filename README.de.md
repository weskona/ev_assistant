<p align="center">
  <img src="https://raw.githubusercontent.com/weskona/ev_assistant/main/custom_components/ev_assistant/brand/logo.png" alt="EV Assistant Logo" width="400">
</p>

# EV Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/v/release/weskona/ev_assistant)](https://github.com/weskona/ev_assistant/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![HA min version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io)
[![Validate](https://github.com/weskona/ev_assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/weskona/ev_assistant/actions/workflows/validate.yml)
[![Downloads](https://img.shields.io/github/downloads/weskona/ev_assistant/total)](https://github.com/weskona/ev_assistant/releases)

[🇬🇧 English Version](README.md) · 📖 [Vollständige Dokumentation im Wiki](https://github.com/weskona/ev_assistant/wiki)

Eine umfassende **EV-Überwachungs-Integration für Home Assistant**. EV Assistant deckt Heimladen (via evcc), automatische Fremdladungserkennung und -protokollierung, Fahrtenbuch, Ladewirkungsgrad-Kalibrierung, Kostenvergleich gegenüber einem Verbrenner sowie ein vollständiges EV-Dashboard als eigenes Seitenleisten-Panel ab. Funktioniert mit jedem Fahrzeug, das einen SoC-Sensor in HA bereitstellt — herstellerunabhängig.

---

## Status & bekannte Grenzen

EV Assistant befindet sich in **aktiver 0.x-Entwicklung** — vor 1.0. Verhalten und Konfiguration können sich zwischen Releases noch ändern; beim Update das [CHANGELOG](custom_components/ev_assistant/CHANGELOG.md) prüfen.

Getestet wurde primär gegen **eine reale Installation**: ein Stellantis-basiertes Fahrzeug (SoC über die Cloud-Integration des Herstellers), eine evcc-Version, eine Wallbox. Das ist nur ein schmaler Ausschnitt des angestrebten „jedes Fahrzeug, jede evcc-Version, jede Wallbox"-Spektrums — Feedback von anderen Fahrzeugen, SoC-Meldeverhalten, evcc-Versionen und Wallboxen ist ausdrücklich erwünscht, nicht nur geduldet.

Ein paar bekannte Grenzen, unverblümt:

- **Erkennung und Nutzungsprofile sind nur so gut wie das SoC-Signal.** Fahrzeuge, die grob melden (nur ganze Prozentschritte, seltene Updates), funktionieren trotzdem, nur ungenauer.
- **Nutzungsprofile brauchen Zeit zum Aufbauen** (ungefähr zwei Wochen für eine vollständige Wochentags-Verteilung), bevor sie verlässlich sind.
- **Die evcc-Schreibsteuerung ist optional und standardmäßig aus.** Erst eine Weile aus lassen, den Sensor `evcc_mode_control` beobachten, und die Schreibfunktion erst aktivieren, wenn die Empfehlungen plausibel aussehen. Sie setzt evccs Lademodus und Min-/Ziel-SoC — sie entscheidet **nicht**, woher die Ladeleistung kommt (Solar/Netz/Speicher); das bleibt vollständig evccs eigene Aufgabe.

---

## Funktionen

- **Heimladen-Überwachung** — erfasst kWh und Kosten über euren Wallbox-Energiezähler und evccs Sitzungshistorie; Sitzungshistorie mit SOC-Balken, Solaranteil und Ø-Ladeleistung je Sitzung.
- **Fremdladungserkennung** — erkennt Ladungen unterwegs rein aus SoC-Telemetrie (kein GPS, keine Ladesäulenliste). Fordert euch auf, die echten kWh/den Preis vom Beleg zu erfassen.
- **Automatisches Fahrtenbuch** — erkennt Fahrten aus dem Kilometerstand-Sensor; ihr bestätigt Start-/Zielort. CSV-Export inklusive.
- **Ladewirkungsgrad-Kalibrierung** — lernt den echten AC→Akku-Wirkungsgrad eures Autos aus Heimlade-Sitzungen und wendet ihn automatisch an.
- **Kilometerstand-Statistiken** — gefahrene km je Tag/Woche/Monat/Jahr sowie gleitende Durchschnitte und Kalenderjahr-Projektion.
- **Kostenvergleich** — vergleicht die gesamten EV-Ausgaben gegen einen vergleichbaren Verbrenner, mit automatischer oder Live-Kraftstoffpreis-Ermittlung.
- **Automatische evcc-Modus-/SoC-Steuerung** — steuert optional evccs Lademodus aus eurem eigenen Nutzungsprofil, inklusive Echtzeit-PV-Überschuss-Übersteuerung, wirtschaftlicher Kappung des Netz-Zuschusses und Speicher-Priorität.
- **Fahrten-Import** — historische Fahrten aus einer anderen Fahrtenbuch-App/einem Export bulk-importieren.
- **Vollständiges Seitenleisten-Panel** — ein eingebautes, anpassbares EV-Dashboard; keine Lovelace-Karten-Einrichtung nötig.
- **Multi-Fahrzeug-Unterstützung** — ein Integrations-Eintrag je Fahrzeug, mit Panel-Tab-Umschalter.
- **Diagnose & Repair-Issues** — ein herunterladbarer, geschwärzter Zustands-Snapshot, sowie Repair-Issues, wenn eine Quell-Entität veraltet.
- **Leasing-Kilometerbudget, Ladekarten und Fahrzeugwartung** — alles vollständig optional, panel-verwaltet.

Die vollständige Aufschlüsselung jedes Sensors, Services und Panel-Tabs steht im [Wiki](https://github.com/weskona/ev_assistant/wiki).

---

## Installation

### Über HACS (empfohlen)

1. **HACS** → Integrationen → ⋮ → **Benutzerdefinierte Repositories**
2. URL hinzufügen: `https://github.com/weskona/ev_assistant` — Kategorie: **Integration**
3. **EV Assistant** installieren, dann Home Assistant neu starten.

### Manuell

1. `custom_components/ev_assistant/` in euer `config/custom_components/`-Verzeichnis kopieren.
2. Home Assistant neu starten.

---

## Erste Schritte

**Einstellungen → Geräte & Dienste → Integration hinzufügen → „EV Assistant"**

Die Einrichtung läuft als 9-Schritte-Flow — Fahrzeugdetails, Lademodus, evcc/Wallbox, Ladeleistung, Benachrichtigungen, Erkennungs-Feinjustierung, Fahrtenbuch, Leasing und Kostenvergleich. Nur Schritt 1 (Fahrzeug) ist Pflicht; alles andere ist optional und kann später über **Konfigurieren** ergänzt/geändert werden.

📖 **[Konfiguration](https://github.com/weskona/ev_assistant/wiki/Configuration-DE)** im Wiki hat die vollständige Schritt-für-Schritt-Referenz.

Nach der Einrichtung registriert EV Assistant automatisch ein Seitenleisten-Panel — keine Dashboard-/Lovelace-Einrichtung nötig. Siehe **[Panel-Rundgang](https://github.com/weskona/ev_assistant/wiki/Panel-Tour-DE)** für einen Tab-für-Tab-Rundgang.

---

## Dokumentation

Das [Wiki](https://github.com/weskona/ev_assistant/wiki) hat die vollständige Referenz:

| Seite | Behandelt |
|---|---|
| [Konfiguration](https://github.com/weskona/ev_assistant/wiki/Configuration-DE) | Der komplette 9-Schritte-Einrichtungs-Flow, jede Option erklärt. |
| [Sensoren & Entitäten](https://github.com/weskona/ev_assistant/wiki/Sensors-and-Entities-DE) | Jeder Sensor/Binärsensor, mit allen Attributen. |
| [Dienste](https://github.com/weskona/ev_assistant/wiki/Services-DE) | Jeder Service-Aufruf, mit Parametern. |
| [Panel-Rundgang](https://github.com/weskona/ev_assistant/wiki/Panel-Tour-DE) | Ein Tab-für-Tab-Rundgang durch das Seitenleisten-Panel. |
| [Automatische evcc-Modus-Steuerung](https://github.com/weskona/ev_assistant/wiki/Automatic-evcc-Mode-Control-DE) | Tiefer Einblick: die Tages-Basis-Entscheidung, PV-Überschuss-Anrechnung, Echtzeit-Übersteuerung, wirtschaftliche Kappung, Ladeplan. |
| [Fremdladungserkennung](https://github.com/weskona/ev_assistant/wiki/External-Charge-Detection-Deep-Dive-DE) | Tiefer Einblick: die exakte Zustandsmaschine hinter der Erkennung von Ladungen unterwegs. |
| [Nutzungsprofil & Recency-Weighting](https://github.com/weskona/ev_assistant/wiki/Usage-Profile-Deep-Dive-DE) | Tiefer Einblick: wie euer typischer Tagesbedarf gelernt und aktuell gehalten wird. |
| [Anleitung: Panel anpassen](https://github.com/weskona/ev_assistant/wiki/Panel-Customization-Guide-DE) | Praktische Anleitung zu Karten-Auswahl/-Reihenfolge/-Größe. |
| [Architektur & Mitwirken](https://github.com/weskona/ev_assistant/wiki/Architecture-and-Contributing-DE) | Modul-Struktur, Testen, und eine Anleitung zum Hinzufügen eines neuen Sensors. |
| [FAQ / Fehlersuche](https://github.com/weskona/ev_assistant/wiki/FAQ-Troubleshooting-DE) | Einrichtungsprobleme und häufige Verhaltensfragen. |

---

## Voraussetzungen

- **Home Assistant 2024.1** oder neuer
- **evcc** (das Addon/die Binary selbst, im Netzwerk erreichbar) — optional, aber erforderlich für die Heimladen-Historie und Live-Energieflussdaten im Panel. EV Assistant spricht evccs eigene REST-API direkt an — keine separate `evcc_intg`-HA-Integration nötig.
- Jedes Fahrzeug mit einem SoC-Sensor in HA (WiCAN Pro / MQTT, Hersteller-Cloud-Integrationen, evcc-Fahrzeugsensoren, ...)

---

## Mitwirken

Einen Bug gefunden oder einen Feature-Wunsch? Bitte [ein GitHub Issue eröffnen](https://github.com/weskona/ev_assistant/issues) — mit eurer Home-Assistant-Version und, falls relevant, einem Debug-Log (siehe [Fehlersuche](https://github.com/weskona/ev_assistant/wiki/FAQ-Troubleshooting-DE)). Pull Requests willkommen; vorher [CONTRIBUTING.md](CONTRIBUTING.md) und die Wiki-Seite [Architektur & Mitwirken](https://github.com/weskona/ev_assistant/wiki/Architecture-and-Contributing-DE) lesen.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).

## Danksagung & Support

Erstellt und gepflegt von [@weskona](https://github.com/weskona).

Das App-Icon basiert auf dem „ev-station"-Glyph von Material Design Icons
(https://pictogrammers.com/library/mdi/), © Pictogrammers, lizenziert unter
Apache License 2.0. Das Glyph wurde auf eine eigene Sechseck-Kachel gesetzt.

Fragen oder Support-Anfragen bitte über [GitHub Issues](https://github.com/weskona/ev_assistant/issues), nicht per Direktnachricht.
