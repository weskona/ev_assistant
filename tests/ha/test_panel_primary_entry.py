"""Top-Level-Kontext der Panel-Konfiguration (__init__.py::_primary_entry()):
immer der ERSTE geladene Eintrag, nicht der zuletzt registrierende. Vorfall
2026-10-10: bei mehreren Eintraegen entschied die Setup-Reihenfolge nach einem
Neustart, welches Fahrzeug die Panels (v. a. das Glow-Panel, das seine Karte aus
diesem Kontext baut) zeigen -- einmal war es ein TEST-Eintrag ohne Daten."""
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _entries(hass, namen):
    from custom_components.ev_assistant.const import (
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        DOMAIN,
    )

    out = []
    for i, name in enumerate(namen):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_VEHICLE_HERSTELLER: "Marke",
                CONF_VEHICLE_MODELL: name,
                CONF_SOC_ENTITY: f"sensor.soc_{name.lower()}",
                CONF_USABLE_KWH: 50.0,
            },
            options={},
            entry_id=f"pe{i}",
            title=f"EV Assistant {name}",
        )
        entry.add_to_hass(hass)
        out.append(entry)
    return out


class _Panels:
    """Faengt die Panel-Registrierungen ab (Config je url_path, letzte gewinnt)."""

    def __init__(self):
        self.configs = {}

    async def register(self, hass, **kwargs):
        self.configs[kwargs["frontend_url_path"]] = kwargs["config"]


@asynccontextmanager
async def _geladen(hass, entries):
    """Laedt alle Eintraege (der erste Setup laedt die ganze Domain), faengt die
    Panel-Registrierungen ab und entlaedt danach wieder."""
    from custom_components.ev_assistant import _STATIC_REGISTERED
    from custom_components.ev_assistant.const import DOMAIN

    panels = _Panels()
    hass.data.setdefault(DOMAIN, {})[_STATIC_REGISTERED] = True  # kein echter HTTP-Server im Test
    hass.http = MagicMock()
    with patch("homeassistant.components.panel_custom.async_register_panel", side_effect=panels.register), \
            patch("homeassistant.components.frontend.async_remove_panel"):
        assert await hass.config_entries.async_setup(entries[0].entry_id)
        await hass.async_block_till_done()
        panels.configs.clear()
        try:
            yield panels
        finally:
            for entry in entries:
                await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()


async def test_top_level_ist_immer_der_erste_eintrag_egal_wer_zuletzt_registriert(hass):
    """Nach einem Neustart registriert je Eintrag eine Setup-Runde das Panel
    neu, wer zuletzt kommt, gewinnt -- die Reihenfolge ist zufaellig."""
    from custom_components.ev_assistant import _async_register_panel

    entries = _entries(hass, ["Haupt", "TestA", "TestB"])
    async with _geladen(hass, entries) as panels:
        for registrierende in ([0, 1, 2], [2, 1, 0], [1, 2, 0], [0, 1], [2], [1]):
            panels.configs.clear()
            for i in registrierende:
                await _async_register_panel(hass, entries[i])
            assert panels.configs, registrierende
            for url_path, cfg in panels.configs.items():
                assert cfg["config_entry_id"] == entries[0].entry_id, (registrierende, url_path)
                assert cfg["title"] == entries[0].title
                assert cfg["entities"]["soc_entity"] == "sensor.soc_haupt"


async def test_panel_bekommt_alle_fahrzeuge_in_eintragsreihenfolge(hass):
    from custom_components.ev_assistant import _async_register_panel

    entries = _entries(hass, ["Haupt", "TestA"])
    async with _geladen(hass, entries) as panels:
        await _async_register_panel(hass, entries[1])
        for cfg in panels.configs.values():
            assert cfg["config_entry_id"] == entries[0].entry_id
            assert [v["config_entry_id"] for v in cfg["vehicles"]] == [e.entry_id for e in entries]


async def test_nach_unload_des_ersten_ist_der_naechste_geladene_top_level(hass):
    from custom_components.ev_assistant import _STATIC_REGISTERED
    from custom_components.ev_assistant.const import DOMAIN

    entries = _entries(hass, ["Haupt", "TestA", "TestB"])
    panels = _Panels()
    hass.data.setdefault(DOMAIN, {})[_STATIC_REGISTERED] = True
    hass.http = MagicMock()
    with patch("homeassistant.components.panel_custom.async_register_panel", side_effect=panels.register), \
            patch("homeassistant.components.frontend.async_remove_panel"):
        assert await hass.config_entries.async_setup(entries[0].entry_id)  # laedt alle Eintraege der Domain
        await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(entries[0].entry_id)
        await hass.async_block_till_done()
        for cfg in panels.configs.values():
            assert cfg["config_entry_id"] == entries[1].entry_id
        for entry in entries[1:]:
            await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_fallback_ist_der_aufrufende_eintrag_wenn_noch_keiner_geladen(hass):
    from custom_components.ev_assistant import _primary_entry

    entries = _entries(hass, ["Haupt", "TestA"])
    assert _primary_entry(hass, entries[1]) is entries[1]
