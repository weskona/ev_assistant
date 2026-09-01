"""Tests fuer coordinator.py::evcc_live_attrs() -- insbesondere die
Korrektur von "limit_soc"/neue "min_soc"/"connected"-Felder (siehe
Uebersicht-Beta-Redesign): evcc kann Min-/Ziel-SoC je nach Version
entweder auf Loadpoint- oder Fahrzeug-Ebene fuehren (siehe
evcc_client.py::async_probe_scope()) -- bei Fahrzeug-Scope bleibt das
rohe Loadpoint-Feld ("limitSoc"/"minSoc") auf 0/unbelegt stehen, waehrend
evccs eigene "effective*"-Felder den tatsaechlich wirksamen Wert
unabhaengig vom Scope liefern."""


async def _make_coordinator(hass, coordinators, entry_id="live1"):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator


async def test_evcc_live_attrs_ohne_evcc_state_gibt_leeres_dict(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "live1")
    assert coordinator.evcc_live_attrs() == {}


async def test_evcc_live_attrs_limit_soc_bevorzugt_effective_bei_fahrzeug_scope(hass, coordinators):
    """Regression: bei Fahrzeug-Scope (min-/limitSoc auf dem Fahrzeug statt
    dem Loadpoint gefuehrt) blieb das rohe Loadpoint-Feld "limitSoc" auf 0
    stehen, obwohl der tatsaechlich wirksame Wert (effectiveLimitSoc) ganz
    anders war -- reale evcc-0.314.5-Situation, siehe CHANGELOG."""
    coordinator = await _make_coordinator(hass, coordinators, "live2")
    coordinator._evcc_state = {
        "loadpoints": [{"limitSoc": 0, "minSoc": 0, "effectiveLimitSoc": 80, "effectiveMinSoc": 3}],
    }
    attrs = coordinator.evcc_live_attrs()
    assert attrs["limit_soc"] == 80
    assert attrs["min_soc"] == 3


async def test_evcc_live_attrs_limit_soc_faellt_auf_rohes_feld_zurueck_ohne_effective(hass, coordinators):
    """Aeltere evcc-Versionen ohne "effective*"-Felder -- graceful
    Fallback auf das rohe Feld statt None/Absturz."""
    coordinator = await _make_coordinator(hass, coordinators, "live3")
    coordinator._evcc_state = {"loadpoints": [{"limitSoc": 80, "minSoc": 20}]}
    attrs = coordinator.evcc_live_attrs()
    assert attrs["limit_soc"] == 80
    assert attrs["min_soc"] == 20


async def test_evcc_live_attrs_connected_feld(hass, coordinators):
    """"connected" (neu) ist eine ANDERE Frage als "charging": ein
    Fahrzeug kann angesteckt/verbunden sein, ohne gerade Leistung zu
    ziehen (z.B. Modus "off", oder Ziel-SoC bereits erreicht)."""
    coordinator = await _make_coordinator(hass, coordinators, "live4")
    coordinator._evcc_state = {"loadpoints": [{"connected": True, "charging": False}]}
    attrs = coordinator.evcc_live_attrs()
    assert attrs["connected"] is True
    assert attrs["charging"] is False


async def test_evcc_live_attrs_connected_fehlt_ohne_loadpoint_feld(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "live5")
    coordinator._evcc_state = {"loadpoints": [{}]}
    attrs = coordinator.evcc_live_attrs()
    assert attrs["connected"] is None
