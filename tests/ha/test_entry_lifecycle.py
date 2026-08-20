"""Regressionsnetz fuer den Config-Entry-Lifecycle (__init__.py::
async_setup_entry()/async_unload_entry()): Setup legt Coordinator+Entities
an, Unload raeumt sauber ab (kein KeyError, hass.data[DOMAIN] bereinigt) und
flusht einen ausstehenden _save_soon()-Stand (siehe coordinator.py::
async_shutdown(), Kommentar dort: "ohne diesen expliziten Flush wuerde der
letzte unkritische Zwischenstand ... bei einem Reload verloren gehen")."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _make_entry(hass):
    from custom_components.ev_assistant.const import (
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VEHICLE_HERSTELLER: "Testmarke",
            CONF_VEHICLE_MODELL: "Testmodell",
            CONF_SOC_ENTITY: "sensor.test_soc",
            CONF_USABLE_KWH: 50.0,
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_entry_legt_coordinator_und_entities_an(hass):
    from custom_components.ev_assistant.const import DOMAIN

    entry = _make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.entry_id in hass.data[DOMAIN]
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data["lifetime_baselines_migrated"] is True

    # Mindestens ein ev_assistant-Sensor muss angelegt worden sein.
    states = hass.states.async_entity_ids("sensor")
    assert any(hass.states.get(eid) is not None for eid in states)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_unload_entry_raeumt_hass_data_sauber_ab(hass):
    from custom_components.ev_assistant.const import DOMAIN

    entry = _make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # .pop(entry_id, None) statt hartem Zugriff -- kein KeyError.
    assert entry.entry_id not in hass.data[DOMAIN]

    # Ein zweiter Unload-Versuch (z.B. durch einen doppelten Aufruf) darf
    # ebenfalls nicht mit einer Exception scheitern.
    coordinator_module_ok = True
    try:
        from custom_components.ev_assistant import async_unload_entry
        await async_unload_entry(hass, entry)
    except KeyError:
        coordinator_module_ok = False
    assert coordinator_module_ok


async def test_unload_flusht_ausstehenden_save_soon_stand(hass, hass_storage):
    from custom_components.ev_assistant.const import DOMAIN, STORAGE_KEY

    entry = _make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Ein ueber _save_soon() gebuendelter (noch nicht geschriebener)
    # Zwischenstand -- z.B. ein SoC-Mirrorwert -- darf beim Unload nicht
    # verloren gehen.
    coordinator.data["_test_marker"] = "ausstehende_aenderung"
    coordinator._save_soon()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    storage_key = f"{STORAGE_KEY}_{entry.entry_id}"
    assert hass_storage[storage_key]["data"].get("_test_marker") == "ausstehende_aenderung"
