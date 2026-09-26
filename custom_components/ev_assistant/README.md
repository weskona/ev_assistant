<p align="center">
  <img src="brand/logo.png" alt="EV Assistant logo" width="400">
</p>

# EV Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/v/release/weskona/ev_assistant)](https://github.com/weskona/ev_assistant/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/weskona/ev_assistant/blob/main/LICENSE)

A comprehensive **EV monitoring integration for Home Assistant**. EV Assistant covers home charging (via evcc), automatic external charge detection and logging, trip logging, charge-efficiency calibration, cost comparison against a combustion car, and a full EV dashboard as a dedicated sidebar panel. Works with any vehicle that exposes an SoC sensor in HA — manufacturer-independent.

📖 **[Full documentation on the Wiki](https://github.com/weskona/ev_assistant/wiki)**

**[🇩🇪 Deutsche Version weiter unten](#-deutsch)**

---

## 🇬🇧 English

### Status & Known Limitations

EV Assistant is in **active 0.x development** — pre-1.0. Behavior and configuration can still change between releases; check the [CHANGELOG](CHANGELOG.md) when updating.

It's been tested primarily against **one real setup**: a Stellantis-based vehicle (SoC via the manufacturer's cloud integration), one evcc version, one wallbox. That's a narrow slice of the "any vehicle, any evcc version, any wallbox" space this integration aims to cover — feedback from different vehicles, SoC reporting behavior, evcc versions, and wallboxes is genuinely wanted, not just tolerated.

A few known limitations, stated plainly:

- **Detection and usage profiles are only as good as the SoC signal.** Vehicles that report coarsely (whole-percent steps only, infrequent updates) still work, just less precisely.
- **Usage profiles need time to build up** (roughly two weeks for a full weekday spread) before they're reliable.
- **The evcc write control is opt-in and off by default.** Leave it off at first, watch the `evcc_mode_control` sensor for a while, and only turn on writing once its recommendations look plausible. It sets evcc's charge mode and min/target SoC — it does **not** decide where the charging power comes from (solar/grid/battery); that stays entirely evcc's own job.

### Features

- **Home charging monitoring** — tracks kWh and cost via your wallbox energy meter and evcc session history; session history with SOC bars, solar share, and Ø charge power per session.
- **External charge detection** — detects away-from-home charges purely from SoC telemetry (no GPS, no charger list). Prompts you to log the real kWh/price from the receipt.
- **Automatic trip log** — detects trips from your odometer sensor; you confirm start/end locations. CSV export included.
- **Charge-efficiency calibration** — learns your car's real AC→battery efficiency from home sessions and applies it automatically.
- **Odometer statistics** — driven km per day/week/month/year plus rolling averages and calendar-year projection.
- **Cost comparison** — compares total EV spend against an equivalent combustion car, with automatic or live fuel-price lookup.
- **Automatic evcc mode/SoC control** — optionally steers evcc's charge mode from your own usage profile, including a real-time PV-surplus override, an economic cap on grid top-ups, and home-battery priority.
- **Trip import** — bulk-import historical trips from another trip-log app/export.
- **Full sidebar panel** — a built-in, customizable EV dashboard; no Lovelace card setup needed.
- **Multi-vehicle support** — one integration entry per vehicle, with a panel tab switcher.
- **Diagnostics & repair issues** — a downloadable redacted state snapshot, plus Repair issues when a source entity goes stale.
- **Leasing mileage budget, charging cards, and vehicle maintenance tracking** — all fully optional, panel-managed.

See the [Wiki](https://github.com/weskona/ev_assistant/wiki) for the full breakdown of every sensor, service, and panel tab.

### Installation

**Via HACS (recommended):** HACS → Integrations → ⋮ → Custom repositories → add `https://github.com/weskona/ev_assistant` (Category: Integration) → install **EV Assistant** → restart Home Assistant.

**Manual:** copy `custom_components/ev_assistant/` into your `config/custom_components/` directory, then restart Home Assistant.

### Getting Started

**Settings → Devices & Services → Add Integration → "EV Assistant"**

Setup runs as a 9-step flow — vehicle details, charging mode, evcc/wallbox, charge power, notifications, detection tuning, trip log, leasing, and cost comparison. Only step 1 (vehicle) is required; everything else is optional and can be added or changed later via **Configure**.

📖 **[Configuration](https://github.com/weskona/ev_assistant/wiki/Configuration)** on the Wiki has the full step-by-step reference.

Once set up, EV Assistant registers a sidebar panel automatically — no dashboard/Lovelace setup needed. See **[Panel Tour](https://github.com/weskona/ev_assistant/wiki/Panel-Tour)** for a tab-by-tab walkthrough.

### Documentation

| Page | Covers |
|---|---|
| [Configuration](https://github.com/weskona/ev_assistant/wiki/Configuration) | The full 9-step setup flow, every option explained. |
| [Sensors & Entities](https://github.com/weskona/ev_assistant/wiki/Sensors-and-Entities) | Every sensor/binary sensor, with all attributes. |
| [Services](https://github.com/weskona/ev_assistant/wiki/Services) | Every service call, with parameters. |
| [Panel Tour](https://github.com/weskona/ev_assistant/wiki/Panel-Tour) | A tab-by-tab walkthrough of the sidebar panel. |
| [Automatic evcc Mode Control](https://github.com/weskona/ev_assistant/wiki/Automatic-evcc-Mode-Control) | Deep dive: day-ahead decision, PV-surplus carryover, real-time override, economic cap, charge plan. |
| [External Charge Detection](https://github.com/weskona/ev_assistant/wiki/External-Charge-Detection-Deep-Dive) | Deep dive: the exact state machine behind detecting away-from-home charges. |
| [Usage Profile & Recency-Weighting](https://github.com/weskona/ev_assistant/wiki/Usage-Profile-Deep-Dive) | Deep dive: how your typical daily need is learned and kept current. |
| [Panel Customization Guide](https://github.com/weskona/ev_assistant/wiki/Panel-Customization-Guide) | Practical walkthrough of card selection/reordering/sizing. |
| [Architecture & Contributing](https://github.com/weskona/ev_assistant/wiki/Architecture-and-Contributing) | Module layout, testing, and a guide to adding a new sensor. |
| [FAQ / Troubleshooting](https://github.com/weskona/ev_assistant/wiki/FAQ-Troubleshooting) | Setup issues and common behavior questions. |

### Requirements

- **Home Assistant 2024.1** or later
- **evcc** (the add-on/binary itself, reachable over the network) — optional, but required for home charging history and live energy-flow data in the panel. EV Assistant talks to evcc's own REST API directly — no separate `evcc_intg` HA integration needed.
- Any vehicle with an SoC sensor in HA (WiCAN Pro / MQTT, manufacturer cloud integrations, evcc vehicle sensors, ...)

### Contributing

Found a bug or have a feature request? Please [open a GitHub Issue](https://github.com/weskona/ev_assistant/issues) — include your Home Assistant version and, if relevant, a debug log (see [Troubleshooting](https://github.com/weskona/ev_assistant/wiki/FAQ-Troubleshooting)). Pull requests are welcome; see [CONTRIBUTING.md](https://github.com/weskona/ev_assistant/blob/main/CONTRIBUTING.md) and the wiki's [Architecture & Contributing](https://github.com/weskona/ev_assistant/wiki/Architecture-and-Contributing) page before opening one.

---

## 🇩🇪 Deutsch

### Status & bekannte Grenzen

EV Assistant befindet sich in **aktiver 0.x-Entwicklung** — vor 1.0. Verhalten und Konfiguration können sich zwischen Releases noch ändern; beim Update das [CHANGELOG](CHANGELOG.md) prüfen.

Getestet wurde primär gegen **eine reale Installation**: ein Stellantis-basiertes Fahrzeug (SoC über die Cloud-Integration des Herstellers), eine evcc-Version, eine Wallbox. Das ist nur ein schmaler Ausschnitt des angestrebten „jedes Fahrzeug, jede evcc-Version, jede Wallbox"-Spektrums — Feedback von anderen Fahrzeugen, SoC-Meldeverhalten, evcc-Versionen und Wallboxen ist ausdrücklich erwünscht, nicht nur geduldet.

Ein paar bekannte Grenzen, unverblümt:

- **Erkennung und Nutzungsprofile sind nur so gut wie das SoC-Signal.** Fahrzeuge, die grob melden (nur ganze Prozentschritte, seltene Updates), funktionieren trotzdem, nur ungenauer.
- **Nutzungsprofile brauchen Zeit zum Aufbauen** (ungefähr zwei Wochen für eine vollständige Wochentags-Verteilung), bevor sie verlässlich sind.
- **Die evcc-Schreibsteuerung ist optional und standardmäßig aus.** Erst eine Weile aus lassen, den Sensor `evcc_mode_control` beobachten, und die Schreibfunktion erst aktivieren, wenn die Empfehlungen plausibel aussehen. Sie setzt evccs Lademodus und Min-/Ziel-SoC — sie entscheidet **nicht**, woher die Ladeleistung kommt (Solar/Netz/Speicher); das bleibt vollständig evccs eigene Aufgabe.

### Funktionen

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

### Installation

**Über HACS (empfohlen):** HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories → URL hinzufügen `https://github.com/weskona/ev_assistant` (Kategorie: Integration) → **EV Assistant** installieren → Home Assistant neu starten.

**Manuell:** `custom_components/ev_assistant/` in euer `config/custom_components/`-Verzeichnis kopieren, dann Home Assistant neu starten.

### Erste Schritte

**Einstellungen → Geräte & Dienste → Integration hinzufügen → „EV Assistant"**

Die Einrichtung läuft als 9-Schritte-Flow — Fahrzeugdetails, Lademodus, evcc/Wallbox, Ladeleistung, Benachrichtigungen, Erkennungs-Feinjustierung, Fahrtenbuch, Leasing und Kostenvergleich. Nur Schritt 1 (Fahrzeug) ist Pflicht; alles andere ist optional und kann später über **Konfigurieren** ergänzt/geändert werden.

📖 **[Konfiguration](https://github.com/weskona/ev_assistant/wiki/Configuration-DE)** im Wiki hat die vollständige Schritt-für-Schritt-Referenz.

Nach der Einrichtung registriert EV Assistant automatisch ein Seitenleisten-Panel — keine Dashboard-/Lovelace-Einrichtung nötig. Siehe **[Panel-Rundgang](https://github.com/weskona/ev_assistant/wiki/Panel-Tour-DE)** für einen Tab-für-Tab-Rundgang.

### Dokumentation

| Seite | Behandelt |
|---|---|
| [Konfiguration](https://github.com/weskona/ev_assistant/wiki/Configuration-DE) | Der komplette 9-Schritte-Einrichtungs-Flow, jede Option erklärt. |
| [Sensoren & Entitäten](https://github.com/weskona/ev_assistant/wiki/Sensors-and-Entities-DE) | Jeder Sensor/Binärsensor, mit allen Attributen. |
| [Dienste](https://github.com/weskona/ev_assistant/wiki/Services-DE) | Jeder Service-Aufruf, mit Parametern. |
| [Panel-Rundgang](https://github.com/weskona/ev_assistant/wiki/Panel-Tour-DE) | Ein Tab-für-Tab-Rundgang durch das Seitenleisten-Panel. |
| [Automatische evcc-Modus-Steuerung](https://github.com/weskona/ev_assistant/wiki/Automatic-evcc-Mode-Control-DE) | Tiefer Einblick: Tages-Basis-Entscheidung, PV-Überschuss-Anrechnung, Echtzeit-Übersteuerung, wirtschaftliche Kappung, Ladeplan. |
| [Fremdladungserkennung](https://github.com/weskona/ev_assistant/wiki/External-Charge-Detection-Deep-Dive-DE) | Tiefer Einblick: die exakte Zustandsmaschine hinter der Erkennung von Ladungen unterwegs. |
| [Nutzungsprofil & Recency-Weighting](https://github.com/weskona/ev_assistant/wiki/Usage-Profile-Deep-Dive-DE) | Tiefer Einblick: wie euer typischer Tagesbedarf gelernt und aktuell gehalten wird. |
| [Anleitung: Panel anpassen](https://github.com/weskona/ev_assistant/wiki/Panel-Customization-Guide-DE) | Praktische Anleitung zu Karten-Auswahl/-Reihenfolge/-Größe. |
| [Architektur & Mitwirken](https://github.com/weskona/ev_assistant/wiki/Architecture-and-Contributing-DE) | Modul-Struktur, Testen, und eine Anleitung zum Hinzufügen eines neuen Sensors. |
| [FAQ / Fehlersuche](https://github.com/weskona/ev_assistant/wiki/FAQ-Troubleshooting-DE) | Einrichtungsprobleme und häufige Verhaltensfragen. |

### Voraussetzungen

- **Home Assistant 2024.1** oder neuer
- **evcc** (das Addon/die Binary selbst, im Netzwerk erreichbar) — optional, aber erforderlich für die Heimladen-Historie und Live-Energieflussdaten im Panel. EV Assistant spricht evccs eigene REST-API direkt an — keine separate `evcc_intg`-HA-Integration nötig.
- Jedes Fahrzeug mit einem SoC-Sensor in HA (WiCAN Pro / MQTT, Hersteller-Cloud-Integrationen, evcc-Fahrzeugsensoren, ...)

### Mitwirken

Einen Bug gefunden oder einen Feature-Wunsch? Bitte [ein GitHub Issue eröffnen](https://github.com/weskona/ev_assistant/issues) — mit eurer Home-Assistant-Version und, falls relevant, einem Debug-Log (siehe [Fehlersuche](https://github.com/weskona/ev_assistant/wiki/FAQ-Troubleshooting-DE)). Pull Requests willkommen; vorher [CONTRIBUTING.md](https://github.com/weskona/ev_assistant/blob/main/CONTRIBUTING.md) und die Wiki-Seite [Architektur & Mitwirken](https://github.com/weskona/ev_assistant/wiki/Architecture-and-Contributing-DE) lesen.

---

## Lizenz / License

MIT © [weskona](https://github.com/weskona)
