"""Tests fuer die dynamische Speicher-Vorrang-Steuerung (siehe
coordinator.py::_apply_battery_priority_for_vehicle_presence(),
CONF_EVCC_BATTERY_PRIORITY_ENABLED) -- Nutzerentscheidung 2026-09-23
(Vorfall Montag: Heimspeicher lud im PV-Modus wegen fest evcc-
prioritySoc=100 immer zuerst komplett voll, das Auto fuhr genau dann
leer los, der Rest-Ueberschuss ging danach ungenutzt ins Netz): waehrend
das Auto angesteckt ist, soll es Vorrang vor dem Speicher bekommen
("der speicher nimmt ja eh dann alles auf"), dynamisch statt einer fixen
prioritySoc-Absenkung."""
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="bp1", options=None):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


def _evcc_client(priority_soc_result=True):
    client = AsyncMock()
    client.async_set_priority_soc = AsyncMock(return_value=priority_soc_result)
    return client


async def test_deaktiviert_per_default_ist_no_op(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "bp1", options={CONF_USABLE_KWH: 50.0})
    coordinator._evcc_client = _evcc_client()
    coordinator._evcc_state = {"prioritySoc": 100, "loadpoints": [{"connected": True}]}
    await coordinator._apply_battery_priority_for_vehicle_presence()
    coordinator._evcc_client.async_set_priority_soc.assert_not_called()
    assert coordinator.data.get("evcc_battery_priority_override_active", False) is False


async def test_verbunden_senkt_prioritaet_und_merkt_sich_baseline(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_BATTERY_PRIORITY_ENABLED, EVCC_BATTERY_PRIORITY_VEHICLE_SOC

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "bp2", options={CONF_EVCC_BATTERY_PRIORITY_ENABLED: True},
    )
    coordinator._evcc_client = _evcc_client()
    coordinator._evcc_state = {"prioritySoc": 100, "loadpoints": [{"connected": True}]}
    await coordinator._apply_battery_priority_for_vehicle_presence()
    coordinator._evcc_client.async_set_priority_soc.assert_awaited_once_with(EVCC_BATTERY_PRIORITY_VEHICLE_SOC)
    assert coordinator.data["evcc_battery_priority_baseline_soc"] == 100
    assert coordinator.data["evcc_battery_priority_override_active"] is True


async def test_bereits_aktiver_override_schreibt_nicht_erneut(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_BATTERY_PRIORITY_ENABLED

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "bp3", options={CONF_EVCC_BATTERY_PRIORITY_ENABLED: True},
    )
    coordinator.data["evcc_battery_priority_override_active"] = True
    coordinator.data["evcc_battery_priority_baseline_soc"] = 100
    coordinator._evcc_client = _evcc_client()
    coordinator._evcc_state = {"prioritySoc": 0, "loadpoints": [{"connected": True}]}
    await coordinator._apply_battery_priority_for_vehicle_presence()
    coordinator._evcc_client.async_set_priority_soc.assert_not_called()


async def test_abgesteckt_stellt_baseline_wieder_her(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_BATTERY_PRIORITY_ENABLED

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "bp4", options={CONF_EVCC_BATTERY_PRIORITY_ENABLED: True},
    )
    coordinator.data["evcc_battery_priority_override_active"] = True
    coordinator.data["evcc_battery_priority_baseline_soc"] = 100
    coordinator._evcc_client = _evcc_client()
    coordinator._evcc_state = {"prioritySoc": 0, "loadpoints": [{"connected": False}]}
    await coordinator._apply_battery_priority_for_vehicle_presence()
    coordinator._evcc_client.async_set_priority_soc.assert_awaited_once_with(100)
    assert coordinator.data["evcc_battery_priority_override_active"] is False


async def test_abgesteckt_ohne_override_verfolgt_baseline_nur_nach(hass, coordinators):
    """Der Nutzer hat evccs prioritySoc zwischenzeitlich selbst (z.B. in
    der evcc-UI) auf einen anderen Wert geaendert, waehrend kein Override
    aktiv war -- dieser neue Wert muss als kuenftige Baseline uebernommen
    werden, ohne dass wir selbst etwas schreiben."""
    from custom_components.ev_assistant.const import CONF_EVCC_BATTERY_PRIORITY_ENABLED

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "bp5", options={CONF_EVCC_BATTERY_PRIORITY_ENABLED: True},
    )
    coordinator._evcc_client = _evcc_client()
    coordinator._evcc_state = {"prioritySoc": 45, "loadpoints": [{"connected": False}]}
    await coordinator._apply_battery_priority_for_vehicle_presence()
    coordinator._evcc_client.async_set_priority_soc.assert_not_called()
    assert coordinator.data["evcc_battery_priority_baseline_soc"] == 45


async def test_schreibfehler_beim_verbinden_haelt_override_inaktiv_fuer_retry(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_BATTERY_PRIORITY_ENABLED

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "bp6", options={CONF_EVCC_BATTERY_PRIORITY_ENABLED: True},
    )
    coordinator._evcc_client = _evcc_client(priority_soc_result=False)
    coordinator._evcc_state = {"prioritySoc": 100, "loadpoints": [{"connected": True}]}
    await coordinator._apply_battery_priority_for_vehicle_presence()
    assert coordinator.data.get("evcc_battery_priority_override_active", False) is False


async def test_ohne_loadpoint_gilt_als_nicht_verbunden(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_BATTERY_PRIORITY_ENABLED

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "bp7", options={CONF_EVCC_BATTERY_PRIORITY_ENABLED: True},
    )
    coordinator.data["evcc_battery_priority_override_active"] = True
    coordinator.data["evcc_battery_priority_baseline_soc"] = 100
    coordinator._evcc_client = _evcc_client()
    coordinator._evcc_state = {"prioritySoc": 0, "loadpoints": []}
    await coordinator._apply_battery_priority_for_vehicle_presence()
    coordinator._evcc_client.async_set_priority_soc.assert_awaited_once_with(100)
    assert coordinator.data["evcc_battery_priority_override_active"] is False


async def test_ohne_evcc_client_ist_no_op(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_BATTERY_PRIORITY_ENABLED

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "bp8", options={CONF_EVCC_BATTERY_PRIORITY_ENABLED: True},
    )
    coordinator._evcc_client = None
    coordinator._evcc_state = {"prioritySoc": 100, "loadpoints": [{"connected": True}]}
    await coordinator._apply_battery_priority_for_vehicle_presence()
    assert coordinator.data.get("evcc_battery_priority_override_active", False) is False
