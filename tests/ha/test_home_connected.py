"""Tests fuer coordinator.py::_home_connected() -- Quelle fuer
ChargeSample.home_connected (Issue #7: BMS-Rebalancing nach Ladeende darf
nicht als Fremdladung erkannt werden, solange das Fahrzeug am eigenen
Ladepunkt haengt). Der Stecker-Sensor (CONF_PLUG_ENTITY) fliesst bewusst
NICHT ein, er ist auch an einer fremden Ladesaeule True."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id, options=None):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator


async def test_ohne_evcc_und_ohne_wallbox_sensor_ist_none(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "hc1")
    assert coordinator._home_connected() is None


async def test_evcc_connected_wird_uebernommen(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "hc2")
    coordinator._evcc_state = {"loadpoints": [{"connected": True}]}
    assert coordinator._home_connected() is True
    coordinator._evcc_state = {"loadpoints": [{"connected": False}]}
    assert coordinator._home_connected() is False


async def test_evcc_unbekannt_ist_none(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "hc3")
    coordinator._evcc_state = {"loadpoints": [{}]}
    assert coordinator._home_connected() is None
    coordinator._evcc_state = None
    assert coordinator._home_connected() is None


async def test_wallbox_connected_entity_hat_vorrang_vor_evcc(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "hc4")
    coordinator._evcc_state = {"loadpoints": [{"connected": True}]}
    coordinator._wallbox_connected_override = False
    assert coordinator._home_connected() is False


async def test_plug_sensor_fliesst_nicht_ein(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "hc5")
    coordinator._plugged_in = True
    assert coordinator._home_connected() is None


async def test_anderes_fahrzeug_am_ladepunkt_ist_none(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator = await _make_coordinator(
        hass, coordinators, "hc6", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator._evcc_state = {
        "vehicles": {"db:8": {"title": "eRifter"}, "db:9": {"title": "Zoe"}},
        "loadpoints": [{"connected": True, "vehicleName": "db:9"}],
    }
    assert coordinator._home_connected() is None
    coordinator._evcc_state["loadpoints"][0]["vehicleName"] = "db:8"
    assert coordinator._home_connected() is True
