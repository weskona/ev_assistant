"""Glow-Panel (zweiter Sidebar-Eintrag, Karte aus deepblue120/glow-dashboard,
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


async def test_beide_panels_werden_registriert_mit_api_version(hass):
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

    async def _register(hass_, **kwargs):
        registriert[kwargs["frontend_url_path"]] = kwargs

    hass.data.setdefault(DOMAIN, {})[_STATIC_REGISTERED] = True
    hass.http = MagicMock()
    with patch("homeassistant.components.panel_custom.async_register_panel", side_effect=_register), \
            patch("homeassistant.components.frontend.async_remove_panel"):
        await _async_register_panel(hass, entry)

    assert set(registriert) == {"ev-assistant", "ev-assistant-glow"}
    glow = registriert["ev-assistant-glow"]
    assert glow["webcomponent_name"] == "ev-assistant-glow-panel"
    assert glow["module_url"].startswith("/ev_assistant_static/ev-assistant-glow-panel.js?v=")
    assert glow["config"]["api_version"] == 1
    assert registriert["ev-assistant"]["config"]["api_version"] == 1
    # seit 0.99.67: Glow ist das Haupt-Panel, das klassische heisst "(klassisch)"; die URL-Pfade bleiben
    assert glow["sidebar_title"] == "EV Assistant" and glow["sidebar_icon"] == "mdi:ev-station"
    assert registriert["ev-assistant"]["sidebar_title"] == "EV Assistant (klassisch)"
    assert registriert["ev-assistant"]["sidebar_title"] > glow["sidebar_title"]  # Glow steht alphabetisch zuerst
    assert registriert["ev-assistant"]["sidebar_icon"] != glow["sidebar_icon"]
    assert glow["config"]["config_entry_id"] == registriert["ev-assistant"]["config"]["config_entry_id"]
