"""coordinator.py::_persistent_notification(): best effort, aber nie still.
Vorher stand an 14 Stellen ein "except Exception: pass" um
persistent_notification.create/.dismiss."""
import logging
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _coordinator(hass, coordinators, entry_id):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator


async def test_erfolg_ruft_den_dienst_nicht_blockierend_auf(hass, coordinators):
    coordinator = await _coordinator(hass, coordinators, "pn1")
    with patch("homeassistant.core.ServiceRegistry.async_call", new=AsyncMock()) as call:
        await coordinator._persistent_notification("create", {"notification_id": "x", "title": "t", "message": "m"})
    call.assert_awaited_once_with(
        "persistent_notification", "create", {"notification_id": "x", "title": "t", "message": "m"}, blocking=False,
    )


async def test_fehlender_dienst_ist_nur_debug_und_wirft_nicht(hass, coordinators, caplog):
    from homeassistant.exceptions import ServiceNotFound

    coordinator = await _coordinator(hass, coordinators, "pn2")
    missing = AsyncMock(side_effect=ServiceNotFound("persistent_notification", "create"))
    with patch("homeassistant.core.ServiceRegistry.async_call", new=missing), caplog.at_level(
        logging.DEBUG, logger="custom_components.ev_assistant.coordinator"
    ):
        await coordinator._persistent_notification("create", {"notification_id": "x"})
    assert "persistent_notification.create nicht verfuegbar" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "persistent_notification" in r.message]


async def test_anderer_fehler_steht_als_warnung_im_log_und_wirft_nicht(hass, coordinators, caplog):
    coordinator = await _coordinator(hass, coordinators, "pn3")
    broken = AsyncMock(side_effect=ValueError("kaputter Payload"))
    with patch("homeassistant.core.ServiceRegistry.async_call", new=broken), caplog.at_level(
        logging.WARNING, logger="custom_components.ev_assistant.coordinator"
    ):
        await coordinator._persistent_notification("dismiss", {"notification_id": "x"})
    assert "persistent_notification.dismiss fehlgeschlagen: kaputter Payload" in caplog.text
