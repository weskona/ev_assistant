"""Tests fuer ausblendbare Panel-Tabs (Nutzerwunsch, Issue #2/Jochen754-
Folgefeedback 2026-09-27: "Leasing", "Ladekarten", "Wartung" ausblendbar
machen) -- coordinator.py::hidden_tabs()/async_set_hidden_tabs(). Reines
Persistieren einer Praesentationseinstellung, keine Berechnungslogik
(analog test_panel_layout.py)."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="ht1", options=None):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


async def test_hidden_tabs_leer_ohne_gespeicherte_einstellung(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    assert coordinator.hidden_tabs() == []


async def test_async_set_hidden_tabs_speichert_liste(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    await coordinator.async_set_hidden_tabs(["leasing", "wartung"])
    assert coordinator.hidden_tabs() == ["leasing", "wartung"]


async def test_async_set_hidden_tabs_verwirft_unbekannte_tab_ids(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    await coordinator.async_set_hidden_tabs(["ladekarten", "fahrzeuge", "irgendwas_altes"])
    # "fahrzeuge" ist kein ausblendbarer Tab (siehe const.py::HIDEABLE_TAB_IDS)
    # und wird deshalb verworfen, genau wie der unbekannte Wert.
    assert coordinator.hidden_tabs() == ["ladekarten"]


async def test_async_set_hidden_tabs_ueberschreibt_vorherige_einstellung(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    await coordinator.async_set_hidden_tabs(["leasing"])
    await coordinator.async_set_hidden_tabs(["wartung", "ladekarten"])
    assert coordinator.hidden_tabs() == ["wartung", "ladekarten"]


async def test_async_set_hidden_tabs_leere_liste_blendet_alles_wieder_ein(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    await coordinator.async_set_hidden_tabs(["leasing", "wartung", "ladekarten"])
    await coordinator.async_set_hidden_tabs([])
    assert coordinator.hidden_tabs() == []
