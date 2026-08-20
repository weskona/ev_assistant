"""Regressionsnetz fuer coordinator._async_truncate_lifetime_lists() (siehe
dort, CHANGELOG v0.70.0): Eintraege aelter als FAHRTEN_MAX_MONATE/
HISTORY_MAX_MONATE wandern in ein separates Archiv statt geloescht zu
werden; export_fahrtenbuch()/import_fahrtenbuch() muessen das Archiv
weiterhin vollstaendig beruecksichtigen; kumulative Kennzahlen bleiben
unveraendert."""
import time

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _fahrt(start_ts, km, erfasst_ts=None, delta_soc=None, verbrauch_kwh=None):
    return {
        "config_entry_id": "poc", "datum": "2024-01-01",
        "start_ts": start_ts, "end_ts": start_ts + 1800,
        "odo_start": None, "odo_end": None,
        "km": km, "start_ort": "A", "end_ort": "B",
        "erfasst_ts": erfasst_ts if erfasst_ts is not None else int(start_ts),
        **({"delta_soc": delta_soc} if delta_soc is not None else {}),
        **({"verbrauch_kwh": verbrauch_kwh} if verbrauch_kwh is not None else {}),
    }


def _charge(erfasst_ts, kwh, kosten, delta_soc=None):
    rec = {
        "config_entry_id": "poc", "kwh": kwh, "preis_kwh": round(kosten / kwh, 4),
        "startgebuehr": 0.0, "blockiergebuehr": 0.0, "zeitgebuehr": 0.0,
        "kosten": kosten, "erfasst_ts": erfasst_ts,
    }
    if delta_soc is not None:
        rec["delta_soc"] = delta_soc
    return rec


async def _setup_with_data(hass, hass_storage, coordinators, entry_id, fahrten, history):
    from custom_components.ev_assistant.const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    hass_storage[f"{STORAGE_KEY}_{entry.entry_id}"] = {
        "version": STORAGE_VERSION,
        "data": {"fahrten": list(fahrten), "history": list(history)},
    }
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


async def test_archivierung_verschiebt_alte_eintraege_und_erhaelt_kennzahlen(hass, hass_storage, coordinators):
    from custom_components.ev_assistant.const import STORAGE_KEY
    from custom_components.ev_assistant.engine import equivalent_full_cycles

    now = time.time()
    alt_ts = now - 1000 * 86400  # ~2,7 Jahre -- ueber der 24-Monats-Schwelle
    fahrten = [
        _fahrt(alt_ts, 20.0, delta_soc=-30.0, verbrauch_kwh=5.0),
        _fahrt(now, 10.0, delta_soc=-15.0, verbrauch_kwh=2.5),
    ]
    history = [_charge(int(alt_ts), 20.0, 10.0, delta_soc=50.0)]

    coordinator, entry = await _setup_with_data(hass, hass_storage, coordinators, "arch1", fahrten, history)
    erwartete_cycles = equivalent_full_cycles(fahrten, history, 0.0)
    assert coordinator.equivalent_full_cycles() == erwartete_cycles

    await coordinator._async_truncate_lifetime_lists()

    assert [f["start_ts"] for f in coordinator.data["fahrten"]] == [now]
    assert coordinator.data["history"] == []

    archiv_key = f"{STORAGE_KEY}_{entry.entry_id}_archiv"
    assert archiv_key in hass_storage
    archiv = hass_storage[archiv_key]["data"]
    assert [f["start_ts"] for f in archiv["fahrten"]] == [alt_ts]
    assert len(archiv["history"]) == 1

    # Kernanforderung: die Kennzahl bleibt trotz gekuerzter Liste identisch.
    assert coordinator.equivalent_full_cycles() == erwartete_cycles


async def test_archivierung_ohne_alte_eintraege_ist_no_op(hass, hass_storage, coordinators):
    from custom_components.ev_assistant.const import STORAGE_KEY

    fahrten = [_fahrt(time.time(), 10.0, verbrauch_kwh=2.0)]
    coordinator, entry = await _setup_with_data(hass, hass_storage, coordinators, "arch2", fahrten, [])

    archiv_key = f"{STORAGE_KEY}_{entry.entry_id}_archiv"
    await coordinator._async_truncate_lifetime_lists()
    # Kein Archiv-Schreibzugriff, wenn nichts zu kuerzen war (siehe Docstring).
    assert archiv_key not in hass_storage
    assert len(coordinator.data["fahrten"]) == 1


async def test_archivierung_ist_idempotent_bei_wiederholtem_lauf(hass, hass_storage, coordinators):
    now = time.time()
    alt_ts = now - 1000 * 86400
    fahrten = [_fahrt(alt_ts, 20.0, verbrauch_kwh=5.0), _fahrt(now, 10.0, verbrauch_kwh=2.0)]

    coordinator, entry = await _setup_with_data(hass, hass_storage, coordinators, "arch3", fahrten, [])
    await coordinator._async_truncate_lifetime_lists()
    stand_nach_erstem_lauf = list(coordinator.data["fahrten"])

    # Zweiter taeglicher Lauf ohne neu hinzugekommene alte Eintraege darf
    # nichts mehr veraendern.
    await coordinator._async_truncate_lifetime_lists()
    assert coordinator.data["fahrten"] == stand_nach_erstem_lauf


async def test_export_fahrtenbuch_fuehrt_archiv_und_aktuelle_liste_zusammen(
    hass, hass_storage, coordinators, tmp_path
):
    now = time.time()
    alt_ts = now - 1000 * 86400
    fahrten = [_fahrt(alt_ts, 20.0, verbrauch_kwh=5.0), _fahrt(now, 10.0, verbrauch_kwh=2.0)]

    coordinator, entry = await _setup_with_data(hass, hass_storage, coordinators, "arch4", fahrten, [])
    await coordinator._async_truncate_lifetime_lists()
    assert len(coordinator.data["fahrten"]) == 1  # tatsaechlich gekuerzt (Testaufbau)

    hass.config.config_dir = str(tmp_path)
    path = await coordinator.async_export_fahrtenbuch()

    with open(path, encoding="utf-8") as f:
        content = f.read()
    # Beide Fahrten (die archivierte UND die aktuelle) muessen im Export sein.
    assert content.count("\n") - 1 == 2  # Kopfzeile + 2 Datenzeilen


async def test_import_fahrtenbuch_erzeugt_keine_dubletten_fuer_archivierte_fahrten(
    hass, hass_storage, coordinators
):
    from datetime import datetime

    from homeassistant.util import dt as dt_util

    # Ganzzahlige Sekunden, wie sie auch ein echter Fahrtenbuch-Import
    # erzeugt (siehe coordinator.py::async_import_fahrtenbuch(), Format
    # "YYYY-MM-DD HH:MM:SS") -- sonst wuerde die Nachkommastellen-Praezision
    # von time.time() den Vergleich gegen den beim erneuten Import neu
    # geparsten start_ts verfaelschen (kein Bug, nur eine Testdaten-Falle).
    # dt_util.DEFAULT_TIME_ZONE statt UTC/lokaler Zeit, weil
    # async_import_fahrtenbuch() den geparsten String explizit MIT DIESER
    # (vom hass-Fixture ggf. auf eine Test-Zeitzone gesetzten) Zone versieht.
    alt_ts = float(int(time.time() - 1000 * 86400))
    alt_start_dt = datetime.fromtimestamp(alt_ts, tz=dt_util.DEFAULT_TIME_ZONE)
    fahrten = [_fahrt(alt_ts, 20.0, verbrauch_kwh=5.0)]

    coordinator, entry = await _setup_with_data(hass, hass_storage, coordinators, "arch5", fahrten, [])
    await coordinator._async_truncate_lifetime_lists()
    assert coordinator.data["fahrten"] == []  # einzige Fahrt jetzt im Archiv

    # Erneuter Import derselben (jetzt ausschliesslich archivierten) Fahrt.
    anzahl_importiert = await coordinator.async_import_fahrtenbuch([{
        "start": alt_start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "ende": datetime.fromtimestamp(alt_ts + 1800, tz=dt_util.DEFAULT_TIME_ZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "start_ort": "A", "ziel_ort": "B", "strecke": 20.0,
    }])

    assert anzahl_importiert == 0  # Dublette, siehe Docstring
    assert coordinator.data["fahrten"] == []
