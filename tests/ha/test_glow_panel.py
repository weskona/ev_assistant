"""Glow-Panel (einziges Panel, Karte aus deepblue120/glow-dashboard,
siehe Issue #12): Registrierung, Schnittstellenversion und die mitgelieferten
Dateien. Die Karte selbst wird nie von Hand editiert (glow-sync-check.yml);
hier steht nur der Vertrag zwischen Integration und Karte."""
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

FRONTEND = Path(__file__).resolve().parents[2] / "custom_components" / "ev_assistant" / "frontend"


def test_glow_dateien_sind_vorhanden():
    for name in ("ev-assistant-glow-panel.js", "mg-car-dashboard.js", "GLOW_VERSION"):
        assert (FRONTEND / name).is_file(), name
    ref = (FRONTEND / "GLOW_VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"v\d+\.\d+\.\d+", ref) or re.fullmatch(r"[0-9a-f]{7,40}", ref), ref
    assert (FRONTEND / "mg-car-dashboard.js").stat().st_size > 10_000


def test_karte_erwartet_die_api_version_der_integration():
    """Ein Karten-Update mit anderer EVA_API_VERSION muss mit einem Hochzaehlen
    von __init__.py::_PANEL_API_VERSION einhergehen (sonst warnt die Karte)."""
    from custom_components.ev_assistant import _PANEL_API_VERSION

    text = (FRONTEND / "mg-car-dashboard.js").read_text(encoding="utf-8")
    match = re.search(r"^const EVA_API_VERSION = (\d+);", text, re.MULTILINE)
    assert match, "EVA_API_VERSION nicht gefunden"
    assert int(match.group(1)) == _PANEL_API_VERSION


def test_wrapper_definiert_das_registrierte_webcomponent():
    text = (FRONTEND / "ev-assistant-glow-panel.js").read_text(encoding="utf-8")
    assert 'customElements.define("ev-assistant-glow-panel"' in text
    assert '"mg-car-dashboard.js"' in text  # laedt die Karte neben sich


async def test_nur_glow_panel_wird_registriert_mit_api_version(hass):
    from custom_components.ev_assistant import _STATIC_REGISTERED, _async_register_panel
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
            CONF_VEHICLE_HERSTELLER: "Marke", CONF_VEHICLE_MODELL: "Modell",
            CONF_SOC_ENTITY: "sensor.soc", CONF_USABLE_KWH: 50.0,
        },
        options={}, entry_id="glow1",
    )
    entry.add_to_hass(hass)
    registriert = {}

    # echte Funktion statt Mock, damit HAs Signaturpruefung auf handle_safe_area greift
    async def _register(hass_, *, handle_safe_area=None, **kwargs):
        if handle_safe_area is not None:
            kwargs["handle_safe_area"] = handle_safe_area
        registriert[kwargs["frontend_url_path"]] = kwargs

    hass.data.setdefault(DOMAIN, {})[_STATIC_REGISTERED] = True
    hass.http = MagicMock()
    with patch("homeassistant.components.panel_custom.async_register_panel", new=_register), \
            patch("homeassistant.components.frontend.async_remove_panel"):
        await _async_register_panel(hass, entry)

    # seit 0.99.76 ist Glow das einzige Panel, unter dem bisherigen URL-Pfad
    assert set(registriert) == {"ev-assistant"}
    panel = registriert["ev-assistant"]
    assert panel["webcomponent_name"] == "ev-assistant-glow-panel"
    assert panel["module_url"].startswith("/ev_assistant_static/ev-assistant-glow-panel.js?v=")
    assert panel["sidebar_title"] == "EV Assistant" and panel["sidebar_icon"] == "mdi:ev-station"
    assert panel["config"]["api_version"] == 1
    assert panel["config"]["config_entry_id"] == entry.entry_id
    # Glow bekommt den Safe-Area-Abstand von HA (iOS-App)
    assert panel.get("handle_safe_area") is False


def test_klassisches_panel_ist_entfernt():
    assert not (FRONTEND / "ev-assistant-panel.js").exists()


async def test_alte_anzeigeeinstellungen_des_klassischen_panels_werden_beim_laden_verworfen(
    hass, hass_storage, coordinators
):
    """panel_layout/hidden_tabs (set_panel_layout/set_hidden_tabs, bis 0.99.75)
    gehoerten nur dem entfallenen klassischen Panel und werden nicht mehr
    mitgeschleppt."""
    from custom_components.ev_assistant.const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="alt1")
    entry.add_to_hass(hass)
    hass_storage[f"{STORAGE_KEY}_{entry.entry_id}"] = {
        "version": STORAGE_VERSION,
        "data": {"panel_layout": [{"key": "soc", "visible": True}], "hidden_tabs": ["wartung"], "fahrten": []},
    }
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    assert "panel_layout" not in coordinator.data and "hidden_tabs" not in coordinator.data
    assert coordinator.data["fahrten"] == []
