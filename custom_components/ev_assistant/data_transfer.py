"""Import, Export und Backup des persistenten Zustands.

Aus coordinator.py ausgelagert (Umbau vor der 1.0, siehe Issue #12): Fahrtenbuch-
Import (Fremdformat) und -Export (CSV), Export des Ereignisprotokolls (Text) und
Backup/Restore (JSON). Der Zustand bleibt vollstaendig im Coordinator
("host": data, entry, hass, Speichern, Benachrichtigungen); diese Klasse haelt
selbst keinen eigenen Zustand. Die oeffentlichen Methoden des Coordinators
(async_import_fahrtenbuch, async_export_fahrtenbuch, async_export_event_log,
async_export_backup, async_restore_backup) bleiben unveraendert bestehen und
rufen hierher durch -- Dienste, Tests und das Panel merken nichts davon.

Der Datenvertrag (Schluessel von _empty_data(), Format von Backup und CSV) ist
durch tests/ha/test_data_contract.py festgehalten.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import EVENT_TRIP_IMPORTED

if TYPE_CHECKING:
    from .coordinator import EvAssistantCoordinator

_LOGGER = logging.getLogger(__name__)


class DataTransfer:
    """Import/Export/Backup fuer genau einen Coordinator (siehe Modul-Docstring)."""

    def __init__(self, host: EvAssistantCoordinator) -> None:
        self._host = host

    async def import_fahrtenbuch(self, trips: list) -> int:
        """Importiert historische Fahrten aus einer Fremdquelle (z.B. Export
        einer anderen Fahrtenbuch-App) direkt in data['fahrten'], ohne den
        Umweg ueber die Kilometerstand-Erkennung -- odo_start/odo_end
        bleiben dabei None, da diese Fremddaten keine Kilometerstaende
        liefern, nur die gefahrene Strecke. Format je Eintrag: start/ende
        als 'YYYY-MM-DD HH:MM:SS' in lokaler Zeit, start_ort/ziel_ort,
        strecke (km), optional verbrauch_kwh/avg_verbrauch/avg_speed.
        Ungueltige Eintraege werden uebersprungen (Warnung im Log) statt
        den gesamten Import abzubrechen. Eintraege mit einem bereits
        vorhandenen start_ts werden uebersprungen, damit ein wiederholter
        Import keine Dubletten erzeugt -- die Pruefung beruecksichtigt dafuer
        NEBEN der aktuellen fahrten-Liste auch das Archiv (siehe
        _async_truncate_lifetime_lists()), sonst koennte ein laengst
        archivierter Import bei einem erneuten Lauf faelschlich als "neu"
        durchgehen. Gibt die Anzahl tatsaechlich neu importierter Fahrten
        zurueck."""
        host = self._host
        archiv = await host._load_archive()
        existing_starts = {rec.get("start_ts") for rec in host.data.get("fahrten") or []}
        existing_starts.update(rec.get("start_ts") for rec in archiv.get("fahrten", []))
        imported: list[dict] = []
        # Ein Basiswert + laufender Index statt in jeder Iteration neu
        # int(time.time()) zu lesen -- sonst bekaemen mehrere Fahrten in
        # einem Aufruf denselben (ganzzahligen) erfasst_ts, der als
        # alleiniger Schluessel fuer edit_trip()/delete_trip() dient und
        # dann versehentlich die falsche Fahrt trifft.
        erfasst_ts_base = int(time.time())
        for row in trips:
            try:
                start_dt = datetime.strptime(row["start"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=dt_util.DEFAULT_TIME_ZONE
                )
                end_dt = datetime.strptime(row["ende"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=dt_util.DEFAULT_TIME_ZONE
                )
                start_ts = start_dt.timestamp()
                if start_ts in existing_starts:
                    continue
                rec = {
                    "config_entry_id": host.entry.entry_id,
                    "datum": start_dt.date().isoformat(),
                    "start_ts": start_ts, "end_ts": end_dt.timestamp(),
                    "odo_start": None, "odo_end": None,
                    "km": round(float(row["strecke"]), 2),
                    "start_ort": row["start_ort"], "end_ort": row["ziel_ort"],
                    "erfasst_ts": erfasst_ts_base + len(imported), "quelle": "import",
                }
                for key in ("verbrauch_kwh", "avg_verbrauch", "avg_speed"):
                    if row.get(key) is not None:
                        rec[key] = float(row[key])
                imported.append(rec)
                existing_starts.add(start_ts)
            except (KeyError, TypeError, ValueError) as exc:
                _LOGGER.warning(
                    "ev_assistant: Fahrtenbuch-Import: ungueltiger Eintrag uebersprungen (%s): %r", exc, row
                )

        if not imported:
            return 0

        fahrten = host.data.setdefault("fahrten", [])
        fahrten.extend(imported)
        fahrten.sort(key=lambda r: r.get("start_ts") or 0, reverse=True)

        totals = host.data.setdefault("trip_totals", {"km": 0.0, "count": 0})
        totals["km"] = round(totals.get("km", 0.0) + sum(r["km"] for r in imported), 2)
        totals["count"] = totals.get("count", 0) + len(imported)
        for rec in imported:
            host._apply_trip_baselines(rec, 1)
        host._fahrten_version += 1

        await host._save()
        host.hass.bus.async_fire(EVENT_TRIP_IMPORTED, {"anzahl": len(imported)})
        en = host._en()
        await host._persistent_notification(
            "create",
            {
                "notification_id": f"{host._notify_tag}_import",
                "title": "Trip log import" if en else "Fahrtenbuch-Import",
                "message": (
                    f"{len(imported)} trip(s) imported."
                    if en else f"{len(imported)} Fahrt(en) importiert."
                ),
            },
        )
        host.async_set_updated_data(host.data)
        return len(imported)

    async def export_fahrtenbuch(self) -> str:
        """Exportiert das GESAMTE Fahrtenbuch (chronologisch aufsteigend,
        inkl. archivierter Fahrten, siehe _async_truncate_lifetime_lists())
        als CSV nach www/, damit es unter /local/... herunterladbar ist --
        der Export bleibt dadurch vollstaendig, auch wenn die aktuelle
        fahrten-Liste laengst gekuerzt wurde."""
        host = self._host
        archiv = await host._load_archive()
        fahrten = archiv.get("fahrten", []) + list(host.data.get("fahrten") or [])
        fahrten.sort(key=lambda r: r.get("start_ts") or 0)
        path = host.hass.config.path("www", f"ev_assistant_fahrtenbuch_{host.entry.entry_id}.csv")
        await host.hass.async_add_executor_job(self._write_fahrtenbuch_csv, path, fahrten)
        filename = os.path.basename(path)
        en = host._en()
        await host._persistent_notification(
            "create",
            {
                "notification_id": f"{host._notify_tag}_export",
                "title": "Trip log exported" if en else "Fahrtenbuch exportiert",
                "message": (
                    f"CSV export ready: [{filename}](/local/{filename})" if en
                    else f"CSV-Export bereit: [{filename}](/local/{filename})"
                ),
            },
        )
        return path

    @staticmethod
    def _write_fahrtenbuch_csv(path: str, fahrten: list[dict]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Datum", "Start", "Ziel", "km Start", "km Ende", "Strecke (km)"])
            for t in fahrten:
                odo_start = t["odo_start"] if t["odo_start"] is not None else ""
                odo_end = t["odo_end"] if t["odo_end"] is not None else ""
                writer.writerow([t["datum"], t["start_ort"], t["end_ort"], odo_start, odo_end, t["km"]])

    async def export_event_log(self) -> str:
        """Exportiert das Ereignisprotokoll (siehe _log_event()/
        EVENT_LOG_MAX_AGE_DAYS in const.py) als lesbare Text-Datei nach
        www/, fuer Bug-Reports -- andere Nutzer koennen die Datei direkt
        an ein GitHub-Issue anhaengen, ohne dass wir Zugriff auf ihre
        Instanz brauchen. Bewusst reiner Text statt JSON: soll auf einen
        Blick lesbar sein, nicht nur maschinell auswertbar. Keine eigene
        Redaction noetig (anders als diagnostics.py/TO_REDACT_LOCATION):
        _log_event()-Aufrufer duerfen laut dortigem Docstring ohnehin
        keine Orte/Tokens in den Text schreiben, nur technische Werte
        (SoC/kWh/Modus/Entity-IDs)."""
        host = self._host
        log = list(host.data.get("event_log") or [])
        path = host.hass.config.path("www", f"ev_assistant_event_log_{host.entry.entry_id}.txt")
        await host.hass.async_add_executor_job(self._write_event_log_txt, path, log)
        filename = os.path.basename(path)
        en = host._en()
        await host._persistent_notification(
            "create",
            {
                "notification_id": f"{host._notify_tag}_event_log_export",
                "title": "Event log exported" if en else "Ereignisprotokoll exportiert",
                "message": (
                    f"Log ready: [{filename}](/local/{filename})" if en
                    else f"Protokoll bereit: [{filename}](/local/{filename})"
                ),
            },
        )
        return path

    @staticmethod
    def _write_event_log_txt(path: str, log: list[dict]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for entry in log:
                ts_local = dt_util.as_local(dt_util.utc_from_timestamp(entry["ts"]))
                f.write(f"[{ts_local.strftime('%Y-%m-%d %H:%M:%S')}] {entry['kategorie']}: {entry['text']}\n")

    async def export_backup(self) -> str:
        """Exportiert den kompletten persistenten Zustand (coordinator.data --
        Fahrtenbuch, Ladehistorie, Ladekarten, Wartungsplan, alle "seit
        Einrichtung"-Anker, Event-Log) als JSON-Datei nach www/, zum
        manuellen Sichern/Wiederherstellen (siehe async_restore_backup()).
        Deterministischer Dateiname (wie async_export_event_log()) -- wird
        bei jedem Aufruf ueberschrieben, eine dauerhafte Historie mehrerer
        Zeitpunkte muss der Nutzer selbst durch Herunterladen/Umbenennen der
        Datei anlegen (kein automatisches, geplantes Backup -- bewusst rein
        On-Demand, siehe Nutzerwunsch).

        Enthaelt zusaetzlich einen rein informativen Konfigurations-
        Schnappschuss (entry.data/entry.options) unter dem Schluessel
        "_config_snapshot_readonly" -- NUR zur Referenz (z.B. um spaeter zu
        sehen, mit welchem evcc-Host ein Backup erstellt wurde), wird von
        async_restore_backup() verworfen. coordinator.data ist bereits vollstaendig
        JSON-serialisierbar (laeuft ohnehin schon durch Store.async_save()),
        kein Encoder noetig."""
        host = self._host
        payload = dict(host.data)
        payload["_config_snapshot_readonly"] = {
            "data": dict(host.entry.data), "options": dict(host.entry.options),
        }
        path = host.hass.config.path("www", f"ev_assistant_backup_{host.entry.entry_id}.json")
        await host.hass.async_add_executor_job(self._write_backup_json, path, payload)
        filename = os.path.basename(path)
        en = host._en()
        await host._persistent_notification(
            "create",
            {
                "notification_id": f"{host._notify_tag}_backup_export",
                "title": "Backup exported" if en else "Backup exportiert",
                "message": (
                    f"Backup ready: [{filename}](/local/{filename})" if en
                    else f"Backup bereit: [{filename}](/local/{filename})"
                ),
            },
        )
        return path

    @staticmethod
    def _write_backup_json(path: str, payload: dict) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    async def restore_backup(self, backup_data: str) -> bool:
        """Ersetzt coordinator.data komplett durch einen zuvor per async_export_
        backup() erzeugten JSON-Snapshot -- die folgenschwerste Aktion der
        Integration, daher mehrfach abgesichert:

        (1) Minimale Struktur-Pruefung (erwartet mindestens die "history"-
        Kernstruktur aus _empty_data()) -- bei Fehlschlag NUR eine Warnung
        im Log, coordinator.data bleibt unveraendert (analog async_add_
        maintenance() ohne Kriterium: stiller Reject statt Exception). Die
        eigentliche Validierung (ist das ueberhaupt eine JSON-Datei, hat sie
        die erwarteten Schluessel) passiert bereits client-seitig im Panel,
        BEVOR der Service ueberhaupt aufgerufen wird -- diese Pruefung hier
        ist nur die zweite Verteidigungslinie fuer einen direkten
        Service-Aufruf (z.B. ueber Entwicklerwerkzeuge).
        (2) Automatisches Sicherheits-Backup des AKTUELLEN Stands vor dem
        Ueberschreiben (eigener Dateiname, siehe async_export_backup()) --
        fuer den Fall der falschen Datei.
        (3) Integration-Reload danach statt nur _save() + async_set_
        updated_data(): mehrere abgeleitete In-Memory-Caches (z.B. _evcc_
        session_sums, Debounce-Zustaende) waeren nach einem reinen Daten-
        Austausch sonst inkonsistent mit dem neuen Stand.

        Der rein informative "_config_snapshot_readonly"-Schluessel (siehe
        async_export_backup()) wird verworfen -- Konfiguration (evcc-Host,
        Entity-IDs etc.) ist NIE Teil des Restores, nur die Daten. Gibt
        True bei Erfolg zurueck, False bei Ablehnung."""
        host = self._host
        try:
            restored = json.loads(backup_data)
        except (json.JSONDecodeError, TypeError):
            _LOGGER.warning("restore_backup: kein gueltiges JSON, Vorgang abgebrochen")
            return False
        if not isinstance(restored, dict) or "history" not in restored:
            _LOGGER.warning("restore_backup: fehlende Kernstruktur, Vorgang abgebrochen")
            return False
        restored.pop("_config_snapshot_readonly", None)

        pre_restore_path = host.hass.config.path(
            "www", f"ev_assistant_backup_pre_restore_{host.entry.entry_id}.json"
        )
        await host.hass.async_add_executor_job(self._write_backup_json, pre_restore_path, dict(host.data))

        host.data = restored
        await host._save()
        host.hass.async_create_task(host.hass.config_entries.async_reload(host.entry.entry_id))
        return True
