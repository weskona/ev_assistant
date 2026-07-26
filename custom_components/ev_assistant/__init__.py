"""ev_assistant — Fremdladung: Setup, Services, Unload."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN, PLATFORMS, SERVICE_DELETE, SERVICE_DELETE_TRIP, SERVICE_DISCARD,
    SERVICE_DISCARD_TRIP, SERVICE_EDIT, SERVICE_EDIT_TRIP, SERVICE_EXPORT_TRIPS,
    SERVICE_LOG, SERVICE_LOG_TRIP, SERVICE_SIMULATE, SERVICE_SIMULATE_TRIP,
    EVCC_CONF_KEYS,
)
from .coordinator import EvAssistantCoordinator

_LOGGER = logging.getLogger(__name__)

_PANEL_URL_PATH = "ev-assistant"
_PANEL_STATIC_PATH = "/ev_assistant_static"
_PANEL_TITLE = "EV Assistant"
_PANEL_ICON = "mdi:car-electric"
_STATIC_REGISTERED = "_ev_panel_static"
_PANEL_REGISTERED = "_ev_panel"


async def _async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Sidebar-Panel registrieren. Fehler blockieren nie den Setup."""
    try:
        from homeassistant.components import frontend, panel_custom
        from homeassistant.components.http import StaticPathConfig
        from homeassistant.helpers import entity_registry as er

        domain_data = hass.data.setdefault(DOMAIN, {})
        frontend_dir = Path(__file__).parent / "frontend"

        if not domain_data.get(_STATIC_REGISTERED):
            await hass.http.async_register_static_paths(
                [StaticPathConfig(_PANEL_STATIC_PATH, str(frontend_dir), cache_headers=False)]
            )
            domain_data[_STATIC_REGISTERED] = True

        js_file = frontend_dir / "ev-assistant-panel.js"
        try:
            cache_bust = str(int(js_file.stat().st_mtime))
        except Exception:
            cache_bust = "1"

        # Entity-IDs aus der Registry holen: unique_id = "{entry_id}_{key}"
        ent_reg = er.async_get(hass)
        entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        entity_map = {}
        prefix = entry.entry_id + "_"
        for e in entries:
            if e.unique_id.startswith(prefix):
                entity_map[e.unique_id[len(prefix):]] = e.entity_id

        # Evcc-Dashboard-Entitäten aus options/data ergänzen
        for key in EVCC_CONF_KEYS:
            eid = entry.options.get(key) or entry.data.get(key)
            if eid:
                entity_map[key] = eid

        panel_config = {"title": entry.title, "entities": entity_map}

        try:
            frontend.async_remove_panel(hass, _PANEL_URL_PATH, warn_if_unknown=False)
        except Exception:
            pass

        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=_PANEL_URL_PATH,
            webcomponent_name="ev-assistant-panel",
            module_url=f"{_PANEL_STATIC_PATH}/ev-assistant-panel.js?v={cache_bust}",
            sidebar_title=_PANEL_TITLE,
            sidebar_icon=_PANEL_ICON,
            require_admin=False,
            config=panel_config,
        )
        domain_data[_PANEL_REGISTERED] = True
        _LOGGER.info("EV Assistant Panel registriert (v=%s, %d entities)", cache_bust, len(entity_map))
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("EV Assistant Panel konnte nicht registriert werden: %s", exc)


def _async_unregister_panel(hass: HomeAssistant) -> None:
    """Panel beim Entladen des letzten Entries entfernen."""
    if not hass.data.get(DOMAIN, {}).get(_PANEL_REGISTERED):
        return
    try:
        from homeassistant.components import frontend
        frontend.async_remove_panel(hass, _PANEL_URL_PATH, warn_if_unknown=False)
        hass.data[DOMAIN].pop(_PANEL_REGISTERED, None)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Fehler beim Entfernen des Panels: %s", exc)

LOG_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("kwh"): vol.Coerce(float),
    vol.Required("price_kwh"): vol.Coerce(float),
    vol.Optional("start_ts"): vol.Coerce(float),
})

DISCARD_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Optional("start_ts"): vol.Coerce(float),
})

SIMULATE_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("soc_start"): vol.Coerce(float),
    vol.Required("soc_end"): vol.Coerce(float),
    vol.Optional("energy_source", default="soc"): str,
})

EDIT_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("erfasst_ts"): vol.Coerce(int),
    vol.Required("kwh"): vol.Coerce(float),
    vol.Required("price_kwh"): vol.Coerce(float),
})

DELETE_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("erfasst_ts"): vol.Coerce(int),
})

LOG_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("start_ort"): str,
    vol.Required("end_ort"): str,
    vol.Optional("start_ts"): vol.Coerce(float),
})

DISCARD_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Optional("start_ts"): vol.Coerce(float),
})

EXPORT_TRIPS_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
})

SIMULATE_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("km"): vol.Coerce(float),
})

EDIT_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("erfasst_ts"): vol.Coerce(int),
    vol.Required("start_ort"): str,
    vol.Required("end_ort"): str,
})

DELETE_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("erfasst_ts"): vol.Coerce(int),
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EvAssistantCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    _register_services(hass)
    await _async_register_panel(hass, entry)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _coordinator_for(hass: HomeAssistant, config_entry_id: str) -> EvAssistantCoordinator | None:
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry_id)
    if coordinator is None:
        _LOGGER.warning("ev_assistant: unbekannte config_entry_id %s", config_entry_id)
    return coordinator


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_LOG):
        return

    async def _handle_log(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_log_charge(
                call.data["kwh"], call.data["price_kwh"], call.data.get("start_ts")
            )

    async def _handle_discard(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_discard(call.data.get("start_ts"))

    async def _handle_simulate(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_simulate(
                call.data["soc_start"], call.data["soc_end"], call.data.get("energy_source", "soc")
            )

    async def _handle_edit(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_edit_charge(
                call.data["erfasst_ts"], call.data["kwh"], call.data["price_kwh"]
            )

    async def _handle_delete(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_delete_charge(call.data["erfasst_ts"])

    async def _handle_log_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_log_trip(
                call.data["start_ort"], call.data["end_ort"], call.data.get("start_ts")
            )

    async def _handle_discard_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_discard_trip(call.data.get("start_ts"))

    async def _handle_export_trips(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_export_fahrtenbuch()

    async def _handle_simulate_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_simulate_trip(call.data["km"])

    async def _handle_edit_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_edit_trip(
                call.data["erfasst_ts"], call.data["start_ort"], call.data["end_ort"]
            )

    async def _handle_delete_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_delete_trip(call.data["erfasst_ts"])

    hass.services.async_register(DOMAIN, SERVICE_LOG, _handle_log, schema=LOG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISCARD, _handle_discard, schema=DISCARD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SIMULATE, _handle_simulate, schema=SIMULATE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_EDIT, _handle_edit, schema=EDIT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE, _handle_delete, schema=DELETE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_LOG_TRIP, _handle_log_trip, schema=LOG_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISCARD_TRIP, _handle_discard_trip, schema=DISCARD_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_EXPORT_TRIPS, _handle_export_trips, schema=EXPORT_TRIPS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SIMULATE_TRIP, _handle_simulate_trip, schema=SIMULATE_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_EDIT_TRIP, _handle_edit_trip, schema=EDIT_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_TRIP, _handle_delete_trip, schema=DELETE_TRIP_SCHEMA)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        if not hass.data[DOMAIN]:
            _async_unregister_panel(hass)
            for service in (
                SERVICE_LOG, SERVICE_DISCARD, SERVICE_SIMULATE, SERVICE_EDIT, SERVICE_DELETE,
                SERVICE_LOG_TRIP, SERVICE_DISCARD_TRIP, SERVICE_EXPORT_TRIPS, SERVICE_SIMULATE_TRIP,
                SERVICE_EDIT_TRIP, SERVICE_DELETE_TRIP,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok
