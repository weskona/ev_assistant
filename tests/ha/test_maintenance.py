"""Smoke-Tests fuer die Fahrzeugwartung-Verdrahtung (Services + Sensor,
siehe coordinator.py::async_add_maintenance() u.a./sensor.py::WartungSensor)
-- die eigentliche Faelligkeitslogik ist bereits in tests/test_engine.py
(engine.wartung_status()/wartung_uebersicht()) erschoepfend getestet."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="wart1"):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    coordinator.data["odo"] = 10000.0
    coordinator.data["odo_unit"] = "km"
    return coordinator


async def test_add_maintenance_mit_preset_fuellt_defaults(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators)

    wartung_id = await coordinator.async_add_maintenance(preset="tuev")
    assert wartung_id is not None

    punkte = coordinator.data["wartung"]
    assert len(punkte) == 1
    assert punkte[0]["name"] == "HU/TÜV"
    assert punkte[0]["zeit_intervall_monate"] == 24
    assert punkte[0]["km_intervall"] is None
    assert punkte[0]["aktiv"] is True

    stats = coordinator.wartung_stats()
    assert len(stats["punkte"]) == 1


async def test_add_maintenance_ohne_name_und_kriterium_wird_abgelehnt(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "wart2")

    ohne_name = await coordinator.async_add_maintenance(km_intervall=30000.0)
    assert ohne_name is None

    ohne_kriterium = await coordinator.async_add_maintenance(name="Nichts faelliges")
    assert ohne_kriterium is None

    assert coordinator.data["wartung"] == []


async def test_mark_maintenance_done_setzt_last_done_und_resettet_hysterese(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "wart3")
    # Reines Zeit-Kriterium, weit in der Vergangenheit faellig -- nach dem
    # Markieren als erledigt (last_done -> heute) liegt die naechste
    # Faelligkeit dank zeit_intervall_monate=12 klar in der Zukunft (kein
    # Grenzfall wie bei einem knapp gewaehlten km-Wert).
    wartung_id = await coordinator.async_add_maintenance(
        name="Inspektion", zeit_intervall_monate=12, last_done_datum="2020-01-01",
    )

    coordinator._check_wartung_thresholds()
    assert coordinator.data["wartung_notified"][str(wartung_id)]["rank"] == 2

    await coordinator.async_mark_maintenance_done(wartung_id)
    punkt = coordinator.data["wartung"][0]
    assert punkt["last_done"]["km"] == 10000.0
    assert punkt["last_done"]["datum"] is not None

    # last_done hat sich geaendert -> Hysterese fuer diesen Punkt ist wieder frisch.
    coordinator._check_wartung_thresholds()
    assert coordinator.data["wartung_notified"][str(wartung_id)]["rank"] == 0


async def test_edit_maintenance_kriterium_entfernen_und_letztes_kriterium_schuetzen(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "wart4")
    wartung_id = await coordinator.async_add_maintenance(
        name="Inspektion", km_intervall=30000.0, zeit_intervall_monate=24,
    )

    # km_intervall entfernen -- zeit_intervall_monate bleibt, also erlaubt.
    ok = await coordinator.async_edit_maintenance(wartung_id, km_intervall="")
    assert ok is True
    assert coordinator.data["wartung"][0]["km_intervall"] is None
    assert coordinator.data["wartung"][0]["zeit_intervall_monate"] == 24

    # Auch das letzte verbleibende Kriterium entfernen -- muss verworfen werden.
    abgelehnt = await coordinator.async_edit_maintenance(wartung_id, zeit_intervall_monate="")
    assert abgelehnt is False
    assert coordinator.data["wartung"][0]["zeit_intervall_monate"] == 24  # unveraendert


async def test_delete_maintenance_entfernt_punkt_und_notified_eintrag(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "wart5")
    wartung_id = await coordinator.async_add_maintenance(name="Bremsfluessigkeit", zeit_intervall_monate=24)
    coordinator._check_wartung_thresholds()

    geloescht = await coordinator.async_delete_maintenance(wartung_id)
    assert geloescht is True
    assert coordinator.data["wartung"] == []
    assert str(wartung_id) not in coordinator.data["wartung_notified"]


async def test_migration_zeit_intervall_tage_auf_monate(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "wart7")
    # Alt-Eintrag direkt injiziert (bypasst async_add_maintenance(), das das
    # alte Feld gar nicht mehr kennt) -- simuliert einen bestehenden Punkt
    # aus einer Installation von vor der Monats-Umstellung.
    coordinator.data["wartung"] = [
        {"id": 1, "name": "Alt-Inspektion", "zeit_intervall_tage": 730, "aktiv": True},
    ]

    geaendert = coordinator._migrate_wartung_zeit_einheiten()
    assert geaendert is True
    punkt = coordinator.data["wartung"][0]
    assert punkt["zeit_intervall_monate"] == 24
    assert "zeit_intervall_tage" not in punkt

    # Idempotent: ein zweiter Lauf findet nichts mehr zu tun.
    assert coordinator._migrate_wartung_zeit_einheiten() is False
    assert coordinator.data["wartung"][0]["zeit_intervall_monate"] == 24


async def test_add_maintenance_reminder_monate_wird_zu_reminder_tage(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "wart8")
    wartung_id = await coordinator.async_add_maintenance(
        name="Mit Erinnerung", zeit_intervall_monate=24, reminder_monate=1.0, reminder_km=500.0,
    )
    punkt = coordinator.data["wartung"][0]
    assert punkt["id"] == wartung_id
    assert punkt["reminder_tage"] == 30.4  # 1 Monat * WARTUNG_TAGE_PRO_MONAT (30.44), gerundet
    assert punkt["reminder_km"] == 500.0


async def test_mark_maintenance_done_schreibt_festes_datum_fort(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "wart9")
    wartung_id = await coordinator.async_add_maintenance(
        name="HU/TÜV", festes_datum="2029-07-15", zeit_intervall_monate=24,
    )

    await coordinator.async_mark_maintenance_done(wartung_id, datum="2029-09-01")
    punkt = coordinator.data["wartung"][0]
    assert punkt["festes_datum"] == "2031-09-01"
    assert punkt["last_done"]["datum"] == "2029-09-01"


async def test_wartung_sensor_native_value_und_presets_attribut(hass, coordinators):
    from custom_components.ev_assistant.sensor import WartungSensor

    coordinator = await _make_coordinator(hass, coordinators, "wart6")
    entry = coordinator.entry
    sensor = WartungSensor(coordinator, entry)

    assert sensor.native_value is None  # ohne jeden Punkt: unknown

    await coordinator.async_add_maintenance(name="Ueberfaellig", festes_datum="2020-01-01")
    assert sensor.native_value == 1

    attrs = sensor.extra_state_attributes
    assert len(attrs["punkte"]) == 1
    assert attrs["punkte"][0]["status"] == "ueberfaellig"
    preset_keys = {p["key"] for p in attrs["presets"]}
    assert "tuev" in preset_keys and "inspektion" in preset_keys
