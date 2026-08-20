"""Regressionsnetz fuer coordinator._migrate_lifetime_baselines() (siehe
dort): einmalige Ruecksicherung der Lebenszeit-Baselines aus einer bereits
vorhandenen fahrten/history-Liste beim ersten Start nach dem Upgrade auf die
Fahrtenbuch/History-Archivierung (siehe CHANGELOG v0.70.0). Muss exakt
dieselben Werte liefern wie eine direkte Berechnung ueber die volle Liste
(engine.equivalent_full_cycles() u.a.) und beim zweiten Aufruf idempotent
sein (kein Doppel-Backfill)."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _fahrt(start_ts, km, delta_soc=None, verbrauch_kwh=None, temp_start=None):
    """Ein vollstaendiger fahrten-Datensatz (alle Felder, die reale Fahrten
    immer haben, siehe coordinator.py::_build_trip_record()) -- ohne das
    wuerde z.B. async_export_fahrtenbuch() mit KeyError auf 'odo_start'
    scheitern, das echte Datensaetze immer (ggf. als None) mitfuehren."""
    rec = {
        "config_entry_id": "poc", "datum": "2024-01-01",
        "start_ts": start_ts, "end_ts": start_ts + 1800,
        "odo_start": None, "odo_end": None,
        "km": km, "start_ort": "A", "end_ort": "B",
        "erfasst_ts": int(start_ts),
    }
    if delta_soc is not None:
        rec["delta_soc"] = delta_soc
    if verbrauch_kwh is not None:
        rec["verbrauch_kwh"] = verbrauch_kwh
    if temp_start is not None:
        rec["temp_start"] = temp_start
    return rec


def _charge(erfasst_ts, kwh, kosten, delta_soc=None, dauer_min=None, anbieter=None):
    """Ein vollstaendiger history-Datensatz, siehe coordinator.py::
    async_log_charge()."""
    rec = {
        "config_entry_id": "poc", "kwh": kwh, "preis_kwh": round(kosten / kwh, 4),
        "startgebuehr": 0.0, "blockiergebuehr": 0.0, "zeitgebuehr": 0.0,
        "kosten": kosten, "erfasst_ts": erfasst_ts,
    }
    if delta_soc is not None:
        rec["delta_soc"] = delta_soc
    if dauer_min is not None:
        rec["dauer_min"] = dauer_min
    if anbieter is not None:
        rec["anbieter"] = anbieter
    return rec


async def test_migration_backfill_entspricht_voller_liste_berechnung(hass, hass_storage, coordinators):
    from custom_components.ev_assistant.const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator
    from custom_components.ev_assistant.engine import (
        ac_dc_breakdown,
        ac_dc_breakdown_from_totals,
        anbieter_breakdown,
        anbieter_breakdown_from_totals,
        consumption_by_temp_bucket,
        consumption_by_temp_bucket_from_totals,
        equivalent_full_cycles,
    )

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="mig1")
    entry.add_to_hass(hass)

    fahrten = [
        _fahrt(1000.0, 20.0, delta_soc=-30.0, verbrauch_kwh=5.0, temp_start=15.0),
        _fahrt(2000.0, 15.0, delta_soc=-20.0, verbrauch_kwh=3.5, temp_start=16.0),
        _fahrt(3000.0, 10.0, delta_soc=-12.0, verbrauch_kwh=2.0, temp_start=14.0),
    ]
    history = [
        _charge(500, 20.0, 10.0, delta_soc=50.0, dauer_min=60.0, anbieter="EnBW"),
        _charge(1500, 30.0, 21.0, delta_soc=40.0, dauer_min=20.0, anbieter="Ionity"),
    ]
    # Bewusst OHNE lifetime_baselines_migrated/*_totals -- simuliert eine
    # Bestandsinstallation von vor der Archivierungs-Version (v0.70.0).
    hass_storage[f"{STORAGE_KEY}_{entry.entry_id}"] = {
        "version": STORAGE_VERSION,
        "data": {
            "fahrten": fahrten, "history": history,
            "totals": {"kwh": 50.0, "kosten": 31.0, "count": 2},
            "trip_totals": {"km": 45.0, "count": 3},
        },
    }

    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()

    assert coordinator.data["lifetime_baselines_migrated"] is True

    # Vollzyklen: identisch zur direkten Berechnung auf denselben Rohdaten.
    erwartete_cycles = equivalent_full_cycles(fahrten, history, 0.0)
    assert coordinator.equivalent_full_cycles() == erwartete_cycles

    # AC/DC-, Anbieter- und Temperaturband-Aufschluesselung ebenso.
    assert ac_dc_breakdown_from_totals(coordinator.data["ac_dc_totals"]) == ac_dc_breakdown(history)
    assert anbieter_breakdown_from_totals(coordinator.data["anbieter_totals"]) == anbieter_breakdown(history)
    assert consumption_by_temp_bucket_from_totals(
        coordinator.data["temp_bucket_totals"], min_samples=1
    ) == consumption_by_temp_bucket(fahrten, min_samples=1)

    # Kosten/kWh gesamt und €/100km haengen an totals/trip_totals/odo, nicht
    # an fahrten/history -- die migriert das Setup nicht neu, sie waren
    # schon vorher baseline-basiert (siehe Diagnose vor v0.70.0).
    assert coordinator.data["totals"] == {"kwh": 50.0, "kosten": 31.0, "count": 2}
    assert coordinator.data["trip_totals"] == {"km": 45.0, "count": 3}


async def test_migration_zweiter_aufruf_ist_idempotent(hass, hass_storage, coordinators):
    from custom_components.ev_assistant.const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="mig2")
    entry.add_to_hass(hass)

    fahrten = [_fahrt(1000.0, 20.0, delta_soc=-30.0, verbrauch_kwh=5.0)]
    history = [_charge(500, 20.0, 10.0, delta_soc=50.0)]
    hass_storage[f"{STORAGE_KEY}_{entry.entry_id}"] = {
        "version": STORAGE_VERSION,
        "data": {"fahrten": fahrten, "history": history},
    }

    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    cycles_nach_erstem_setup = coordinator.equivalent_full_cycles()
    discharge_nach_erstem_setup = coordinator.data["fahrten_discharge_pct_total"]

    # Erneuter Migrationsversuch (z.B. bei einem zweiten Neustart) darf NICHT
    # erneut ueber fahrten/history summieren -- sonst wuerden die Baselines
    # bei jedem Neustart verdoppelt.
    ran = coordinator._migrate_lifetime_baselines()
    assert ran is False
    assert coordinator.data["fahrten_discharge_pct_total"] == discharge_nach_erstem_setup
    assert coordinator.equivalent_full_cycles() == cycles_nach_erstem_setup


async def test_migration_leere_bestandsinstallation_liefert_nullwerte(hass, hass_storage, coordinators):
    """Bestandsinstallation ganz ohne Fahrten/Ladungen (z.B. frisch
    eingerichtetes, noch ungenutztes Fahrzeug) -- Migration muss ein
    sauberes Nullergebnis liefern, keine Exception."""
    from custom_components.ev_assistant.const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="mig3")
    entry.add_to_hass(hass)
    hass_storage[f"{STORAGE_KEY}_{entry.entry_id}"] = {
        "version": STORAGE_VERSION, "data": {"fahrten": [], "history": []},
    }

    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()

    assert coordinator.data["lifetime_baselines_migrated"] is True
    assert coordinator.equivalent_full_cycles() == 0.0
    assert coordinator.data["fahrtenbuch_first_ts"] is None
