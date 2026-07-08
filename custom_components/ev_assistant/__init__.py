"""ev_assistant — Fremdladung: Setup, Services, Unload."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, PLATFORMS, SERVICE_DISCARD, SERVICE_LOG, SERVICE_SIMULATE
from .coordinator import EvAssistantCoordinator

LOG_SCHEMA = vol.Schema({
    vol.Required("kwh"): vol.Coerce(float),
    vol.Required("price_kwh"): vol.Coerce(float),
    vol.Optional("start_ts"): vol.Coerce(float),
})

SIMULATE_SCHEMA = vol.Schema({
    vol.Required("soc_start"): vol.Coerce(float),
    vol.Required("soc_end"): vol.Coerce(float),
    vol.Optional("energy_source", default="soc"): str,
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EvAssistantCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    _register_services(hass)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _first_coordinator(hass: HomeAssistant) -> EvAssistantCoordinator | None:
    return next(iter(hass.data.get(DOMAIN, {}).values()), None)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_LOG):
        return

    async def _handle_log(call: ServiceCall) -> None:
        coordinator = _first_coordinator(hass)
        if coordinator:
            await coordinator.async_log_charge(
                call.data["kwh"], call.data["price_kwh"], call.data.get("start_ts")
            )

    async def _handle_discard(call: ServiceCall) -> None:
        coordinator = _first_coordinator(hass)
        if coordinator:
            await coordinator.async_discard()

    async def _handle_simulate(call: ServiceCall) -> None:
        coordinator = _first_coordinator(hass)
        if coordinator:
            await coordinator.async_simulate(
                call.data["soc_start"], call.data["soc_end"], call.data.get("energy_source", "soc")
            )

    hass.services.async_register(DOMAIN, SERVICE_LOG, _handle_log, schema=LOG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISCARD, _handle_discard)
    hass.services.async_register(DOMAIN, SERVICE_SIMULATE, _handle_simulate, schema=SIMULATE_SCHEMA)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        if not hass.data[DOMAIN]:
            for service in (SERVICE_LOG, SERVICE_DISCARD, SERVICE_SIMULATE):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok
