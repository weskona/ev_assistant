"""Tests fuer coordinator.py::home_generic_live_attrs() -- das Pendant zu
evcc_live_attrs() fuer den generischen (nicht-evcc) Heimladen-Pfad, das die
Wallbox-Karte im Uebersicht-Beta-Tab braucht (Nutzerbericht 2026-09-28:
"die wallboxkarte wird bei nur zuhause laden nicht angezeigt" -- die Karte
war zuvor ausschliesslich an evcc_live_attrs()/"connected" gebunden, das
ohne evcc nie befuellt wird).

Alle custom_components-Importe bewusst LOKAL in den Testfunktionen (nicht
auf Modulebene) -- ein modulweiter Import scheitert unter dem reinen
"pytest"-CLI-Einstiegspunkt (wie in CI verwendet, siehe .github/workflows/
validate.yml) mit "ModuleNotFoundError: No module named 'custom_components'",
da dort (anders als bei einem lokalen "python -m pytest"-Aufruf) das
Arbeitsverzeichnis nicht automatisch auf sys.path landet -- erst
pytest-homeassistant-custom-component's Fixtures richten das zur Testlaufzeit
ein. Regression 2026-09-28: v0.99.11-Release brach genau daran (CI-Fehler
"fehler" gemeldet), siehe auch alle anderen Testdateien in tests/ha/, die
demselben Muster folgen."""


async def _make_coordinator(hass, coordinators, entry_id, options=None):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator


async def test_ohne_home_entity_gibt_leeres_dict(hass, coordinators):
    """Kein Heimlade-Signal konfiguriert -- nichts, an dem sich ein
    Live-Status festmachen liesse."""
    coordinator = await _make_coordinator(hass, coordinators, "gen1", {})
    assert coordinator.home_generic_live_attrs() == {}


async def test_mit_evcc_host_gibt_leeres_dict(hass, coordinators):
    """evcc_live_attrs() deckt diesen Fall bereits ab -- die beiden
    Datenquellen schliessen sich gegenseitig aus, niemals beide befuellt.
    evcc_host wird ERST NACH async_setup() gesetzt (nicht schon in den
    Ausgangs-Optionen), damit _setup_evcc_client() waehrend des Setups
    keinen echten Netzwerkverbindungsversuch unternimmt (siehe
    test_home_charging_estimate.py fuer denselben Kniff)."""
    from custom_components.ev_assistant.const import CONF_EVCC_HOST, CONF_HOME_ENTITY

    coordinator = await _make_coordinator(
        hass, coordinators, "gen2", {CONF_HOME_ENTITY: "sensor.wallbox_leistung"},
    )
    hass.config_entries.async_update_entry(
        coordinator.entry,
        options={**coordinator.entry.options, CONF_EVCC_HOST: "http://evcc.local:7070"},
    )
    assert coordinator.home_generic_live_attrs() == {}


async def test_laedt_gerade_ohne_plug_entity_connected_faellt_auf_charging_zurueck(hass, coordinators):
    import time

    from custom_components.ev_assistant.const import CONF_HOME_ENTITY

    coordinator = await _make_coordinator(
        hass, coordinators, "gen3", {CONF_HOME_ENTITY: "sensor.wallbox_leistung"},
    )
    coordinator._home = True
    # _power (power_entity, FAHRZEUG-seitig) nur als Fallback getestet --
    # _home_power_raw bleibt hier bewusst None (kein _set_home()-Aufruf),
    # siehe test_home_entity_liefert_ladeleistung_ohne_power_entity() fuer
    # den eigentlichen (bevorzugten) Pfad ueber home_entity selbst.
    coordinator._power = 7.4
    now = time.time()
    coordinator._home_session_start_ts = now - 120.0

    attrs = coordinator.home_generic_live_attrs()
    assert attrs["charging"] is True
    assert attrs["connected"] is True
    assert attrs["charge_power"] == 7.4
    assert attrs["charge_duration"] is not None
    assert 110 <= attrs["charge_duration"] <= 130


async def test_home_entity_liefert_ladeleistung_ohne_power_entity(hass, coordinators):
    """Regression (Bugbericht 2026-09-28: "zeigt keine ladeleistung"):
    charge_power muss aus home_entity selbst kommen (der eigentlichen
    Wallbox-Leistungsmessung, siehe _set_home()), nicht ausschliesslich aus
    power_entity -- das ist die FAHRZEUG-seitige Ladeleistung fuer
    Fremdladungs-Schaetzungen (siehe const.py), bei einem reinen
    Heimlade-Setup typischerweise gar nicht konfiguriert."""
    from custom_components.ev_assistant.const import CONF_HOME_ENTITY

    hass.states.async_set("sensor.wallbox_leistung", "7.4")
    coordinator = await _make_coordinator(
        hass, coordinators, "gen9", {CONF_HOME_ENTITY: "sensor.wallbox_leistung"},
    )

    attrs = coordinator.home_generic_live_attrs()
    assert attrs["charging"] is True
    assert attrs["charge_power"] == 7.4


async def test_nicht_ladend_ohne_plug_entity_connected_ist_false(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_ENTITY

    coordinator = await _make_coordinator(
        hass, coordinators, "gen4", {CONF_HOME_ENTITY: "sensor.wallbox_leistung"},
    )
    coordinator._home = False
    coordinator._power = None
    coordinator._home_session_start_ts = None

    attrs = coordinator.home_generic_live_attrs()
    assert attrs["charging"] is False
    assert attrs["connected"] is False
    assert attrs["charge_power"] is None
    assert attrs["charge_duration"] is None


async def test_mit_plug_entity_connected_kann_von_charging_abweichen(hass, coordinators):
    """Angesteckt (plug_entity bestaetigt True), aber gerade keine
    Ladeleistung -- der "verbunden"-Zustand der Panel-Karte, nicht
    "nicht verbunden"."""
    from custom_components.ev_assistant.const import CONF_HOME_ENTITY

    coordinator = await _make_coordinator(
        hass, coordinators, "gen5", {CONF_HOME_ENTITY: "sensor.wallbox_leistung"},
    )
    coordinator._home = False
    coordinator._plugged_in = True

    attrs = coordinator.home_generic_live_attrs()
    assert attrs["charging"] is False
    assert attrs["connected"] is True


async def test_wallbox_connected_entity_override_hat_vorrang(hass, coordinators):
    """Konfigurierter eigener Statussensor ersetzt die abgeleitete
    Heuristik (Nutzerwunsch 2026-09-28: "im schritt wallbox, sensoren
    auswaehlbar machen die den status zeigen")."""
    from custom_components.ev_assistant.const import CONF_HOME_ENTITY, CONF_WALLBOX_CONNECTED_ENTITY

    hass.states.async_set("binary_sensor.wallbox_verbunden", "on")
    coordinator = await _make_coordinator(
        hass, coordinators, "gen6",
        {
            CONF_HOME_ENTITY: "sensor.wallbox_leistung",
            CONF_WALLBOX_CONNECTED_ENTITY: "binary_sensor.wallbox_verbunden",
        },
    )
    coordinator._home = False  # abgeleitete Heuristik waere "nicht verbunden"
    attrs = coordinator.home_generic_live_attrs()
    assert attrs["connected"] is True

    hass.states.async_set("binary_sensor.wallbox_verbunden", "off")
    await hass.async_block_till_done()
    attrs = coordinator.home_generic_live_attrs()
    assert attrs["connected"] is False


async def test_wallbox_charging_entity_override_hat_vorrang(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_ENTITY, CONF_WALLBOX_CHARGING_ENTITY

    hass.states.async_set("binary_sensor.wallbox_laedt", "off")
    coordinator = await _make_coordinator(
        hass, coordinators, "gen7",
        {
            CONF_HOME_ENTITY: "sensor.wallbox_leistung",
            CONF_WALLBOX_CHARGING_ENTITY: "binary_sensor.wallbox_laedt",
        },
    )
    coordinator._home = True  # abgeleitete Heuristik waere "laedt"
    attrs = coordinator.home_generic_live_attrs()
    assert attrs["charging"] is False

    hass.states.async_set("binary_sensor.wallbox_laedt", "on")
    await hass.async_block_till_done()
    attrs = coordinator.home_generic_live_attrs()
    assert attrs["charging"] is True


async def test_wallbox_status_entity_unavailable_faellt_auf_heuristik_zurueck(hass, coordinators):
    """unavailable/unknown zaehlt nicht als Override -- sonst wuerde ein
    kurzzeitig ausgefallener Statussensor die Karte faelschlich auf
    "nicht verbunden" stellen, obwohl home_entity weiterhin ladet."""
    from custom_components.ev_assistant.const import CONF_HOME_ENTITY, CONF_WALLBOX_CONNECTED_ENTITY

    hass.states.async_set("binary_sensor.wallbox_verbunden", "unavailable")
    coordinator = await _make_coordinator(
        hass, coordinators, "gen8",
        {
            CONF_HOME_ENTITY: "sensor.wallbox_leistung",
            CONF_WALLBOX_CONNECTED_ENTITY: "binary_sensor.wallbox_verbunden",
        },
    )
    coordinator._home = True

    attrs = coordinator.home_generic_live_attrs()
    assert attrs["connected"] is True
