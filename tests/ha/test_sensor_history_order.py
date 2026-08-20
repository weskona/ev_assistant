"""Regressionsnetz fuer die Anzeigereihenfolge von LastCostSensor.historie
und LastTripSensor.fahrtenbuch (siehe sensor.py): beide muessen nach dem
tatsaechlichen Zeitpunkt (start_ts) absteigend sortiert sein, unabhaengig
von der Bestaetigungs-/Speicherreihenfolge in self.data["history"]/
["fahrten"] -- sonst landet eine nachtraeglich manuell erfasste oder
spaeter bestaetigte/bearbeitete Ladung bzw. Fahrt an der falschen
chronologischen Position im Panel."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _make_coordinator(hass, coordinators, entry_id):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    return coordinator, entry


async def test_last_cost_sensor_historie_sortiert_nach_start_ts(hass, coordinators):
    from custom_components.ev_assistant.sensor import LastCostSensor

    coordinator, entry = _make_coordinator(hass, coordinators, "sort1")
    await coordinator.async_setup()

    # Speicherreihenfolge (Bestaetigung) != chronologische Reihenfolge:
    # der ZULETZT bestaetigte Eintrag (erfasst_ts=300, Index 0) liegt
    # chronologisch in der MITTE (start_ts=500) -- eine nachtraeglich
    # manuell erfasste aeltere Ladung (start_ts=100) wurde erst DANACH
    # eingetragen (erfasst_ts=200) und landet dadurch an Index 1.
    coordinator.data["history"] = [
        {"erfasst_ts": 300, "start_ts": 500, "kwh": 20.0, "kosten": 10.0},  # zuletzt bestaetigt, mittlere Zeit
        {"erfasst_ts": 200, "start_ts": 100, "kwh": 5.0, "kosten": 2.5},    # nachtraeglich erfasst, aelteste Zeit
        {"erfasst_ts": 100, "start_ts": 900, "kwh": 30.0, "kosten": 15.0},  # zuerst bestaetigt, juengste Zeit
    ]

    sensor = LastCostSensor(coordinator, entry)
    historie = sensor.extra_state_attributes["historie"]

    assert [h["start_ts"] for h in historie] == [900, 500, 100]
    # native_value bleibt bewusst an der Speicherreihenfolge (hist[0]) --
    # "zuletzt bestaetigt", nicht "chronologisch juengste".
    assert sensor.native_value == 10.0


async def test_last_cost_sensor_historie_ohne_start_ts_faellt_auf_erfasst_ts_zurueck(hass, coordinators):
    from custom_components.ev_assistant.sensor import LastCostSensor

    coordinator, entry = _make_coordinator(hass, coordinators, "sort2")
    await coordinator.async_setup()

    # Ein Eintrag ganz ohne start_ts (z.B. ein rein manueller Alt-Eintrag)
    # darf nicht verschwinden, sondern degradiert auf erfasst_ts.
    coordinator.data["history"] = [
        {"erfasst_ts": 50, "kwh": 1.0, "kosten": 0.5},
        {"erfasst_ts": 200, "start_ts": 100, "kwh": 2.0, "kosten": 1.0},
    ]

    sensor = LastCostSensor(coordinator, entry)
    historie = sensor.extra_state_attributes["historie"]

    assert len(historie) == 2
    assert historie[0]["start_ts"] == 100
    assert historie[1]["erfasst_ts"] == 50


async def test_last_trip_sensor_fahrtenbuch_sortiert_nach_start_ts(hass, coordinators):
    from custom_components.ev_assistant.sensor import LastTripSensor

    coordinator, entry = _make_coordinator(hass, coordinators, "sort3")
    await coordinator.async_setup()

    # Analog: async_edit_trip(start_ts=...) kann start_ts nachtraeglich
    # aendern, ohne die Liste neu zu sortieren.
    coordinator.data["fahrten"] = [
        {"erfasst_ts": 300, "start_ts": 500, "km": 10.0},
        {"erfasst_ts": 200, "start_ts": 100, "km": 5.0},
        {"erfasst_ts": 100, "start_ts": 900, "km": 20.0},
    ]

    sensor = LastTripSensor(coordinator, entry)
    fahrtenbuch = sensor.extra_state_attributes["fahrtenbuch"]

    assert [f["start_ts"] for f in fahrtenbuch] == [900, 500, 100]
    assert sensor.native_value == 10.0  # native_value: weiterhin fahrten[0] (Speicherreihenfolge)
