"""Option home_includes_wallbox: Der Hausverbrauchszaehler misst den
Gesamtverbrauch INKLUSIVE Wallbox, die Wallbox-Energie wird abgezogen
(Hausprofil-Zaehlerstand und Live-Tick der Heimladung). Standard aus."""
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


async def test_zaehlerstand_ohne_option_unveraendert(hass, coordinators):
    c, _ = await _make_coordinator(hass, coordinators, options=_generic_options())
    hass.states.async_set("sensor.home_cons", "100.0")
    c._set_wallbox_energy(30.0)
    assert c._house_combined_reading_kwh() == 100.0


async def test_zaehlerstand_zieht_wallbox_ab(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_INCLUDES_WALLBOX

    c, _ = await _make_coordinator(
        hass, coordinators, options=_generic_options(**{CONF_HOME_INCLUDES_WALLBOX: True})
    )
    hass.states.async_set("sensor.home_cons", "100.0")
    c._set_wallbox_energy(30.0)
    assert c._house_combined_reading_kwh() == 70.0


async def test_zaehlerstand_ohne_wallbox_stand_bucht_nichts(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_INCLUDES_WALLBOX

    c, _ = await _make_coordinator(
        hass, coordinators, options=_generic_options(**{CONF_HOME_INCLUDES_WALLBOX: True})
    )
    hass.states.async_set("sensor.home_cons", "100.0")
    c._wallbox_energy = None
    assert c._house_combined_reading_kwh() is None


async def test_live_tick_zieht_wallbox_vom_haus_ab(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_INCLUDES_WALLBOX

    c, _ = await _make_coordinator(
        hass, coordinators, options=_generic_options(**{CONF_HOME_INCLUDES_WALLBOX: True})
    )
    c._soc = 50.0
    c._pv_generation = 100.0
    c._home_consumption_live_raw = 50.0
    c._set_wallbox_energy(10.0)
    c._set_home("on")
    # 3 kWh PV, Gesamtzaehler +3 (davon 2 kWh Auto) -> Haus 1 kWh, 2 kWh
    # Ueberschuss, Auto 2 kWh -> komplett Solar. Ohne Abzug waere Haus 3 kWh
    # und der Solaranteil 0.
    c._pv_generation = 103.0
    c._home_consumption_live_raw = 53.0
    c._wallbox_energy = 12.0
    c._process_home_tick()
    c._set_home("off")
    await hass.async_block_till_done()
    rec = c.data["home_sessions"][0]
    assert rec["kwh"] == 2.0
    assert rec["solar_pct"] == 100.0
