"""Tests fuer die tick-basierte Solaranteil-/Kosten-Schaetzung von Heim-
Ladesessions OHNE evcc (Nutzeranforderung 2026-09-27: "gleiche Kosten
ermitteln koennen, genauso richtig wie evcc es macht. Sonst macht das
keinen Sinn") -- coordinator.py::_process_home_tick()/_set_home()/
_home_generic_estimate_eligible(). Reine Berechnungslogik (engine.py::
home_charging_tick_split()) ist bereits in tests/test_engine.py abgedeckt --
hier nur die HA-Verdrahtung (Session-Lifecycle, Eligibility-Gating,
Restart-Sicherheit)."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="hce1", options=None, pre_seed_store=None):
    """`pre_seed_store`: wird VOR async_setup() in den Store geschrieben --
    simuliert einen bereits vorhandenen persistierten Coordinator-Zustand
    aus einer frueheren Laufzeit (z.B. fuer den Restart-Sicherheits-Test),
    NICHT zu verwechseln mit entry.data/entry.options (Konfiguration)."""
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    if pre_seed_store:
        await coordinator._store.async_save(pre_seed_store)
    await coordinator.async_setup()
    return coordinator, entry


def _generic_options(hass=None, **overrides):
    from custom_components.ev_assistant.const import (
        CONF_HOME_CONSUMPTION_ENTITY,
        CONF_HOME_ENTITY,
        CONF_HOME_FEEDIN_PRICE_KWH,
        CONF_HOME_PRICE_KWH,
        CONF_PV_GENERATION_ENTITY,
        CONF_WALLBOX_ENERGY_ENTITY,
    )

    opts = {
        CONF_HOME_ENTITY: "sensor.home_power",
        CONF_PV_GENERATION_ENTITY: "sensor.pv_gen",
        CONF_HOME_CONSUMPTION_ENTITY: "sensor.home_cons",
        CONF_WALLBOX_ENERGY_ENTITY: "sensor.wallbox_energy",
        CONF_HOME_FEEDIN_PRICE_KWH: 0.08,
        CONF_HOME_PRICE_KWH: 0.30,
    }
    opts.update(overrides)
    return opts


async def test_home_generic_estimate_volle_session(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, options=_generic_options())
    coordinator._soc = 50.0
    coordinator._pv_generation = 100.0
    coordinator._home_consumption_live_raw = 50.0
    coordinator._set_wallbox_energy(10.0)

    coordinator._set_home("on")
    assert coordinator._home_tick_acc is not None
    assert coordinator.data["home_generic_estimate_open"] is True

    # Tick 1: 3 kWh PV, 1 kWh Haus -> 2 kWh Ueberschuss, 2 kWh Auto -> komplett Solar.
    coordinator._pv_generation = 103.0
    coordinator._home_consumption_live_raw = 51.0
    coordinator._wallbox_energy = 12.0
    coordinator._process_home_tick()

    # Tick 2: 1 kWh PV, 1 kWh Haus -> kein Ueberschuss, 3 kWh Auto -> komplett Netz.
    coordinator._pv_generation = 104.0
    coordinator._home_consumption_live_raw = 52.0
    coordinator._wallbox_energy = 15.0
    coordinator._process_home_tick()

    coordinator._set_home("off")
    await hass.async_block_till_done()

    assert coordinator._home_tick_acc is None
    assert coordinator.data["home_generic_estimate_open"] is False
    sessions = coordinator.data["home_sessions"]
    assert len(sessions) == 1
    rec = sessions[0]
    assert rec["kwh"] == 5.0
    assert rec["solar_pct"] == 40.0
    # Tick 1: 2 kWh x 0.08 (reine Solar-Session-Kosten) = 0.16
    # Tick 2: 3 kWh x 0.30 (reiner Netzpreis) = 0.90
    assert rec["kosten"] == 1.06


async def test_home_generic_estimate_speicherladung_zaehlt_additiv_zum_hausverbrauch(hass, coordinators):
    """battery_charge_entity (falls konfiguriert) konkurriert genauso um
    den PV-Ueberschuss wie das Auto -- analog _house_combined_reading_kwh().
    Nutzerkorrektur 2026-09-27: darf NICHT exklusiv nur in "heimladen"
    liegen bzw. bei der Schaetzung selbst fehlen."""
    from custom_components.ev_assistant.const import CONF_BATTERY_CHARGE_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, options=_generic_options(**{CONF_BATTERY_CHARGE_ENTITY: "sensor.battery_charge"}),
    )
    coordinator._soc = 50.0
    coordinator._pv_generation = 100.0
    coordinator._home_consumption_live_raw = 50.0
    coordinator._battery_charge_live_raw = 20.0
    coordinator._set_wallbox_energy(10.0)

    coordinator._set_home("on")
    assert coordinator._home_tick_acc is not None

    # 3 kWh PV, 1 kWh Haus + 1 kWh Speicherladung -> nur 1 kWh Ueberschuss,
    # Auto braucht 2 kWh -> 1 kWh Solar + 1 kWh Netz (OHNE Speicher-
    # Beruecksichtigung waere es faelschlich 2 kWh komplett Solar gewesen).
    coordinator._pv_generation = 103.0
    coordinator._home_consumption_live_raw = 51.0
    coordinator._battery_charge_live_raw = 21.0
    coordinator._wallbox_energy = 12.0
    coordinator._process_home_tick()

    coordinator._set_home("off")
    await hass.async_block_till_done()

    rec = coordinator.data["home_sessions"][0]
    assert rec["kwh"] == 2.0
    assert rec["solar_pct"] == 50.0


async def test_home_generic_estimate_ohne_ueberschuss_reiner_netzbezug(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, options=_generic_options())
    coordinator._soc = 50.0
    coordinator._pv_generation = 0.0
    coordinator._home_consumption_live_raw = 0.0
    coordinator._set_wallbox_energy(0.0)

    coordinator._set_home("on")
    coordinator._pv_generation = 0.5
    coordinator._home_consumption_live_raw = 2.0
    coordinator._wallbox_energy = 4.0
    coordinator._process_home_tick()
    coordinator._set_home("off")
    await hass.async_block_till_done()

    rec = coordinator.data["home_sessions"][0]
    assert rec["kwh"] == 4.0
    assert rec["solar_pct"] == 0.0
    assert rec["kosten"] == round(4.0 * 0.30, 2)


async def test_home_generic_estimate_fehlender_sensor_kein_akkumulator(hass, coordinators):
    """Fehlt auch nur einer der noetigen Sensoren (hier: PV-Erzeugung), gibt
    es KEINEN Akkumulator und damit auch keine Session-Aufzeichnung --
    keine grobe Naeherung, siehe _home_generic_estimate_eligible()."""
    from custom_components.ev_assistant.const import CONF_PV_GENERATION_ENTITY

    opts = _generic_options()
    del opts[CONF_PV_GENERATION_ENTITY]
    coordinator, _ = await _make_coordinator(hass, coordinators, options=opts)
    coordinator._soc = 50.0
    coordinator._set_wallbox_energy(10.0)

    coordinator._set_home("on")
    assert coordinator._home_tick_acc is None

    coordinator._wallbox_energy = 15.0
    coordinator._set_home("off")
    await hass.async_block_till_done()

    assert coordinator.data["home_sessions"] == []


async def test_home_generic_estimate_fehlender_preis_kein_akkumulator(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_FEEDIN_PRICE_KWH

    opts = _generic_options()
    del opts[CONF_HOME_FEEDIN_PRICE_KWH]
    coordinator, _ = await _make_coordinator(hass, coordinators, options=opts)
    coordinator._soc = 50.0
    coordinator._set_wallbox_energy(10.0)

    coordinator._set_home("on")
    assert coordinator._home_tick_acc is None


async def test_home_generic_estimate_inaktiv_mit_evcc_host(hass, coordinators):
    """evcc_host konfiguriert -> generische Schaetzung bleibt komplett aus,
    auch wenn alle generischen Sensoren zusaetzlich vorhanden sind (evccs
    eigenes Session-Log liefert dieselben Werte bereits praeziser, siehe
    _home_generic_estimate_eligible()). evcc_host wird bewusst ERST NACH
    async_setup() gesetzt (direkt am Coordinator geprueft per _opt(), kein
    erneuter _setup_evcc_client()-Aufruf noetig) -- ein echter evcc_host
    ab Konstruktionszeit wuerde _setup_evcc_client() einen echten (in
    Tests nicht aufloesbaren) Netzwerk-Request ausloesen."""
    from custom_components.ev_assistant.const import CONF_EVCC_HOST

    coordinator, entry = await _make_coordinator(hass, coordinators, options=_generic_options())
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_EVCC_HOST: "http://evcc.local:7070"},
    )
    coordinator._soc = 50.0
    coordinator._set_wallbox_energy(10.0)

    coordinator._set_home("on")
    assert coordinator._home_tick_acc is None


async def test_home_generic_estimate_restart_waehrend_offener_session_unterdrueckt(hass, coordinators):
    """Kernanforderung: ein Neustart waehrend einer offenen generischen
    Session darf KEIN falsches/unvollstaendiges Solar-/Kosten-Ergebnis fuer
    diese Session liefern -- der Marker home_generic_estimate_open=True
    (vom "letzten Mal" persistiert) muss den Akkumulator fuer die gerade
    fortgesetzte Session unterdruecken, siehe async_setup()/_set_home()."""
    coordinator, entry = await _make_coordinator(
        hass, coordinators, entry_id="hce_restart",
        options=_generic_options(),
        pre_seed_store={"home_generic_estimate_open": True},
    )
    coordinator._soc = 50.0
    coordinator._set_wallbox_energy(10.0)

    # Simuliert den initialen _wire()-Aufruf beim Hochfahren, waehrend das
    # Auto schon (von vor dem Neustart) laedt.
    coordinator._set_home("on")
    assert coordinator._home_tick_acc is None

    coordinator._pv_generation = 100.0
    coordinator._home_consumption_live_raw = 50.0
    coordinator._wallbox_energy = 20.0
    coordinator._set_home("off")
    await hass.async_block_till_done()

    assert coordinator.data["home_sessions"] == []
    assert coordinator.data["home_generic_estimate_open"] is False


async def test_home_generic_estimate_echte_neue_session_nach_restart_funktioniert_wieder(hass, coordinators):
    """Nach der unterdrueckten (fortgesetzten) Session muss eine WIRKLICH
    neue Session in derselben Laufzeit wieder ganz normal geschaetzt
    werden -- die Unterdrueckung ist einmalig, kein Dauerzustand."""
    coordinator, _ = await _make_coordinator(
        hass, coordinators, entry_id="hce_restart2",
        options=_generic_options(),
        pre_seed_store={"home_generic_estimate_open": True},
    )
    coordinator._soc = 50.0
    coordinator._set_wallbox_energy(10.0)
    coordinator._pv_generation = 100.0
    coordinator._home_consumption_live_raw = 50.0

    # Fortgesetzte (unterdrueckte) Session.
    coordinator._set_home("on")
    coordinator._set_home("off")
    await hass.async_block_till_done()
    assert coordinator.data["home_sessions"] == []

    # Echte neue Session.
    coordinator._set_home("on")
    assert coordinator._home_tick_acc is not None
    coordinator._pv_generation = 103.0
    coordinator._home_consumption_live_raw = 51.0
    coordinator._wallbox_energy = 12.0
    coordinator._process_home_tick()
    coordinator._set_home("off")
    await hass.async_block_till_done()

    assert len(coordinator.data["home_sessions"]) == 1
