"""Regressionsnetz fuer den neuen Options-Flow-Zweig home_charging_method
(evcc vs. generisch, Nutzerwunsch 2026-09-27: "falls man mal von evcc weg
will") -- analog test_mode_switch.py fuer LADE_MODUS_NUR_AUSWAERTS. Wechseln
zwischen den beiden Pfaden darf die jeweils andere Feldgruppe nicht aus
entry.data entfernen (siehe config_flow.py::_carry_forward()/
_all_step_schema_keys())."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _make_entry(hass):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_HOST,
        CONF_EVCC_VEHICLE_NAME,
        CONF_HOME_CHARGING_METHOD,
        CONF_HOME_ENTITY,
        CONF_LADE_MODUS,
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        CONF_WALLBOX_ENERGY_ENTITY,
        DOMAIN,
        HOME_CHARGING_METHOD_EVCC,
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
            CONF_HOME_CHARGING_METHOD: HOME_CHARGING_METHOD_EVCC,
            CONF_EVCC_HOST: "http://evcc.local:7070",
            CONF_EVCC_VEHICLE_NAME: "mein_auto",
            CONF_HOME_ENTITY: "binary_sensor.wallbox_laedt",
            CONF_WALLBOX_ENERGY_ENTITY: "sensor.wallbox_energie",
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


async def test_wechsel_zu_generisch_erhaelt_evcc_werte(hass):
    """Wechsel evcc -> generisch darf die bereits konfigurierten evcc-Werte
    NICHT aus entry.data entfernen, obwohl der "evcc"-Schritt diesmal
    uebersprungen wird (stattdessen "heimladen")."""
    from custom_components.ev_assistant.config_flow import EvAssistantOptionsFlow
    from custom_components.ev_assistant.const import (
        CONF_EVCC_HOST,
        CONF_EVCC_VEHICLE_NAME,
        CONF_HOME_CHARGING_METHOD,
        CONF_LADE_MODUS,
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        HOME_CHARGING_METHOD_GENERISCH,
        LADE_MODUS_GEMISCHT,
    )

    entry = _make_entry(hass)
    flow = EvAssistantOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_init()
    result = await flow.async_step_fahrzeug({
        CONF_VEHICLE_HERSTELLER: "Testmarke", CONF_VEHICLE_MODELL: "Testmodell",
        CONF_SOC_ENTITY: "sensor.test_soc", CONF_USABLE_KWH: 50.0,
    })
    assert result["step_id"] == "modus"
    result = await flow.async_step_modus({
        CONF_LADE_MODUS: LADE_MODUS_GEMISCHT, CONF_HOME_CHARGING_METHOD: HOME_CHARGING_METHOD_GENERISCH,
    })
    assert result["step_id"] == "heimladen"

    # Restliche Schritte einfach leer durchreichen, bis zum Abschluss.
    while result["type"] != "create_entry":
        handler = getattr(flow, f"async_step_{result['step_id']}")
        result = await handler({})

    assert entry.data[CONF_EVCC_HOST] == "http://evcc.local:7070"
    assert entry.data[CONF_EVCC_VEHICLE_NAME] == "mein_auto"
    assert entry.data[CONF_HOME_CHARGING_METHOD] == HOME_CHARGING_METHOD_GENERISCH


async def test_wechsel_zu_evcc_erhaelt_heimladen_werte(hass):
    """Umgekehrter Fall: generisch -> evcc darf die "heimladen"-exklusiven
    Felder (z.B. wallbox_energy_entity) nicht entfernen, obwohl dieser
    Schritt diesmal uebersprungen wird. home_entity ist bewusst NICHT
    Teil dieser Pruefung -- das ist jetzt Teil des immer sichtbaren
    Schritts "ladeleistung", nicht heimladen-exklusiv (siehe
    build_power_schema())."""
    from custom_components.ev_assistant.config_flow import EvAssistantOptionsFlow
    from custom_components.ev_assistant.const import (
        CONF_HOME_CHARGING_METHOD,
        CONF_LADE_MODUS,
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        CONF_WALLBOX_ENERGY_ENTITY,
        HOME_CHARGING_METHOD_EVCC,
        LADE_MODUS_GEMISCHT,
    )

    entry = _make_entry(hass)
    flow = EvAssistantOptionsFlow(entry)
    flow.hass = hass

    await flow.async_step_init()
    await flow.async_step_fahrzeug({
        CONF_VEHICLE_HERSTELLER: "Testmarke", CONF_VEHICLE_MODELL: "Testmodell",
        CONF_SOC_ENTITY: "sensor.test_soc", CONF_USABLE_KWH: 50.0,
    })
    result = await flow.async_step_modus({
        CONF_LADE_MODUS: LADE_MODUS_GEMISCHT, CONF_HOME_CHARGING_METHOD: HOME_CHARGING_METHOD_EVCC,
    })
    # "heimladen" wird diesmal komplett uebersprungen (siehe async_step_modus()) --
    # genau das ist der Fall, den _carry_forward() dort absichern soll.
    assert result["step_id"] == "evcc"

    while result["type"] != "create_entry":
        handler = getattr(flow, f"async_step_{result['step_id']}")
        result = await handler({})

    assert entry.data[CONF_WALLBOX_ENERGY_ENTITY] == "sensor.wallbox_energie"
    assert entry.data[CONF_HOME_CHARGING_METHOD] == HOME_CHARGING_METHOD_EVCC


async def test_zurueckwechseln_zu_generisch_zeigt_erhaltene_werte_vorbefuellt(hass):
    """Wechsel zu "generisch" muss die generischen Heimladen-Werte im
    "heimladen"-Formular vorbefuellt zeigen, obwohl diese Session sie nie
    selbst gesetzt hat (kommen unveraendert aus entry.data, siehe
    _make_entry())."""
    from custom_components.ev_assistant.config_flow import EvAssistantOptionsFlow
    from custom_components.ev_assistant.const import (
        CONF_HOME_CHARGING_METHOD,
        CONF_LADE_MODUS,
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        CONF_WALLBOX_ENERGY_ENTITY,
        HOME_CHARGING_METHOD_GENERISCH,
        LADE_MODUS_GEMISCHT,
    )

    entry = _make_entry(hass)

    # Neuer Flow-Durchlauf, wechselt direkt zu "generisch" -- entry.data
    # traegt die evcc-Werte bereits aus _make_entry(), OHNE dass diese Session
    # sie je selbst gesetzt hat (simuliert einen bereits umgestellten Zustand).
    flow = EvAssistantOptionsFlow(entry)
    flow.hass = hass
    await flow.async_step_init()
    await flow.async_step_fahrzeug({
        CONF_VEHICLE_HERSTELLER: "Testmarke", CONF_VEHICLE_MODELL: "Testmodell",
        CONF_SOC_ENTITY: "sensor.test_soc", CONF_USABLE_KWH: 50.0,
    })
    result = await flow.async_step_modus({
        CONF_LADE_MODUS: LADE_MODUS_GEMISCHT, CONF_HOME_CHARGING_METHOD: HOME_CHARGING_METHOD_GENERISCH,
    })
    assert result["step_id"] == "heimladen"
    heimladen_defaults = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if getattr(key, "description", None)
    }
    assert heimladen_defaults[CONF_WALLBOX_ENERGY_ENTITY] == "sensor.wallbox_energie"


async def test_heimladen_schema_enthaelt_wallbox_status_felder():
    """Regressionsnetz fuer den Nutzerwunsch 2026-09-28: "im schritt
    wallbox, sensoren auswaehlbar machen die den status zeigen" --
    wallbox_connected_entity/wallbox_charging_entity muessen im "heimladen"-
    Schema auswaehlbar sein (siehe coordinator.py::home_generic_live_attrs()
    fuer ihre Verwendung)."""
    from custom_components.ev_assistant.config_flow import build_heimladen_schema
    from custom_components.ev_assistant.const import CONF_WALLBOX_CHARGING_ENTITY, CONF_WALLBOX_CONNECTED_ENTITY

    keys = {str(key) for key in build_heimladen_schema({}).schema}
    assert CONF_WALLBOX_CONNECTED_ENTITY in keys
    assert CONF_WALLBOX_CHARGING_ENTITY in keys


async def test_geteiltes_feld_laesst_sich_im_evcc_pfad_leeren(hass):
    """Review 2026-10-04: home_consumption_entity steht im evcc- UND im
    Heimladen-Schema. Der Modus-Schritt kopiert den Wert des uebersprungenen
    Pfads vorab nach _data -- Leeren im aktiven Schritt muss ihn trotzdem
    entfernen."""
    from custom_components.ev_assistant.config_flow import EvAssistantOptionsFlow
    from custom_components.ev_assistant.const import (
        CONF_HOME_CHARGING_METHOD,
        CONF_HOME_CONSUMPTION_ENTITY,
        CONF_LADE_MODUS,
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        HOME_CHARGING_METHOD_EVCC,
        LADE_MODUS_GEMISCHT,
    )

    entry = _make_entry(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_HOME_CONSUMPTION_ENTITY: "sensor.hausverbrauch"},
    )
    flow = EvAssistantOptionsFlow(entry)
    flow.hass = hass
    await flow.async_step_init()
    await flow.async_step_fahrzeug({
        CONF_VEHICLE_HERSTELLER: "Testmarke", CONF_VEHICLE_MODELL: "Testmodell",
        CONF_SOC_ENTITY: "sensor.test_soc", CONF_USABLE_KWH: 50.0,
    })
    result = await flow.async_step_modus({
        CONF_LADE_MODUS: LADE_MODUS_GEMISCHT, CONF_HOME_CHARGING_METHOD: HOME_CHARGING_METHOD_EVCC,
    })
    assert result["step_id"] == "evcc"
    assert flow._data.get(CONF_HOME_CONSUMPTION_ENTITY) == "sensor.hausverbrauch"  # vorab kopiert
    # evcc-Schritt ohne das Feld (Nutzer hat es geleert), ohne Host -> kein Netzwerk
    await flow.async_step_evcc({})
    assert CONF_HOME_CONSUMPTION_ENTITY not in flow._data
