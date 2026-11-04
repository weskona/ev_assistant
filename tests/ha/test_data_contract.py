"""Sicherheitsnetz fuer den Umbau/die Aufteilung von coordinator.py.

Der Coordinator haelt seinen GESAMTEN persistenten Zustand in einem Dict
(`self.data`), das unveraendert in den Store geschrieben und beim naechsten
Start wieder gelesen wird. Jeder Schluessel darin ist ein Vertrag mit den
Daten, die Nutzer schon auf der Platte haben: ein umbenannter oder
vergessener Schluessel verliert Daten beim naechsten Update.

Diese Tests halten fest, was ein Umbau NICHT veraendern darf:
  1. die Schluessel und Standardwerte von `_empty_data()` (Schnappschuss in
     tests/ha/data_contract/empty_data.json),
  2. Namen und Version der Stores,
  3. dass Laden und Speichern keinen Schluessel verliert (auch keinen
     unbekannten aus einer neueren Version),
  4. das Format von Backup (Export, Restore) und Fahrtenbuch-CSV (Export,
     Import) -- die ersten Kandidaten fuer eine Auslagerung.

Bewusste Aenderung eines Schluessels: Schnappschuss neu erzeugen mit
    UPDATE_DATA_CONTRACT=1 pytest tests/ha/test_data_contract.py
und dabei bedenken, ob eine Migration in async_setup() noetig ist."""
import csv
import io
import json
import os
from pathlib import Path

from pytest_homeassistant_custom_component.common import MockConfigEntry

SNAPSHOT = Path(__file__).parent / "data_contract" / "empty_data.json"


def _json_roundtrip(value):
    return json.loads(json.dumps(value, sort_keys=True))


def test_empty_data_entspricht_dem_schnappschuss():
    from custom_components.ev_assistant.coordinator import _empty_data

    current = _json_roundtrip(_empty_data())
    if os.environ.get("UPDATE_DATA_CONTRACT"):
        SNAPSHOT.write_text(json.dumps(current, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    removed = sorted(set(expected) - set(current))
    added = sorted(set(current) - set(expected))
    changed = sorted(k for k in set(expected) & set(current) if expected[k] != current[k])
    assert not (removed or added or changed), (
        "Der persistente Datenvertrag hat sich geaendert -- "
        f"entfernt: {removed}, neu: {added}, Standardwert geaendert: {changed}. "
        "Entfernte/umbenannte Schluessel verlieren Nutzerdaten (Migration in async_setup() noetig!). "
        "Bewusst? Schnappschuss neu erzeugen: UPDATE_DATA_CONTRACT=1 pytest tests/ha/test_data_contract.py"
    )


def test_empty_data_ist_json_serialisierbar_und_liefert_frische_objekte():
    from custom_components.ev_assistant.coordinator import _empty_data

    first, second = _empty_data(), _empty_data()
    json.dumps(first)  # Store.async_save()
    first["history"].append({"x": 1})
    assert second["history"] == [], "gemeinsam genutzte veraenderliche Standardwerte"


def test_store_namen_und_version_sind_festgelegt():
    from custom_components.ev_assistant.const import STORAGE_KEY, STORAGE_VERSION

    assert STORAGE_KEY == "ev_assistant_data"
    assert STORAGE_VERSION == 1


def _entry(hass, entry_id):
    from custom_components.ev_assistant.const import DOMAIN

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    return entry


async def _coordinator(hass, coordinators, entry):
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator


async def test_laden_und_speichern_verliert_keinen_schluessel(hass, hass_storage, coordinators):
    """Stand einer NEUEREN Version mit zusaetzlichem Schluessel plus einem
    Altschluessel, den die Integration bewusst verwirft: alles andere bleibt."""
    from custom_components.ev_assistant.const import STORAGE_KEY, STORAGE_VERSION
    from custom_components.ev_assistant.coordinator import _empty_data

    entry = _entry(hass, "dc1")
    stored = _empty_data()
    stored["history"] = [{"config_entry_id": "dc1", "kwh": 10.0, "kosten": 3.0, "erfasst_ts": 1_700_000_000}]
    stored["zukunft_schluessel"] = {"neu": [1, 2, 3]}
    stored["panel_layout"] = [{"key": "soc", "visible": True}]  # bis 0.99.75, wird verworfen
    hass_storage[f"{STORAGE_KEY}_{entry.entry_id}"] = {"version": STORAGE_VERSION, "data": stored}

    coordinator = await _coordinator(hass, coordinators, entry)
    assert coordinator.data["history"] == stored["history"]
    assert coordinator.data["zukunft_schluessel"] == {"neu": [1, 2, 3]}
    assert "panel_layout" not in coordinator.data

    await coordinator._save()
    saved = hass_storage[f"{STORAGE_KEY}_{entry.entry_id}"]["data"]
    assert set(saved) >= set(_empty_data()), "ein Schluessel aus _empty_data() fehlt im Store"
    assert saved["zukunft_schluessel"] == {"neu": [1, 2, 3]}
    assert saved["history"] == stored["history"]


async def test_backup_export_hat_die_zusagte_struktur_und_restore_ist_ein_roundtrip(
    hass, hass_storage, coordinators,
):
    from custom_components.ev_assistant.coordinator import _empty_data

    entry = _entry(hass, "dc2")
    coordinator = await _coordinator(hass, coordinators, entry)
    coordinator.data["history"] = [{"config_entry_id": "dc2", "kwh": 5.0, "kosten": 1.5, "erfasst_ts": 1_700_000_100}]

    path = await coordinator.async_export_backup()
    assert os.path.basename(path) == "ev_assistant_backup_dc2.json"
    exported = json.loads(Path(path).read_text(encoding="utf-8"))
    assert set(exported) == set(coordinator.data) | {"_config_snapshot_readonly"}
    assert set(exported["_config_snapshot_readonly"]) == {"data", "options"}
    assert set(exported) >= set(_empty_data())

    # Restore: Konfigurations-Schnappschuss wird verworfen, der Rest ersetzt self.data
    coordinator.data["history"] = []
    assert await coordinator.async_restore_backup(json.dumps(exported)) is True
    assert "_config_snapshot_readonly" not in coordinator.data
    assert coordinator.data["history"] == exported["history"]
    assert Path(hass.config.path("www", "ev_assistant_backup_pre_restore_dc2.json")).is_file()

    # Ablehnungen aendern nichts
    before = json.dumps(coordinator.data, sort_keys=True)
    assert await coordinator.async_restore_backup("kein json") is False
    assert await coordinator.async_restore_backup(json.dumps({"ohne": "history"})) is False
    assert json.dumps(coordinator.data, sort_keys=True) == before


async def test_fahrtenbuch_csv_export_und_import_sind_ein_roundtrip(hass, hass_storage, coordinators):
    entry = _entry(hass, "dc3")
    coordinator = await _coordinator(hass, coordinators, entry)
    fahrten = [
        {
            "config_entry_id": "dc3", "datum": "2026-01-02", "start_ts": 1_767_300_000.0, "end_ts": 1_767_301_800.0,
            "odo_start": 1000.0, "odo_end": 1012.5, "km": 12.5, "start_ort": "Zuhause", "end_ort": "Arbeit",
            "erfasst_ts": 1_767_301_900, "delta_soc": -6.0, "verbrauch_kwh": 2.4,
        },
        {
            "config_entry_id": "dc3", "datum": "2026-01-01", "start_ts": 1_767_200_000.0, "end_ts": 1_767_201_000.0,
            "odo_start": 990.0, "odo_end": 1000.0, "km": 10.0, "start_ort": "Arbeit", "end_ort": "Zuhause",
            "erfasst_ts": 1_767_201_100,
        },
    ]
    coordinator.data["fahrten"] = list(fahrten)

    path = await coordinator.async_export_fahrtenbuch()
    assert os.path.basename(path) == "ev_assistant_fahrtenbuch_dc3.csv"
    rows = list(csv.reader(io.StringIO(Path(path).read_text(encoding="utf-8")), delimiter=";"))
    assert len(rows) == 3, "Kopfzeile plus zwei Fahrten"
    assert rows[0] == ["Datum", "Start", "Ziel", "km Start", "km Ende", "Strecke (km)"]
    # chronologisch aufsteigend: die Fahrt vom 01.01. zuerst
    assert rows[1] == ["2026-01-01", "Arbeit", "Zuhause", "990.0", "1000.0", "10.0"]
    assert rows[2] == ["2026-01-02", "Zuhause", "Arbeit", "1000.0", "1012.5", "12.5"]


async def test_fahrtenbuch_import_format_dubletten_und_summen(hass, hass_storage, coordinators):
    """Importformat einer Fremd-App (start/ende lokal, start_ort/ziel_ort, strecke);
    ein zweiter Import derselben Zeilen ergibt keine Dubletten."""
    coordinator = await _coordinator(hass, coordinators, _entry(hass, "dc4"))
    rows = [
        {"start": "2026-01-01 08:00:00", "ende": "2026-01-01 08:30:00", "start_ort": "A", "ziel_ort": "B",
         "strecke": 10.004, "verbrauch_kwh": 1.9},
        {"start": "2026-01-02 17:00:00", "ende": "2026-01-02 17:40:00", "start_ort": "B", "ziel_ort": "A",
         "strecke": "12.5"},
        {"start": "kaputt", "ende": "x", "start_ort": "A", "ziel_ort": "B", "strecke": 1},  # wird uebersprungen
    ]
    assert await coordinator.async_import_fahrtenbuch(rows) == 2
    fahrten = coordinator.data["fahrten"]
    assert [f["km"] for f in fahrten] == [12.5, 10.0], "neueste zuerst, auf 2 Stellen gerundet"
    assert all(f["odo_start"] is None and f["odo_end"] is None and f["quelle"] == "import" for f in fahrten)
    assert all(f["config_entry_id"] == "dc4" for f in fahrten)
    assert fahrten[1]["verbrauch_kwh"] == 1.9 and "verbrauch_kwh" not in fahrten[0]
    assert coordinator.data["trip_totals"] == {"km": 22.5, "count": 2}
    assert len({f["erfasst_ts"] for f in fahrten}) == 2, "erfasst_ts ist der Schluessel fuer edit/delete"

    assert await coordinator.async_import_fahrtenbuch(rows) == 0
    assert len(coordinator.data["fahrten"]) == 2
