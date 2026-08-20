"""Regressionsnetz fuer config_flow._carry_forward() (siehe dort) -- der
Options-Flow-Schritt "modus" ueberspringt bei LADE_MODUS_NUR_AUSWAERTS die
Schritte "evcc"/"ladeleistung"; _carry_forward() soll verhindern, dass deren
bereits konfigurierte Werte dabei aus entry.data verschwinden (siehe
async_step_vergleich()'s "preserved"-Logik, die alle Schema-Keys sonst als
"nicht mehr angegeben" behandelt). Bisher 0 Testreferenzen -- reine
Testhaertung, kein Verhaltenswechsel."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _make_entry(hass):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_VEHICLE_NAME,
        CONF_HOME_ENTITY,
        CONF_LADE_MODUS,
        CONF_POWER_ENTITY,
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        CONF_WALLBOX_ENERGY_ENTITY,
        DOMAIN,
        LADE_MODUS_GEMISCHT,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VEHICLE_HERSTELLER: "Testmarke",
            CONF_VEHICLE_MODELL: "Testmodell",
            CONF_SOC_ENTITY: "sensor.test_soc",
            CONF_USABLE_KWH: 50.0,
            CONF_LADE_MODUS: LADE_MODUS_GEMISCHT,
            CONF_EVCC_VEHICLE_NAME: "mein_auto",
            CONF_HOME_ENTITY: "binary_sensor.wallbox_laedt",
            CONF_POWER_ENTITY: "sensor.wallbox_leistung",
            CONF_WALLBOX_ENERGY_ENTITY: "sensor.wallbox_energie",
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


async def _run_to_end(flow, hass, steps: list[dict]) -> None:
    """Treibt den Options-Flow vom Init-Schritt bis "vergleich" durch, mit
    genau den user_input-Dicts aus `steps` fuer fahrzeug/modus/[evcc/
    ladeleistung]/ausgabe/erkennung/fahrtenbuch/leasing/vergleich (je nach
    Lade-Modus werden evcc/ladeleistung uebersprungen, siehe
    async_step_modus())."""
    flow.hass = hass
    result = await flow.async_step_init()
    for user_input in steps:
        assert result["type"] == "form", result
        step_id = result["step_id"]
        handler = getattr(flow, f"async_step_{step_id}")
        result = await handler(user_input)
    assert result["type"] == "create_entry", result


async def test_wechsel_zu_nur_auswaerts_erhaelt_evcc_wallbox_werte(hass):
    """Wechsel gemischt -> nur_auswaerts darf die bereits konfigurierten
    evcc/Wallbox-Werte NICHT aus entry.data entfernen, obwohl die
    zugehoerigen Formulare diesmal uebersprungen werden."""
    from custom_components.ev_assistant.config_flow import EvAssistantOptionsFlow
    from custom_components.ev_assistant.const import (
        CONF_EVCC_VEHICLE_NAME,
        CONF_HOME_ENTITY,
        CONF_LADE_MODUS,
        CONF_POWER_ENTITY,
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        CONF_WALLBOX_ENERGY_ENTITY,
        LADE_MODUS_NUR_AUSWAERTS,
    )

    entry = _make_entry(hass)
    flow = EvAssistantOptionsFlow(entry)

    await _run_to_end(flow, hass, [
        {CONF_VEHICLE_HERSTELLER: "Testmarke", CONF_VEHICLE_MODELL: "Testmodell",
         CONF_SOC_ENTITY: "sensor.test_soc", CONF_USABLE_KWH: 50.0},
        {CONF_LADE_MODUS: LADE_MODUS_NUR_AUSWAERTS},  # evcc/ladeleistung werden uebersprungen
        {},  # ausgabe
        {},  # erkennung
        {},  # fahrtenbuch
        {},  # leasing
        {},  # vergleich
    ])

    # Genau der Datenverlust-Fall, den _carry_forward() verhindern soll:
    assert entry.data[CONF_EVCC_VEHICLE_NAME] == "mein_auto"
    assert entry.data[CONF_HOME_ENTITY] == "binary_sensor.wallbox_laedt"
    assert entry.data[CONF_POWER_ENTITY] == "sensor.wallbox_leistung"
    assert entry.data[CONF_WALLBOX_ENERGY_ENTITY] == "sensor.wallbox_energie"
    assert entry.data[CONF_LADE_MODUS] == LADE_MODUS_NUR_AUSWAERTS


async def test_zurueckwechseln_zu_gemischt_zeigt_erhaltene_werte_vorbefuellt(hass):
    """Nach nur_auswaerts -> gemischt (zurueck) muessen die evcc/Wallbox-
    Formulare wieder mit den unveraendert erhaltenen alten Werten
    vorbefuellt erscheinen (async_step_evcc()/async_step_ladeleistung()
    lesen self._current(), das entry.data einschliesst)."""
    from custom_components.ev_assistant.config_flow import EvAssistantOptionsFlow
    from custom_components.ev_assistant.const import (
        CONF_EVCC_VEHICLE_NAME,
        CONF_HOME_ENTITY,
        CONF_LADE_MODUS,
        CONF_POWER_ENTITY,
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        CONF_WALLBOX_ENERGY_ENTITY,
        LADE_MODUS_GEMISCHT,
        LADE_MODUS_NUR_AUSWAERTS,
    )

    entry = _make_entry(hass)

    # Erst auf nur_auswaerts wechseln (wie im ersten Test).
    flow1 = EvAssistantOptionsFlow(entry)
    await _run_to_end(flow1, hass, [
        {CONF_VEHICLE_HERSTELLER: "Testmarke", CONF_VEHICLE_MODELL: "Testmodell",
         CONF_SOC_ENTITY: "sensor.test_soc", CONF_USABLE_KWH: 50.0},
        {CONF_LADE_MODUS: LADE_MODUS_NUR_AUSWAERTS},
        {}, {}, {}, {}, {},
    ])

    # Neuer Flow-Durchlauf, zurueck auf gemischt.
    flow2 = EvAssistantOptionsFlow(entry)
    flow2.hass = hass
    await flow2.async_step_init()
    await flow2.async_step_fahrzeug({
        CONF_VEHICLE_HERSTELLER: "Testmarke", CONF_VEHICLE_MODELL: "Testmodell",
        CONF_SOC_ENTITY: "sensor.test_soc", CONF_USABLE_KWH: 50.0,
    })
    result = await flow2.async_step_modus({CONF_LADE_MODUS: LADE_MODUS_GEMISCHT})
    assert result["step_id"] == "evcc"
    evcc_defaults = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if getattr(key, "description", None)
    }
    assert evcc_defaults[CONF_EVCC_VEHICLE_NAME] == "mein_auto"
    assert evcc_defaults[CONF_HOME_ENTITY] == "binary_sensor.wallbox_laedt"

    result = await flow2.async_step_evcc({
        CONF_EVCC_VEHICLE_NAME: "mein_auto", CONF_HOME_ENTITY: "binary_sensor.wallbox_laedt",
    })
    assert result["step_id"] == "ladeleistung"
    power_defaults = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if getattr(key, "description", None)
    }
    assert power_defaults[CONF_POWER_ENTITY] == "sensor.wallbox_leistung"
    assert power_defaults[CONF_WALLBOX_ENERGY_ENTITY] == "sensor.wallbox_energie"


async def test_carry_forward_kopiert_nur_fehlende_schluessel():
    """Reiner Logik-Test von _carry_forward() selbst (siehe engine-artige
    Randfaelle: bereits gesetzte Werte in `data` gewinnen gegen `current`)."""
    from custom_components.ev_assistant.config_flow import _carry_forward, build_evcc_schema
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME, CONF_HOME_ENTITY

    current = {CONF_EVCC_VEHICLE_NAME: "alt", CONF_HOME_ENTITY: "binary_sensor.alt"}
    data = {CONF_EVCC_VEHICLE_NAME: "neu"}  # bereits explizit gesetzt -- darf NICHT ueberschrieben werden
    result = _carry_forward(current, data, build_evcc_schema({}))
    assert result[CONF_EVCC_VEHICLE_NAME] == "neu"
    assert result[CONF_HOME_ENTITY] == "binary_sensor.alt"


async def test_mode_switch_beruehrt_keine_coordinator_historie(hass, coordinators):
    """_carry_forward()/der Options-Flow duerfen self.data (fahrten/history/
    totals/Perioden, siehe coordinator.py) nicht anfassen -- der Flow
    schreibt ausschliesslich entry.data/entry.options, niemals den
    Coordinator-Zustand."""
    from custom_components.ev_assistant.config_flow import EvAssistantOptionsFlow
    from custom_components.ev_assistant.const import (
        CONF_LADE_MODUS,
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        LADE_MODUS_NUR_AUSWAERTS,
    )
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = _make_entry(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    coordinator.data["fahrten"] = [{"start_ts": 1.0, "km": 5.0}]
    coordinator.data["totals"] = {"kwh": 12.0, "kosten": 6.0, "count": 3}
    vorher = dict(coordinator.data)

    flow = EvAssistantOptionsFlow(entry)
    await _run_to_end(flow, hass, [
        {CONF_VEHICLE_HERSTELLER: "Testmarke", CONF_VEHICLE_MODELL: "Testmodell",
         CONF_SOC_ENTITY: "sensor.test_soc", CONF_USABLE_KWH: 50.0},
        {CONF_LADE_MODUS: LADE_MODUS_NUR_AUSWAERTS},
        {}, {}, {}, {}, {},
    ])

    assert coordinator.data["fahrten"] == vorher["fahrten"]
    assert coordinator.data["totals"] == vorher["totals"]
