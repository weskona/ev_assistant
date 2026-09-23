"""Tests fuer das anpassbare Beta-Panel-Layout (Nutzerwunsch 2026-09-23:
"der nutzer bekommt eine auswahl von karten, die er selber im panel
anordnen oder auch auswaehlen kann" / "vlt auch die groesse aendern kann")
-- coordinator.py::panel_layout()/async_set_panel_layout(). Reines
Persistieren einer Praesentationseinstellung, keine Berechnungslogik."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="pl1", options=None):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


async def test_panel_layout_leer_ohne_gespeicherte_einstellung(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    assert coordinator.panel_layout() == []


async def test_async_set_panel_layout_speichert_reihenfolge_sichtbarkeit_groesse(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    layout = [
        {"key": "kpi", "visible": True, "size": "half"},
        {"key": "hero_cost", "visible": False, "size": "twothirds"},
        {"key": "wallbox", "visible": True, "size": "third"},
    ]
    await coordinator.async_set_panel_layout(layout)
    assert coordinator.panel_layout() == layout


async def test_async_set_panel_layout_verwirft_unbekannte_schluessel(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    await coordinator.async_set_panel_layout([
        {"key": "kpi", "visible": True, "size": "full"},
        {"key": "irgendwas_altes", "visible": True, "size": "full"},
    ])
    assert coordinator.panel_layout() == [{"key": "kpi", "visible": True, "size": "full"}]


async def test_async_set_panel_layout_visible_default_true_ohne_feld(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    await coordinator.async_set_panel_layout([{"key": "kpi"}])
    assert coordinator.panel_layout() == [{"key": "kpi", "visible": True, "size": "full"}]


async def test_async_set_panel_layout_size_faellt_bei_unbekanntem_wert_auf_full_zurueck(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    await coordinator.async_set_panel_layout([{"key": "kpi", "visible": True, "size": "riesig"}])
    assert coordinator.panel_layout() == [{"key": "kpi", "visible": True, "size": "full"}]


async def test_async_set_panel_layout_ueberschreibt_vorherige_einstellung(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators)
    await coordinator.async_set_panel_layout([{"key": "kpi", "visible": True, "size": "full"}])
    await coordinator.async_set_panel_layout([{"key": "hero_cost", "visible": False, "size": "half"}])
    assert coordinator.panel_layout() == [{"key": "hero_cost", "visible": False, "size": "half"}]
